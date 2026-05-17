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
# commlink_secured.py, a plugin for minqlx to enable authenticated inter-server
# communication functionality.
# This plugin is released to everyone, for any purpose. It comes with no warranty, no guarantee it works, it's released AS IS.
# You can modify everything, except for lines 1-4 and the !tomtec_versions code. Please make it better :D

#Modified by OrbitaL on 9/19/2019 changed irc server

# Modified by BarelyMiSSeD on 10/6/2019: (only team games modifications)
# added - !status (responds with the player status of the other servers)
# added - !need <num> (tells other server that num of players is needed on the requesting server)

# Set the following cvars:
# qlx_commlinkIdentity - Same identity for all linked servers. Required.
# qlx_commlinkServerName - 12-character-or-less server label. Default: Server-XXXX.
# qlx_enableConnectDisconnectMessages - Send connect/disconnect notices. Default: 1.
# qlx_enableCommlinkMessages - Enable CommLink reception by default. Default: 1.
# qlx_commlinkAuthSecret - Shared secret for signed IRC messages. Default: empty.

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import random
import re
import secrets
import threading
import time
import urllib.error
import urllib.request

import minqlx

TEAM_BASED_GAMETYPES = ("ca", "ctf", "ft", "tdm", "ictf", "wipeout", "dom", "ad", "1f", "har")

IRC_CONNECT_TIMEOUT = 10
PUBLIC_IP_TIMEOUT = 3
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 300
IRC_USERNAME_MAX_LENGTH = 10
COMMLINK_UNAVAILABLE_MSG = "^3CommLink^7 unavailable."
EXPECTED_TRANSPORT_ERRORS = (OSError, asyncio.TimeoutError)
AUTH_MESSAGE_PREFIX = "CLS1:"
DEFAULT_MAX_AGE_SECONDS = 300
COMMLINK_MASTER_FLAG = "commlink:enabled"
COMMLINK_CHAT_FLAG = "commlink:chat_enabled"
COMMLINK_EVENTS_FLAG = "commlink:events_enabled"
IRC_MAX_NICK_LENGTH = 20
PLAYER_COMMAND_COOLDOWN = 5
MESSAGE_KIND_CHAT = "chat"
MESSAGE_KIND_EVENT = "event"
MESSAGE_KIND_NOTICE = "notice"
MESSAGE_KIND_CONTROL = "control"
CONTROL_CHARS = {
    ord("\r"): None,
    ord("\n"): None,
    ord("\x00"): None,
}


def sanitize_irc_text(text):
    return "" if text is None else str(text).translate(CONTROL_CHARS)


def _b64encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(token):
    padded = token + "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _canonical_json(payload):
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def _signature(secret, payload):
    return hmac.new(secret.encode("utf-8"), _canonical_json(payload), hashlib.sha256).hexdigest()


def sign_message(secret, text, now=None, kind=MESSAGE_KIND_CHAT):
    if not secret:
        return sanitize_irc_text(text)

    payload = {
        "v": 1,
        "ts": int(now if now is not None else time.time()),
        "n": secrets.token_urlsafe(12),
        "t": sanitize_irc_text(text),
        "k": sanitize_irc_text(kind) or MESSAGE_KIND_CHAT,
    }
    payload["sig"] = _signature(secret, payload)
    return AUTH_MESSAGE_PREFIX + _b64encode(_canonical_json(payload))


def verify_message(secret, wire_text, max_age=DEFAULT_MAX_AGE_SECONDS, now=None):
    wire_text = sanitize_irc_text(wire_text).strip()
    if not wire_text.startswith(AUTH_MESSAGE_PREFIX) or not secret:
        return None
    try:
        raw = _b64decode(wire_text[len(AUTH_MESSAGE_PREFIX):])
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    received_sig = payload.pop("sig", None)
    if not isinstance(received_sig, str):
        return None
    if not hmac.compare_digest(received_sig, _signature(secret, payload)):
        return None
    if payload.get("v") != 1:
        return None

    ts = payload.get("ts")
    nonce = payload.get("n")
    text = payload.get("t")
    kind = payload.get("k", MESSAGE_KIND_CHAT)
    if not isinstance(ts, int) or not isinstance(nonce, str) or not isinstance(text, str):
        return None
    if not isinstance(kind, str):
        return None
    current_time = int(now if now is not None else time.time())
    if abs(current_time - ts) > max_age:
        return None
    return {"text": sanitize_irc_text(text), "kind": sanitize_irc_text(kind), "nonce": nonce, "ts": ts}


re_msg = re.compile(r"^:([^ ]+) PRIVMSG ([^ ]+) :(.*)$")
re_user = re.compile(r"^(.+)!(.+)@(.+)$")


