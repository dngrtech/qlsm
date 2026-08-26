# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2015 Mino <mino@minomino.org>
# Copyright (C) 2016-2026 Thomas Jones <me@thomasjones.id.au>

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

import minqlxtended
import datetime
import time
import re

LENGTH_REGEX = re.compile(r"(?P<number>[0-9]+) (?P<scale>seconds?|minutes?|hours?|days?|weeks?|months?|years?)")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PLAYER_KEY = "minqlx:players:{}"

class silence(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        self.silenced = {}

    @minqlxtended.hook("player_loaded")
    def handle_player_loaded(self, player):
        silenced = self.is_silenced(player.steam_id)
        if not silenced:
            return

        expires, score, reason = silenced
        self.silenced[player.steam_id] = (expires, score, reason)
        player.mute()
        if reason:
            player.tell(f"You have been silenced on this server until ^6{expires}^7: {reason}")
        else:
            player.tell(f"You have been silenced on this server until ^6{expires}^7.")

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        if player.steam_id in self.silenced:
            del self.silenced[player.steam_id]

    @minqlxtended.hook("new_game")
    def handle_new_game(self):
        """ Releases silences that lapsed during the last map. """
        now = time.time()
        for steam_id in [sid for sid, (_expires, score, _reason) in self.silenced.items() if now >= score]:
            self._release(steam_id)

    @minqlxtended.hook("client_command", priority=minqlxtended.Priority.HIGH)
    def handle_client_command(self, player, cmd):
        """ Prevent a silenced player from using `say` or `say_team`. """
        if player.steam_id not in self.silenced:
            return

        lowered = cmd.lower().strip()
        if lowered.startswith("say ") or lowered.startswith("say_team "):
            expires, score, reason = self.silenced[player.steam_id]
            if time.time() < score:
                if reason:
                    player.tell(f"You have been silenced on this server until ^6{expires}^7: {reason}")
                else:
                    player.tell(f"You have been silenced on this server until ^6{expires}^7.")
            else:
                self._release(player.steam_id, player)

                @minqlxtended.next_frame
                def repeat_command():
                    # Replay what the player typed. The lower-cased copy above only
                    # identifies the command.
                    minqlxtended.client_command(player.id, cmd)

                repeat_command()

            return minqlxtended.Return.STOP_ALL

    @minqlxtended.hook("userinfo", priority=minqlxtended.Priority.HIGH)
    def handle_userinfo(self, player, changed, infostring):
        """ Prevent a silenced player from changing their name. """
        if player.steam_id not in self.silenced:
            return
        elif "name" in changed:
            # removesuffix, since rstrip("^7") strips *any* trailing '^' and
            # '7' characters, so it would hand back "Agent4" for "Agent47".
            changed["name"] = player.name.removesuffix("^7")
            return changed

    @minqlxtended.hook("vote_called", priority=minqlxtended.Priority.HIGH)
    def handle_vote_called(self, caller, vote, args):
        """ Prevent a silenced player from calling a vote. """
        if caller.steam_id not in self.silenced:
            return

        expires, score, reason = self.silenced[caller.steam_id]
        if time.time() >= score:
            # The silence has run out. Release it and let the vote through.
            self._release(caller.steam_id, caller)
            return

        if reason:
            caller.tell(f"You have been silenced on this server until ^6{expires}^7: {reason}")
        else:
            caller.tell(f"You have been silenced on this server until ^6{expires}^7.")

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("silence", permission=4, usage="<id> <length> seconds|minutes|hours|days|... [reason]")
    def cmd_silence(self, player, msg, channel):
        """ Mutes a player temporarily. A very long period works for all intents and purposes as a permanent mute, so there's no separate command for that. """
        if len(msg) < 4:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, _name, target_player = resolved

        if target_player:
            name = target_player.name
        else:
            name = ident

        if self.db.has_permission(ident, 2):
            channel.reply(f"^6{name}^7 has permission level 2 or more and cannot be silenced.")
            return

        if len(msg) > 4:
            reason = " ".join(msg[4:])
        else:
            reason = ""

        r = LENGTH_REGEX.match(" ".join(msg[2:4]).lower())
        # An unparseable length ("!silence 3 ten minutes") is a usage error, the same
        # as ban.py treats it.
        if not r:
            return minqlxtended.Return.USAGE

        number = float(r.group("number"))
        if number <= 0:
            channel.reply("The silence length must be greater than zero.")
            return
        scale = r.group("scale").rstrip("s")
        td = None

        if scale == "second":
            td = datetime.timedelta(seconds=number)
        elif scale == "minute":
            td = datetime.timedelta(minutes=number)
        elif scale == "hour":
            td = datetime.timedelta(hours=number)
        elif scale == "day":
            td = datetime.timedelta(days=number)
        elif scale == "week":
            td = datetime.timedelta(weeks=number)
        elif scale == "month":
            td = datetime.timedelta(days=number * 30)
        elif scale == "year":
            td = datetime.timedelta(weeks=number * 52)

        if td is None:
            return minqlxtended.Return.USAGE

        now = datetime.datetime.now().strftime(TIME_FORMAT)
        # The zset score is the expiry. `expires` is the same instant rendered for
        # anyone reading the hash by hand.
        score = time.time() + td.total_seconds()
        expires = datetime.datetime.fromtimestamp(score).strftime(TIME_FORMAT)
        base_key = f"{PLAYER_KEY.format(ident)}:silences"
        silence_id = self.db.zcard(base_key)
        db = self.db.pipeline()
        db.zadd(base_key, {silence_id: score})
        silence = {
            "expires": expires,
            "reason": reason,
            "issued": now,
            "issued_by": player.steam_id
        }
        # hset(mapping=...), matching ban.py: hmset is deprecated in redis-py >= 3.5.
        db.hset(f"{base_key}:{silence_id}", mapping=silence)
        db.execute()

        if target_player:
            self.silenced[ident] = (expires, score, reason)
            try:
                target_player.mute()
            except ValueError:
                pass
        channel.reply(f"^6{name}^7 has been silenced. Silence expires on ^6{expires}^7.")

    @minqlxtended.command("unsilence", permission=4, usage="<id>")
    def cmd_unsilence(self, player, msg, channel):
        """ Unsilences a player if silenced. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, _name, target_player = resolved

        if target_player:
            name = target_player.name
        else:
            name = ident

        base_key = f"{PLAYER_KEY.format(ident)}:silences"
        silences = self.db.zrangebyscore(base_key, time.time(), "+inf", withscores=True)
        if not silences:
            channel.reply(f"^7No active silences on ^6{name}^7 found.")
        else:
            db = self.db.pipeline()
            for silence_id, score in silences:
                db.zincrby(base_key, -score, silence_id)
            db.execute()
            channel.reply(f"^6{name}^7 has been unsilenced.")

        # Unmute either way. A silence that has already lapsed leaves no zset entry
        # behind but can still leave the engine mute flag set.
        self._release(ident, target_player)

    @minqlxtended.command("checksilence", usage="<id>")
    def cmd_checksilence(self, player, msg, channel):
        """ Checks whether a player has been silenced, and if so, why. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, _name, target_player = resolved

        if target_player:
            name = target_player.name
        else:
            name = ident

        # Check manual silences first.
        res = self.is_silenced(ident)
        if res:
            expires, _, reason = res
            if reason:
                channel.reply(f"^6{name}^7 is silenced until ^6{expires}^7 for the following reason: ^6{reason}^7")
            else:
                channel.reply(f"^6{name}^7 is silenced until ^6{expires}^7.")
            return

        channel.reply(f"^6{name}^7 is not silenced.")

    # HELPERS

    def _release(self, steam_id, player=None):
        """ Drops the tracking entry for a silence and clears the engine mute flag. """
        self.silenced.pop(steam_id, None)
        if player is None:
            player = self.player(steam_id)
        if player is None:
            return

        try:
            player.unmute()
        except ValueError:
            pass

    def is_silenced(self, steam_id):
        base_key = f"{PLAYER_KEY.format(steam_id)}:silences"
        silences = self.db.zrangebyscore(base_key, time.time(), "+inf", withscores=True)
        if not silences:
            return None

        silence_id, score = silences[-1]
        longest_silence = self.db.hgetall(f"{base_key}:{silence_id}")
        # hgetall returns {} for a missing key. A detail hash evicted out from under a
        # surviving zset entry counts as no silence. ban.py guards the same way.
        if not longest_silence:
            return None

        # The score is the expiry and zrangebyscore has excluded anything past, so this
        # silence is active. Deriving the display string from it survives a DST shift.
        expires = datetime.datetime.fromtimestamp(score).strftime(TIME_FORMAT)
        return expires, score, longest_silence.get("reason", "")
