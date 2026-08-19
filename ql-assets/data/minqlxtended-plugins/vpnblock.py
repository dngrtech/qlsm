# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2024-2026 Thomas Jones <me@thomasjones.id.au>

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

import bisect
import ipaddress
import time

import minqlxtended
import requests

# VPN_IP_BLOCKS_URL = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt" # VPN IPs
VPN_IP_BLOCKS_URL = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/datacenter/ipv4.txt"  # Datacentre IPs

FLAG_NAME = "bypass_vpn_blocking"

# (connect, read). The list is ~100k lines, so the read timeout has to allow for a
# slow transfer, but a stalled connect should give up quickly.
FETCH_TIMEOUT = (3.05, 30)

# Cap on how many blocked players we remember for the "announce once" behaviour.
MAX_ANNOUNCED = 512

def _build_intervals(cidrs):
    """Turn CIDR strings into sorted, merged [start, end] integer ranges.

    The list holds around 100,000 networks. Walking them and asking `address in
    network` is ~100,000 Python-level comparisons per connecting player, on the game
    thread inside player_connect, which is tens of milliseconds, i.e. several whole
    frames. Merged intervals plus a bisect answer the same question in ~17
    comparisons, and hold two int arrays instead of 100,000 IPv4Network objects.
    """
    ranges = []
    for line in cidrs:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            network = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if network.version != 4:
            continue
        ranges.append((int(network.network_address), int(network.broadcast_address)))

    if not ranges:
        return (), (), 0

    ranges.sort()
    starts = []
    ends = []
    current_start, current_end = ranges[0]
    for start, end in ranges[1:]:
        if start <= current_end + 1:
            # Overlapping or adjacent: extend rather than store a second entry.
            if end > current_end:
                current_end = end
        else:
            starts.append(current_start)
            ends.append(current_end)
            current_start, current_end = start, end
    starts.append(current_start)
    ends.append(current_end)

    return tuple(starts), tuple(ends), len(ranges)