class commlink_secured(minqlx.Plugin):
    def __init__(self):
        self.plugin_version = "1.5.pew"
        self.status_request = False
        self.server_ip = ""
        self.irc = None
        self.auth_seen_nonces = {}
        self._player_last_cmd = {}

        identity = self.get_cvar("qlx_commlinkIdentity")
        if not identity:
            return

        self.add_hook("unload", self.handle_unload)
        self.add_hook("player_connect", self.handle_player_connect, priority=minqlx.PRI_LOWEST)
        self.add_hook("player_disconnect", self.handle_player_disconnect, priority=minqlx.PRI_LOWEST)
        self.add_hook("game_countdown", self.game_countdown)

        self.set_cvar_once("qlx_commlinkServerName", "Server-{}".format(random.randint(1000, 9999)))
        self.set_cvar_once("qlx_commlinkAuthSecret", "")
        self.set_cvar_once("qlx_enableConnectDisconnectMessages", "1")
        self.set_cvar_once("qlx_enableCommlinkMessages", "1")

        if not (self.get_cvar("qlx_commlinkAuthSecret") or "").strip():
            self.logger.warning("qlx_commlinkAuthSecret is not set — inter-server messages are unsigned.")

        self.server = "irc.quakenet.org"
        self.identity = ("#" + identity)
        self.clientName = self.get_cvar("qlx_commlinkServerName")

        self.add_command(("world", "say_world"), self.send_commlink_message, priority=minqlx.PRI_LOWEST, usage="<message>")
        self.add_command("tomtec_versions", self.cmd_showversion)
        self.add_command("commlink", self.cmd_toggle_commlink)
        self.add_command("commlinkchat", self.cmd_toggle_commlink_chat)
        self.add_command("commlinkevents", self.cmd_toggle_commlink_events)
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
                "https://checkip.amazonaws.com/",
                timeout=PUBLIC_IP_TIMEOUT,
            ).read()
        except (urllib.error.URLError, TimeoutError, OSError):
            self.server_ip = ""
            return

        self.server_ip = res.decode("utf-8", errors="ignore").strip()

    def _check_and_update_cooldown(self, player):
        now = time.time()
        last = self._player_last_cmd.get(player.steam_id, 0)
        remaining = PLAYER_COMMAND_COOLDOWN - (now - last)
        if remaining > 0:
            player.tell("^3CommLink^7 cooldown: wait ^1{:.0f}s^7.".format(remaining))
            return False
        self._player_last_cmd[player.steam_id] = now
        return True

    def commlink_available(self):
        irc = getattr(self, "irc", None)
        return bool(irc and irc.is_ready())

    def tell_commlink_unavailable(self, player):
        player.tell(COMMLINK_UNAVAILABLE_MSG)

    def get_auth_secret(self):
        return (self.get_cvar("qlx_commlinkAuthSecret") or "").strip()

    def encode_outbound_message(self, text, kind=MESSAGE_KIND_CHAT):
        text = sanitize_irc_text(text)
        secret = self.get_auth_secret()
        if not secret:
            return text
        return sign_message(secret, text, kind=kind)

    def decode_inbound_message(self, msg):
        wire_text = sanitize_irc_text(" ".join(msg)).strip()
        secret = self.get_auth_secret()
        if secret:
            verified = verify_message(secret, wire_text)
            if not verified or self.is_replayed_auth_message(verified):
                return None
            return verified
        if wire_text.startswith(AUTH_MESSAGE_PREFIX):
            return None
        return {"text": wire_text, "kind": self.classify_plaintext_message(wire_text)}

    def classify_plaintext_message(self, text):
        words = text.split()
        if not words:
            return MESSAGE_KIND_CHAT
        if words[0] == "request_status":
            return MESSAGE_KIND_CONTROL
        if words[0] == "Need":
            return MESSAGE_KIND_NOTICE
        if (
            len(words) >= 3 and
            (words[0].startswith("Duel-") or words[0].startswith("Free-")) and
            words[1].startswith("Spec-")
        ):
            return MESSAGE_KIND_NOTICE
        if (
            len(words) >= 4 and
            words[0].startswith("Red-") and
            words[1].startswith("Blue-") and
            words[2].startswith("Spec-")
        ):
            return MESSAGE_KIND_NOTICE
        if text.endswith(" connected."):
            return MESSAGE_KIND_EVENT
        return MESSAGE_KIND_CHAT

    def is_replayed_auth_message(self, verified):
        seen = getattr(self, "auth_seen_nonces", None)
        if seen is None:
            seen = {}
            self.auth_seen_nonces = seen

        current_ts = verified["ts"]
        cutoff = current_ts - DEFAULT_MAX_AGE_SECONDS
        for nonce, ts in list(seen.items()):
            if ts < cutoff:
                del seen[nonce]

        nonce = verified["nonce"]
        if nonce in seen:
            return True
        seen[nonce] = current_ts
        return False

    def send_irc_message(self, recipient, text, kind=MESSAGE_KIND_CHAT):
        if not self.commlink_available():
            return False
        encoded = self.encode_outbound_message(text, kind=kind)
        if encoded is None:
            return False
        try:
            return self.irc.msg(recipient, encoded)
        except EXPECTED_TRANSPORT_ERRORS:
            return False

    def game_countdown(self):
        if self.game.type_short == "duel":
            self.msg("^3CommLink^7 message reception has been disabled during your Duel.")

    def cmd_toggle_commlink(self, player, msg, channel):
        flag = self.db.get_flag(player, COMMLINK_MASTER_FLAG, default=(self.get_cvar("qlx_enableCommlinkMessages", bool)))
        self.db.set_flag(player, COMMLINK_MASTER_FLAG, not flag)
        if flag:
            word = "disabled"
        else:
            word = "enabled"
        player.tell("^3CommLink^7 notices have been ^4{}^7.".format(word))
        return minqlx.RET_STOP_ALL

    def cmd_toggle_commlink_chat(self, player, msg, channel):
        return self.toggle_commlink_subcategory(
            player,
            COMMLINK_CHAT_FLAG,
            "^3CommLink^7 chat messages have been ^4{}^7.",
        )

    def cmd_toggle_commlink_events(self, player, msg, channel):
        return self.toggle_commlink_subcategory(
            player,
            COMMLINK_EVENTS_FLAG,
            "^3CommLink^7 connect/disconnect notices have been ^4{}^7.",
        )

    def toggle_commlink_subcategory(self, player, flag_name, message):
        flag = self.db.get_flag(player, flag_name, default=True)
        self.db.set_flag(player, flag_name, not flag)
        word = "disabled" if flag else "enabled"
        player.tell(message.format(word))
        return minqlx.RET_STOP_ALL

    def player_receives_commlink(self, player, kind):
        if not self.db.get_flag(player, COMMLINK_MASTER_FLAG, default=(self.get_cvar("qlx_enableCommlinkMessages", bool))):
            return False
        if kind == MESSAGE_KIND_CHAT:
            return self.db.get_flag(player, COMMLINK_CHAT_FLAG, default=True)
        if kind == MESSAGE_KIND_EVENT:
            return self.db.get_flag(player, COMMLINK_EVENTS_FLAG, default=True)
        return True

    def handle_unload(self, plugin):
        if plugin == self.__class__.__name__ and self.irc and self.irc.is_alive():
            self.irc.quit("CommLink plugin unloaded.")
            self.irc.stop()

    def handle_player_connect(self, player):
        if not self.get_cvar("qlx_enableConnectDisconnectMessages", bool):
            return
        if str(player.steam_id).startswith("9"):
            return
        self.send_irc_message(
            self.identity,
            self.translate_colors("{} connected.".format(player.name)),
            kind=MESSAGE_KIND_EVENT,
        )

    def handle_player_disconnect(self, player, reason):
        if reason and reason[-1] not in ("?", "!", "."):
            reason = reason + "."

        if not self.get_cvar("qlx_enableConnectDisconnectMessages", bool):
            return
        if str(player.steam_id).startswith("9"):
            return
        self.send_irc_message(
            self.identity,
            self.translate_colors("{} {}".format(player.name, reason)),
            kind=MESSAGE_KIND_EVENT,
        )

    def handle_msg(self, irc, user, channel, msg):
        def broadcast_commlink(pm, kind):
            is_free_status = (
                len(pm) >= 3 and
                (pm[0].startswith("Duel-") or pm[0].startswith("Free-")) and
                pm[1].startswith("Spec-")
            )
            is_team_status = (
                len(pm) >= 4 and
                pm[0].startswith("Red-") and
                pm[1].startswith("Blue-") and
                pm[2].startswith("Spec-")
            )
            if is_free_status:
                if not self.status_request:
                    return
                self.unset_server_status()
                pm[0] = "^3{}".format(pm[0])
                pm[1] = "^6{}".format(pm[1])
                pm[2] = "^5/connect {}".format(pm[2])
            elif is_team_status:
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
                if self.player_receives_commlink(p, kind):
                    p.tell("[CommLink] ^4{}^7:^3 {}".format(user[0], " ".join(pm)))

        if not msg:
            return
        if channel.lower() != self.identity.lower():
            return
        decoded = self.decode_inbound_message(msg)
        if not decoded:
            return
        msg = decoded["text"].split()
        if not msg:
            return
        if msg[0] == 'request_status':
            status = self.get_status_msg()
            self.send_irc_message(
                self.identity,
                "{} {}:{}".format(status, self.server_ip, self.server_port),
                kind=MESSAGE_KIND_NOTICE,
            )
        else:
            broadcast_commlink(msg, decoded["kind"])

    def handle_perform(self, irc):
        irc.join(self.identity)

    def send_commlink_message(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE
        if not self._check_and_update_cooldown(player):
            return minqlx.RET_STOP_ALL
        if not self.commlink_available():
            self.tell_commlink_unavailable(player)
            return minqlx.RET_STOP_ALL

        text = "^7<{}> ^3{} ".format(player.name, " ".join(msg[1:]))
        if self.send_irc_message(self.identity, self.translate_colors(text), kind=MESSAGE_KIND_CHAT):
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
        if not self._check_and_update_cooldown(player):
            return minqlx.RET_STOP_ALL
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
            if self.player_receives_commlink(p, MESSAGE_KIND_NOTICE):
                p.tell("[CommLink] ^4{}^7: {}".format(self.clientName, status))
        self.status_request = True
        self.send_irc_message(self.identity, "request_status", kind=MESSAGE_KIND_CONTROL)

    @minqlx.delay(1.5)
    def unset_server_status(self):
        self.status_request = False

    def need_player(self, player, msg, channel):
        if len(msg) > 1:
            try:
                needed = int(msg[1])
            except ValueError:
                player.tell("^1You must include a number")
                return minqlx.RET_STOP_ALL
        else:
            needed = 1
        if not self._check_and_update_cooldown(player):
            return minqlx.RET_STOP_ALL
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
        if self.send_irc_message(self.identity, text, kind=MESSAGE_KIND_NOTICE):
            player.tell("^6Sent player request to other servers")
        else:
            self.tell_commlink_unavailable(player)
        return minqlx.RET_STOP_ALL

    def handle_raw(self, irc, msg):
        split_msg = msg.split()
        if len(split_msg) > 1 and split_msg[1] == "433":
            attempted = split_msg[3] if len(split_msg) > 3 else irc.nickname
            suffix = "_{:04d}".format(random.randint(0, 9999))
            irc.nick(attempted[:IRC_MAX_NICK_LENGTH - len(suffix)] + suffix)

    @classmethod
    def translate_colors(cls, text):
        return cls.clean_text(text)

    def cmd_showversion(self, player, msg, channel):
        channel.reply("^4commlink_secured.py^7 - version {}, by Thomas Jones, ^1O^7rbitaL, & Barely^4MiSSeD.".format(self.plugin_version))


# ====================================================================
#                        COMMLINK CHANNEL
# ====================================================================


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
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=IRC_CONNECT_TIMEOUT,
            )
            with self._lock:
                self.reader = reader
                self.writer = writer
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
            with self._lock:
                writer = self.writer
                self.reader = None
                self.writer = None
            if writer:
                self.quit("Quit by user.")
                try:
                    writer.close()
                    wait_closed = getattr(writer, "wait_closed", None)
                    if wait_closed:
                        await wait_closed()
                except EXPECTED_TRANSPORT_ERRORS:
                    pass
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
        elif re.match(r":[^ ]+ (376|422) .+", msg):
            self.set_ready()
            self.perform_handler(self)

        if self.raw_handler:
            self.raw_handler(self, msg)

    def msg(self, recipient, msg):
        recipient = sanitize_irc_text(recipient).strip()
        msg = sanitize_irc_text(msg)
        return self.write("PRIVMSG {} :{}\r\n".format(recipient, msg))

    def nick(self, nick):
        nick = sanitize_irc_text(nick).strip()
        with self._lock:
            self._old_nickname = self.nickname
            self.nickname = nick
        return self.write("NICK {}\r\n".format(nick))

    def join(self, channels):
        channels = sanitize_irc_text(channels).strip()
        return self.write("JOIN {}\r\n".format(channels))

    def part(self, channels):
        channels = sanitize_irc_text(channels).strip()
        return self.write("PART {}\r\n".format(channels))

    def mode(self, what, mode):
        what = sanitize_irc_text(what).strip()
        mode = sanitize_irc_text(mode).strip()
        return self.write("MODE {} {}\r\n".format(what, mode))

    def kick(self, channel, nick, reason):
        channel = sanitize_irc_text(channel).strip()
        nick = sanitize_irc_text(nick).strip()
        reason = sanitize_irc_text(reason)
        return self.write("KICK {} {} :{}\r\n".format(channel, nick, reason))

    def quit(self, reason):
        reason = sanitize_irc_text(reason)
        return self.write("QUIT :{}\r\n".format(reason))

    def pong(self, n):
        n = sanitize_irc_text(n).strip()
        return self.write("PONG :{}\r\n".format(n))


class IrcChannel(minqlx.AbstractChannel):
    name = "irc"

    def __init__(self, irc, recipient):
        self.irc = irc
        self.recipient = recipient

    def __repr__(self):
        return "{} {}".format(str(self), self.recipient)

    def reply(self, msg):
        for line in msg.split("\n"):
            self.irc.msg(self.recipient, commlink_secured.translate_colors(line))
