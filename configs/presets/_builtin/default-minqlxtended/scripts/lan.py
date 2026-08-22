# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2026 Thomas Jones <me@thomasjones.id.au>

# This file is part of minqlxtended.

# minqlxtended is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# minqlxtended is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with minqlxtended. If not, see <http://www.gnu.org/licenses/>.

import ipaddress
import struct

import minqlxtended

# Route flags, from linux/route.h.
RTF_UP = 0x0001
RTF_GATEWAY = 0x0002
RTF_HOST = 0x0004

ROUTE_TABLE = "/proc/net/route"

def _route_address(field):
    """One of /proc/net/route's hex address columns as an IPv4Address.

    The kernel prints a host-order u32, so on x86-64 the bytes come out reversed and have
    to be read back to front: "013014AC" is 172.20.48.1.
    """
    return ipaddress.IPv4Address(struct.pack("<I", int(field, 16)))

def parse_routes(text, interface=""):
    """Work out the default gateway and the directly-connected subnets.

    Takes the *contents* of /proc/net/route rather than a path, so it can be run
    against a captured table. Returns ``(router, networks)``, either of which may be
    empty. Treat "found nothing" as an ordinary outcome.
    """
    gateways = []
    networks = []

    for line in text.splitlines()[1:]:  # first line is the column header
        columns = line.split()
        if len(columns) < 8:
            continue

        iface, destination, gateway, mask = columns[0], columns[1], columns[2], columns[7]
        if iface == "lo" or (interface and iface != interface):
            continue

        try:
            flags, metric = int(columns[3], 16), int(columns[6])
        except ValueError:
            continue

        # Down, or a /32 host route: a WireGuard or PPP peer rather than a subnet we sit on.
        if (not flags & RTF_UP) or (flags & RTF_HOST):
            continue

        if destination == "00000000":
            if flags & RTF_GATEWAY:
                gateways.append((metric, _route_address(gateway)))
            continue

        if flags & RTF_GATEWAY:
            continue  # reached via a router, so not a network this machine is on

        try:
            network = ipaddress.IPv4Network(
                (_route_address(destination), str(_route_address(mask))), strict=False)
        except ValueError:
            continue

        # is_private on its own isn't enough: it's true for loopback and link-local too.
        # A LAN on public address space has to be configured with qlx_lanSubnets.
        if network.is_loopback or network.is_link_local or not network.is_private:
            continue

        networks.append(network)

    # A multi-homed box legitimately has several default routes; the kernel prefers
    # whichever has the lowest metric, so we should agree with it.
    gateways.sort(key=lambda entry: entry[0])
    return (gateways[0][1] if gateways else None), tuple(networks)

def detect_network(interface=""):
    """parse_routes() against the running kernel. Never raises."""
    try:
        with open(ROUTE_TABLE) as routes:
            return parse_routes(routes.read(), interface)
    except OSError:
        return None, ()

