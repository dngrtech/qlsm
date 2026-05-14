# minqlx - A Quake Live server administrator bot.
# Copyright (C) 2015 Mino <mino@minomino.org>

# minqlx is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# minqlx is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with minqlx. If not, see <http://www.gnu.org/licenses/>.


# Modified by Thomas Jones on 27/01/2016 - thomas@tomtecsolutions.com
# commlink.py, a plugin for minqlx to enable inter-server communication functionality.
# This plugin is released to everyone, for any purpose. It comes with no warranty, no guarantee it works, it's released AS IS.
# You can modify everything, except for lines 1-4 and the !tomtec_versions code. Please make it better :D

#Modified by OrbitaL on 9/19/2019 changed irc server

# Modified by BarelyMiSSeD on 10/6/2019: (only team games modifications)
# added - !status (responds with the player status of the other servers)
# added - !need <num> (tells other server that num of players is needed on the requesting server)

"""

    Set the following cvars:
        qlx_commlinkIdentity                        - Set this cvar in your server.cfg, it needs to be the same for all your servers. If someone's using the same identity, there'll be crosstalk across the servers.
            No Default. This cvar MUST be set.
        qlx_commlinkServerName                      - Make this a 12 character or less identifier that will appear when messages from the server appear on other servers in the same identity group.
            Default: Server-XXXX (where X = random number)
        qlx_enableConnectDisconnectMessages         - Enables the 'Player connected.' and 'Player disconnected.' messages in CommLink.
            Default: 1
        qlx_enableCommlinkMessages                  - Enables CommLink message reception for all players. If this is set to 0, players have to manually enable CommLink with the !commlink command.
            Default: 1

"""

import minqlx
import asyncio
import random
import re
import threading
import urllib.error
import urllib.request

TEAM_BASED_GAMETYPES = ("ca", "ctf", "ft", "tdm", "ictf", "wipeout", "dom", "ad", "1f", "har")

IRC_CONNECT_TIMEOUT = 10
PUBLIC_IP_TIMEOUT = 3
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 300
IRC_USERNAME_MAX_LENGTH = 10
COMMLINK_UNAVAILABLE_MSG = "^3CommLink^7 unavailable."
EXPECTED_TRANSPORT_ERRORS = (OSError, asyncio.TimeoutError)