class vpnblock(minqlxtended.Plugin):
    _qlx_blockVpnConnections = minqlxtended.setting("qlx_blockVpnConnections", True)
    _qlx_vpnBlockRefreshHours = minqlxtended.setting("qlx_vpnBlockRefreshHours", 12)

    def __init__(self):
        super().__init__()

        # One tuple, so a reader on the game thread sees a consistent pair. Rebinding a
        # single attribute is atomic under the GIL; assigning two isn't.
        self._blocks = ((), (), 0)
        self._announced_blocked_players = []
        self._announced_lookup = set()
        self._last_fetch = 0.0
        self._etag = None
        self._fetching = False
        self._update_cache()

    @minqlxtended.hook("map")
    def handle_map_load(self, mapname, factory):
        # The list changes daily at most, so a refresh window keeps a map change from
        # pulling ~4MB. `or 12` covers a cvar set to 0 as well as an unset one.
        hours = self._qlx_vpnBlockRefreshHours or 12
        if (time.time() - self._last_fetch) < hours * 3600:
            return
        self._update_cache()

    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot):
        # Use the event's own flag here. This fires before the game module sets
        # ServerFlag.BOT, so player.is_bot would report every bot as human.
        if is_bot:
            return
        if not self._qlx_blockVpnConnections:
            return

        starts, ends, _count = self._blocks
        if not starts:
            return

        # The scan is a bisect, so it's cheaper than the database read. Only ask the
        # database about players this would actually block.
        network = self._matching_range(player.ip)
        if network is None:
            return

        if self.db.get_flag(player, FLAG_NAME):
            return  # bypass VPN blocking for this player

        if player.steam_id not in self._announced_lookup:
            self.msg(f"vpnblock: Denied connection from {player.name}^7 as they are using a VPN.")
            self._remember_announced(player.steam_id)

        return (f"^7VPN connections aren't allowed on The Pur^4g^7ery. ^2Disable ^2your ^2VPN ^2to ^2join ^2the ^2match.\n"
                f"^7Your IP exists within a known VPN range (^4{player.ip}^7 is in ^4{network}^7), "
                f"if you feel there is a mistake please visit ^3thepurgery.com/discord^7.\n")

    @minqlxtended.command("vpn", permission=1, client_cmd_perm=1, usage="<id>")
    def cmd_vpn(self, player, msg, channel):
        """Checks to see if the specified player is playing from a known VPN/datacentre-based IP."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        try:
            client_id = int(msg[1])
        except ValueError:
            player.tell("Invalid client ID.")
            return minqlxtended.Return.STOP_ALL

        if not 0 <= client_id < minqlxtended.MAX_CLIENTS:
            player.tell("Invalid client ID.")
            return minqlxtended.Return.STOP_ALL

        try:
            target_player = self.player(client_id)
        except minqlxtended.NonexistentPlayerError:
            target_player = None
        if target_player is None:
            player.tell("Invalid client ID.")
            return minqlxtended.Return.STOP_ALL

        if self._matching_range(target_player.ip) is not None:
            player.tell(f"{target_player.name}^7's IP address ^2is^7 a known VPN/datacentre-based IP.")
        else:
            player.tell(f"{target_player.name}^7's IP address ^1is not^7 a known VPN/datacentre-based IP.")

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("bypassvpn", permission=4, client_cmd_perm=4, usage="<id>")
    def cmd_bypassvpn(self, player, msg, channel):
        """Allows the specified player to connect to the server while using a VPN, bypassing any VPN blocking."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, name, _target = resolved

        flag = self.db.get_flag(ident, FLAG_NAME)
        self.db.set_flag(ident, FLAG_NAME, not flag)

        if not flag:
            channel.reply(f"{name}^7 is allowed to bypass the VPN blocker.")
        else:
            channel.reply(f"{name}^7 is now blocked from using VPNs.")

    # HELPERS

    def _matching_range(self, ip):
        """The blocked range containing *ip* as a string, or None.

        ~17 integer comparisons rather than a scan of every network.
        """
        if not ip:
            return None
        try:
            address = int(ipaddress.ip_address(ip))
        except ValueError:
            # A player with no IP yet reads as "", which doesn't parse.
            return None

        starts, ends, _count = self._blocks
        if not starts:
            return None

        i = bisect.bisect_right(starts, address) - 1
        if i < 0 or address > ends[i]:
            return None

        return f"{ipaddress.ip_address(starts[i])}-{ipaddress.ip_address(ends[i])}"

    def _remember_announced(self, steam_id):
        self._announced_blocked_players.append(steam_id)
        self._announced_lookup.add(steam_id)
        while len(self._announced_blocked_players) > MAX_ANNOUNCED:
            self._announced_lookup.discard(self._announced_blocked_players.pop(0))

    @minqlxtended.thread
    def _update_cache(self):
        if self._fetching:
            return
        self._fetching = True
        try:
            headers = {"If-None-Match": self._etag} if self._etag else {}
            try:
                req = requests.get(VPN_IP_BLOCKS_URL, timeout=FETCH_TIMEOUT, headers=headers)
            except requests.RequestException as e:
                self.msg(f"vpnblock: ^1Error^7 fetching the latest VPN network blocks: {e}")
                return

            if req.status_code == 304:
                self._last_fetch = time.time()
                return

            if not req.ok:
                self.msg(f"vpnblock: Got ^1{req.status_code} ({req.reason})^7 when fetching the latest VPN network blocks.")
                return

            blocks = _build_intervals(req.text.split())
            if not blocks[0]:
                self.msg("vpnblock: ^1The fetched VPN network block list was empty or unparseable.^7")
                return

            # Single rebind, so a connect handler mid-lookup sees either the whole
            # old list or the whole new one.
            self._blocks = blocks
            self._etag = req.headers.get("ETag")
            self._last_fetch = time.time()
            starts, _ends, source_count = blocks
            self.msg(f"vpnblock: Found ^6{source_count:,}^7 VPN network blocks "
                     f"(^6{len(starts):,}^7 merged ranges) to deny connections from.")
        finally:
            self._fetching = False