class lan(minqlxtended.Plugin):
    """Tells LAN players when they are reaching the server the long way round.

    A player whose source address *is* the router has hairpinned out through NAT and
    back: they're on the LAN, but their traffic goes out to the internet and comes
    back, costing them latency for nothing. Anyone else inside a local subnet is
    connected directly.

    The LAN's shape is read from the kernel routing table, so nothing needs configuring
    on an ordinary host install. Every cvar below is an override for when that guess is
    wrong, most usefully when the server runs inside a container or a network namespace,
    where the routing table describes the container's network rather than the real one.

    Everything here fails open. A server that can't work out its own network lets
    everybody in rather than locking everybody out.
    """

    _qlx_lanPlayersOnly = minqlxtended.setting("qlx_lanPlayersOnly", False)
    _qlx_lanAllowIndirectConnections = minqlxtended.setting("qlx_lanAllowIndirectConnections", False)
    # All empty: work it out from the routing table.
    _qlx_lanSubnets = minqlxtended.setting("qlx_lanSubnets", "", type=list)
    _qlx_lanRouter = minqlxtended.setting("qlx_lanRouter", "")
    _qlx_lanHostname = minqlxtended.setting("qlx_lanHostname", "")
    _qlx_lanInterface = minqlxtended.setting("qlx_lanInterface", "")

    def __init__(self):
        super().__init__()

        self._warned = False
        self._recompute_network_state()

    @minqlxtended.hook("map")
    def handle_map(self, mapname, factory):
        self._recompute_network_state()

    def _recompute_network_state(self):
        """Parse the subnet and router cvars, filling gaps from the routing table."""
        networks = self._configured_subnets()
        router = self._configured_router()

        # Only ask the kernel for what has not been pinned down by a cvar.
        if (not networks) or (router is None):
            detected_router, detected_networks = detect_network(self._qlx_lanInterface.strip())
            networks = networks or list(detected_networks)
            router = router if router is not None else detected_router

        self._networks = tuple(networks)
        self._router = router

        if not self._warned:
            self._warned = True
            if not self._networks:
                self.logger.warning(
                    "No local subnet could be determined, so every player will be treated as remote. "
                    "Set qlx_lanSubnets if this server is on a LAN.")
            else:
                self.logger.info("LAN subnets: %s. Router: %s.",
                                 ", ".join(str(network) for network in self._networks),
                                 self._router if self._router else "unknown")
                # A router outside every known subnet can't be the hairpin address, which
                # leaves that whole check dead. Say so rather than guessing.
                if self._router is not None and not self._is_lan(self._router):
                    self.logger.warning(
                        "Router %s is not inside any LAN subnet, so indirect connections cannot be "
                        "detected. Check qlx_lanRouter and qlx_lanSubnets.", self._router)

    def _configured_subnets(self):
        networks = []
        # An empty cvar parses to [''], hence the filter.
        for entry in [entry for entry in self._qlx_lanSubnets if entry]:
            try:
                networks.append(ipaddress.IPv4Network(entry, strict=False))
            except ValueError:
                self.logger.warning("qlx_lanSubnets: ignoring %r, which is not a CIDR network.", entry)
        return networks

    def _configured_router(self):
        configured = self._qlx_lanRouter.strip()
        if not configured:
            return None
        try:
            return ipaddress.IPv4Address(configured)
        except ValueError:
            self.logger.warning("qlx_lanRouter: %r is not an IPv4 address.", configured)
            return None

    def _is_lan(self, address):
        return any(address in network for network in self._networks)

    def _address_of(self, player):
        """The player's address, or None if there isn't one to read.

        Player.ip is built from netadr_t.ip[4] as a dotted quad, so it's never a
        hostname and never IPv6; the engine has no v6 address type. The only thing
        that reaches the except is a dummy player, whose ip is "".
        """
        try:
            return ipaddress.IPv4Address(player.ip)
        except ValueError:
            return None

    @minqlxtended.hook("player_connect", priority=minqlxtended.Priority.HIGHEST)
    def handle_player_connect(self, player, is_bot):
        # Use the event's own flag here. This fires before the game module sets
        # ServerFlag.BOT, so player.is_bot would report every bot as human.
        if is_bot:
            return

        address = self._address_of(player)
        if address is None:
            return

        # Only the identity test. Membership is implied whenever the router sits inside a
        # LAN subnet, and _recompute_network_state warns when it doesn't.
        if (self._router is not None) and (address == self._router) and (not self._qlx_lanAllowIndirectConnections):
            # Nothing useful to say without somewhere to send them, so let them in.
            hostname = self._qlx_lanHostname.strip()
            if hostname:
                return f"You must connect using ^2/connect {hostname}:{self.get_cvar('net_port', int)}^7\n"
        elif self._qlx_lanPlayersOnly and self._networks and not self._is_lan(address):
            return "This server is for LAN clients only."

    @minqlxtended.command("lan")
    def cmd_lan(self, player, msg, channel):
        lines = ["^6LAN server connection status:"]
        for connected in self.players():
            address = self._address_of(connected)
            # Router first: with no known router every LAN address reports as local,
            # which is the honest answer when hairpinning can't be detected.
            if address is not None and self._router is not None and address == self._router:
                lines.append(f" {connected.name}^7 is at the LAN but is connected ^1via the internet^7.")
            elif address is not None and self._is_lan(address):
                lines.append(f" {connected.name}^7 is at the LAN and is connected ^2locally^7.")
            else:
                lines.append(f" {connected.name}^7 ^3is not^7 at the LAN.")

        # One reliable command rather than one per player: each client only has a
        # 64-slot ring and overrunning it drops everybody.
        self.reply_lines(channel, lines)