class commlink(minqlx.Plugin):
    def __init__(self):
        self.plugin_version = "1.5.pew"
        self.status_request = False
        self.server_ip = ""
        self.irc = None

        identity = self.get_cvar("qlx_commlinkIdentity")
        if not identity:
            return
                     
        self.add_hook("unload", self.handle_unload)
        self.add_hook("player_connect", self.handle_player_connect, priority=minqlx.PRI_LOWEST)
        self.add_hook("player_disconnect", self.handle_player_disconnect, priority=minqlx.PRI_LOWEST)
        self.add_hook("game_countdown", self.game_countdown)
        
        self.set_cvar_once("qlx_commlinkServerName", "Server-{}".format(random.randint(1000, 9999)))
        self.set_cvar_once("qlx_enableConnectDisconnectMessages", "1")
        self.set_cvar_once("qlx_enableCommlinkMessages", "1")

        self.server = "irc.quakenet.org"
        self.identity = ("#" + identity)
        self.clientName = self.get_cvar("qlx_commlinkServerName")

        self.add_command(("world", "say_world"), self.send_commlink_message, priority=minqlx.PRI_LOWEST, usage="<message>")
        self.add_command("tomtec_versions", self.cmd_showversion)
        self.add_command("commlink", self.cmd_toggle_commlink)
        self.add_command("status", self.server_status)
        self.add_command("need", self.need_player, usage="<number>")
        
        self.irc = SimpleAsyncIrc(self.server, self.clientName, self.handle_msg, self.handle_perform, self.handle_raw)
        self.irc.start()

        self.server_port = self.get_cvar("net_port")
        self.set_ip()

    @minqlx.delay(0.5)
    def set_ip(self):
        try:
            res = urllib.request.urlopen(
                "http://checkip.amazonaws.com/",
                timeout=PUBLIC_IP_TIMEOUT,
            ).read()
        except (urllib.error.URLError, TimeoutError, OSError):
            self.server_ip = ""
            return

        self.server_ip = res.decode("utf-8", errors="ignore").strip()

    def commlink_available(self):
        irc = getattr(self, "irc", None)
        return bool(irc and irc.is_ready())

    def tell_commlink_unavailable(self, player):
        player.tell(COMMLINK_UNAVAILABLE_MSG)

    def send_irc_message(self, recipient, text):
        if not self.commlink_available():
            return False
        try:
            return self.irc.msg(recipient, text)
        except EXPECTED_TRANSPORT_ERRORS:
            return False

    def game_countdown(self):
        if self.game.type_short == "duel":
            self.msg("^3CommLink^7 message reception has been disabled during your Duel.")
            
    def cmd_toggle_commlink(self, player, msg, channel):
        flag = self.db.get_flag(player, "commlink:enabled", default=(self.get_cvar("qlx_enableCommlinkMessages", bool)))
        self.db.set_flag(player, "commlink:enabled", not flag)
        if flag:
            word = "disabled"
        else:
            word = "enabled"
        player.tell("^3CommLink^7 notices have been ^4{}^7.".format(word))
        return minqlx.RET_STOP_ALL
    
    def handle_unload(self, plugin):
        if plugin == self.__class__.__name__ and self.irc and self.irc.is_alive():
            self.irc.quit("CommLink plugin unloaded.")
            self.irc.stop()

    def handle_player_connect(self, player):
        if not self.get_cvar("qlx_enableConnectDisconnectMessages", bool):
            return
        if str(player.steam_id).startswith("9"):
            return
        self.send_irc_message(self.identity, self.translate_colors("{} connected.".format(player.name)))

    def handle_player_disconnect(self, player, reason):
        if reason and reason[-1] not in ("?", "!", "."):
            reason = reason + "."
        
        if not self.get_cvar("qlx_enableConnectDisconnectMessages", bool):
            return
        if str(player.steam_id).startswith("9"):
            return
        self.send_irc_message(self.identity, self.translate_colors("{} {}".format(player.name, reason)))
        
    def handle_msg(self, irc, user, channel, msg):
        def broadcast_commlink(pm):
            if pm[0].startswith("Duel-") or pm[0].startswith("Free-") and pm[1].startswith("Spec-"):
                if not self.status_request:
                    return
                self.unset_server_status()
                pm[0] = "^3{}".format(pm[0])
                pm[1] = "^6{}".format(pm[1])
                pm[2] = "^5/connect {}".format(pm[2])
            elif pm[0].startswith("Red-") and pm[1].startswith("Blue-") and pm[2].startswith("Spec-"):
                if not self.status_request:
                    return
                self.unset_server_status()
                pm[0] = "^1{}".format(pm[0])
                pm[1] = "^4{}".format(pm[1])
                pm[2] = "^6{}".format(pm[2])
                pm[3] = "^5/connect {}".format(pm[3])
            minqlx.console_print("[CommLink] ^5{}^7:^3 {}".format(user[0], " ".join(pm)))
            duelers = self.teams()["free"]
            for p in self.players():
                if self.game.type_short == "duel" and p in duelers and self.game.state != "warmup":
                    continue
                if self.db.get_flag(p, "commlink:enabled", default=(self.get_cvar("qlx_enableCommlinkMessages", bool))):
                    p.tell("[CommLink] ^4{}^7:^3 {}".format(user[0], " ".join(pm)))

        if not msg:
            return
        if msg[0] == 'request_status':
            status = self.get_status_msg()
            self.send_irc_message(self.identity, "{} {}:{}".format(status, self.server_ip, self.server_port))
        else:
            broadcast_commlink(msg)

    def handle_perform(self, irc):
        irc.join(self.identity)

    def send_commlink_message(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE
        if not self.commlink_available():
            self.tell_commlink_unavailable(player)
            return minqlx.RET_STOP_ALL
        
        text = "^7<{}> ^3{} ".format(player.name, " ".join(msg[1:]))
        if self.send_irc_message(self.identity, self.translate_colors(text)):
            player.tell("Message sent via ^3CommLink^7.")
        else:
            self.tell_commlink_unavailable(player)
        return minqlx.RET_STOP_ALL

    def get_status_msg(self):
        teams = self.teams()
        free = len(teams["free"])
        red = len(teams["red"])
        blue = len(teams["blue"])
        spec = len(teams["spectator"])
        if self.game.type_short == "duel":
            status = "^3Duel-{}, ^6Spec-{}".format(free, spec)
        elif self.game.type_short in TEAM_BASED_GAMETYPES:
            status = "^1Red-{}, ^4Blue-{}, ^6Spec-{}".format(red, blue, spec)
        else:
            status = "^3Free-{}, ^6Spec-{}".format(free, spec)
        return status

    def server_status(self, player, msg, channel):
        if not self.commlink_available():
            self.tell_commlink_unavailable(player)
            return minqlx.RET_STOP_ALL
        self.query_status()
        return minqlx.RET_STOP_ALL

    @minqlx.thread
    def query_status(self):
        free = self.teams()["free"]
        status = self.get_status_msg()
        minqlx.console_print("[CommLink] ^5{}^7: {}".format(self.clientName, status))
        for p in self.players():
            if self.game.type_short == "duel" and p in free and self.game.state != "warmup":
                continue
            if self.db.get_flag(p, "commlink:enabled", default=(self.get_cvar("qlx_enableCommlinkMessages", bool))):
                p.tell("[CommLink] ^4{}^7: {}".format(self.clientName, status))
        self.status_request = True
        self.send_irc_message(self.identity, "request_status")

    @minqlx.delay(1.5)
    def unset_server_status(self):
        self.status_request = False

    def need_player(self, player, msg, channel):
        if len(msg) > 1:
            try:
                needed = int(msg[1])
            except:
                player.tell("^1You must include a number")
                return minqlx.RET_STOP_ALL
        else:
            needed = 1
        if not self.commlink_available():
            self.tell_commlink_unavailable(player)
            return minqlx.RET_STOP_ALL

        status = self.get_status_msg()
        text = "Need {} player{} here: {} /connect {}:{}".format(
            needed,
            "s" if needed > 1 else "",
            status,
            self.server_ip,
            self.server_port,
        )
        if self.send_irc_message(self.identity, text):
            player.tell("^6Sent player request to other servers")
        else:
            self.tell_commlink_unavailable(player)
        return minqlx.RET_STOP_ALL
         
    def handle_raw(self, irc, msg):
        split_msg = msg.split()
        if len(split_msg) > 1 and split_msg[1] == "433":
            irc.nick(irc.nickname + "_")

    @classmethod
    def translate_colors(cls, text):
        return cls.clean_text(text)

    def cmd_showversion(self, player, msg, channel):
        channel.reply("^4commlink.py^7 - version {}, by Thomas Jones, ^1O^7rbitaL, & Barely^4MiSSeD.".format(self.plugin_version))


# ====================================================================
#                        COMMLINK CHANNEL
# ====================================================================

class IrcChannel(minqlx.AbstractChannel):
    name = "irc"

    def __init__(self, irc, recipient):
        self.irc = irc
        self.recipient = recipient

    def __repr__(self):
        return "{} {}".format(str(self), self.recipient)

    def reply(self, msg):
        for line in msg.split("\n"):
            self.irc.msg(self.recipient, commlink.translate_colors(line))

# ====================================================================
#                        SIMPLE ASYNC IRC
# ====================================================================

re_msg = re.compile(r"^:([^ ]+) PRIVMSG ([^ ]+) :(.*)$")
re_user = re.compile(r"^(.+)!(.+)@(.+)$")

class SimpleAsyncIrc(threading.Thread):
    def __init__(self, address, nickname, msg_handler, perform_handler, raw_handler=None, stop_event=None):
        split_addr = address.split(":")
        self.host = split_addr[0]
        self.port = int(split_addr[1]) if len(split_addr) > 1 else 6667
        self.nickname = nickname
        self.username = self._username_from_nickname(nickname)
        self.msg_handler = msg_handler
        self.perform_handler = perform_handler
        self.raw_handler = raw_handler
        self.stop_event = stop_event or threading.Event()
        self.reader = None
        self.writer = None
        self.server_options = {}
        super().__init__()

        self._lock = threading.Lock()
        self._ready = False
        self._old_nickname = self.nickname

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        backoff = BACKOFF_BASE_SECONDS
        try:
            while not self.stop_event.is_set():
                ready_seen = False
                try:
                    ready_seen = loop.run_until_complete(self.connect())
                except Exception:
                    minqlx.log_exception()
                finally:
                    self.set_offline()

                if self.stop_event.is_set():
                    break
                if ready_seen:
                    backoff = BACKOFF_BASE_SECONDS
                self.stop_event.wait(backoff)
                if not ready_seen:
                    backoff = min(backoff * 2, BACKOFF_MAX_SECONDS)
        finally:
            loop.close()

    def stop(self):
        self.stop_event.set()

    @staticmethod
    def _username_from_nickname(nickname):
        username = re.sub(r"[^a-z0-9]", "", nickname.lower())
        if not username or not username[0].isalpha():
            username = "ql" + username
        return username[:IRC_USERNAME_MAX_LENGTH]

    def is_ready(self):
        with self._lock:
            return self._ready

    def set_ready(self):
        with self._lock:
            self._ready = True

    def set_offline(self):
        with self._lock:
            self._ready = False

    def write(self, msg):
        with self._lock:
            writer = self.writer
            is_closing = getattr(writer, "is_closing", None)
            if not writer or (is_closing and is_closing()):
                self._ready = False
                return False
            try:
                writer.write(msg.encode(errors="ignore"))
            except EXPECTED_TRANSPORT_ERRORS:
                self._ready = False
                return False
        return True

    async def connect(self):
        ready_seen = False
        self.set_offline()
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=IRC_CONNECT_TIMEOUT,
            )
            self.write("NICK {0}\r\nUSER {1} 0 * :{0}\r\n".format(self.nickname, self.username))

            while not self.stop_event.is_set():
                line = await self.reader.readline()
                if not line:
                    break
                line = line.decode("utf-8", errors="ignore").rstrip()
                if line:
                    await self.parse_data(line)
                    ready_seen = ready_seen or self.is_ready()
        except EXPECTED_TRANSPORT_ERRORS:
            return ready_seen
        finally:
            writer = self.writer
            if writer:
                self.quit("Quit by user.")
                try:
                    writer.close()
                    wait_closed = getattr(writer, "wait_closed", None)
                    if wait_closed:
                        await wait_closed()
                except EXPECTED_TRANSPORT_ERRORS:
                    pass
            self.reader = None
            self.writer = None
        return ready_seen

    async def parse_data(self, msg):
        split_msg = msg.split()
        if not split_msg:
            return
        if len(split_msg) > 1 and split_msg[0] == "PING":
            self.pong(split_msg[1].lstrip(":"))
        elif len(split_msg) > 3 and split_msg[1] == "PRIVMSG":
            r = re_msg.match(msg)
            if r:
                user_match = re_user.match(r.group(1))
                if user_match:
                    user = user_match.groups()
                    channel = user[0] if self.nickname == r.group(2) else r.group(2)
                    self.msg_handler(self, user, channel, r.group(3).split())
        elif len(split_msg) > 2 and split_msg[1] == "NICK":
            user = re_user.match(split_msg[0][1:])
            if user and user.group(1) == self.nickname:
                self.nickname = split_msg[2][1:]
        elif len(split_msg) > 1 and split_msg[1] == "005":
            for option in split_msg[3:-1]:
                opt_pair = option.split("=", 1)
                if len(opt_pair) == 1:
                    self.server_options[opt_pair[0]] = ""
                else:
                    self.server_options[opt_pair[0]] = opt_pair[1]
        elif len(split_msg) > 1 and split_msg[1] == "433":
            self.nickname = self._old_nickname
        # Stuff to do after we get the MOTD.
        elif re.match(r":[^ ]+ (376|422) .+", msg):
            self.set_ready()
            self.perform_handler(self)

        # If we have a raw handler, let it do its stuff now.
        if self.raw_handler:
            self.raw_handler(self, msg)

    def msg(self, recipient, msg):
        return self.write("PRIVMSG {} :{}\r\n".format(recipient, msg))

    def nick(self, nick):
        with self._lock:
            self._old_nickname = self.nickname
            self.nickname = nick
        return self.write("NICK {}\r\n".format(nick))

    def join(self, channels):
        return self.write("JOIN {}\r\n".format(channels))

    def part(self, channels):
        return self.write("PART {}\r\n".format(channels))

    def mode(self, what, mode):
        return self.write("MODE {} {}\r\n".format(what, mode))

    def kick(self, channel, nick, reason):
        return self.write("KICK {} {}:{}\r\n".format(channel, nick, reason))

    def quit(self, reason):
        return self.write("QUIT :{}\r\n".format(reason))

    def pong(self, n):
        return self.write("PONG :{}\r\n".format(n))
