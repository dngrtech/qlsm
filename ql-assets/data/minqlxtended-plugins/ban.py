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

# Manual bans only. Leaver tracking lives in leaverban.py, which owns the
# `leaves`/`games_left`/`games_completed` keys, the qlx_leaverBan* cvars and the `forgive`,
# `gamestats` and `tracked` commands. CommandInvoker keys on (name, handler), so a name
# registered here too would run twice per invocation.

import minqlxtended
import datetime
import time
import re

LENGTH_REGEX = re.compile(r"(?P<number>[0-9]+) (?P<scale>seconds?|minutes?|hours?|days?|weeks?|months?|years?)")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PLAYER_KEY = "minqlx:players:{}"

# Scale name -> how to turn a count of them into a timedelta.
_SCALES = {
    "second": lambda n: datetime.timedelta(seconds=n),
    "minute": lambda n: datetime.timedelta(minutes=n),
    "hour": lambda n: datetime.timedelta(hours=n),
    "day": lambda n: datetime.timedelta(days=n),
    "week": lambda n: datetime.timedelta(weeks=n),
    "month": lambda n: datetime.timedelta(days=n * 30),
    "year": lambda n: datetime.timedelta(weeks=n * 52),
}

class ban(minqlxtended.Plugin):
    @minqlxtended.hook("player_connect", priority=minqlxtended.Priority.HIGH)
    def handle_player_connect(self, player, is_bot):
        # Use the event's own flag here. This fires before the game module sets
        # ServerFlag.BOT, so player.is_bot would report every bot as human.
        if is_bot:
            return

        # Check if a player has been banned manually.
        banned = self.is_banned(player.steam_id)
        if banned:
            expires, reason = banned
            if reason:
                return f"You are banned until {expires}: {reason}"
            else:
                return f"You are banned until {expires}."

    @minqlxtended.command("ban", permission=4, usage="<id> <length> seconds|minutes|hours|days|... [reason]")
    def cmd_ban(self, player, msg, channel):
        """Bans a player temporarily. A very long period works for all intents and
        purposes as a permanent ban, so there's no separate command for that.

        Example #1: !ban <Purger's ID> 1 day Hugely rapacious!

        Example #2: !ban <SyncError's ID> 50 years"""
        if len(msg) < 4:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, name, _target = resolved

        # !ban is itself a permission-4 command, so the guard sits at its own level:
        # anyone who can issue it is out of reach of it. silence.py guards the same way.
        if self.db.has_permission(ident, 4):
            channel.reply(f"^6{name}^7 has permission level 4 or more and cannot be banned.")
            return

        if len(msg) > 4:
            reason = " ".join(msg[4:])
        else:
            reason = ""

        r = LENGTH_REGEX.match(" ".join(msg[2:4]).lower())
        if not r:
            return minqlxtended.Return.USAGE

        number = float(r.group("number"))
        if number <= 0:
            channel.reply("The ban length must be greater than zero.")
            return

        td = _SCALES[r.group("scale").rstrip("s")](number)

        now = datetime.datetime.now()
        # The zset score is the expiry. `expires` is the same instant rendered for
        # anyone reading the hash by hand.
        score = time.time() + td.total_seconds()
        expires = datetime.datetime.fromtimestamp(score).strftime(TIME_FORMAT)
        base_key = f"{PLAYER_KEY.format(ident)}:bans"
        ban_id = self.db.zcard(base_key)
        db = self.db.pipeline()
        db.zadd(base_key, {ban_id: score})
        ban = {
            "expires": expires,
            "reason": reason,
            "issued": now.strftime(TIME_FORMAT),
            "issued_by": player.steam_id,
        }
        db.hset(f"{base_key}:{ban_id}", mapping=ban)
        db.execute()

        # kick() raises only when the target isn't connected, so the confirmation sits
        # after the try.
        try:
            self.game.kick(ident, f"has been banned until ^6{expires}^7: {reason}")
        except ValueError:
            pass  # not connected; the ban is recorded and applies on their next connect

        channel.reply(f"^6{name}^7 has been banned. Ban expires on ^6{expires}^7.")

    @minqlxtended.command("unban", permission=4, usage="<id>")
    def cmd_unban(self, player, msg, channel):
        """ Unbans the specified player if banned. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, name, _target = resolved

        base_key = f"{PLAYER_KEY.format(ident)}:bans"
        bans = self.db.zrangebyscore(base_key, time.time(), "+inf", withscores=True)
        if not bans:
            channel.reply(f"No active bans on ^6{name}^7 found.")
        else:
            db = self.db.pipeline()
            for ban_id, score in bans:
                db.zincrby(base_key, -score, ban_id)
            db.execute()
            channel.reply(f"^6{name}^7 has been unbanned.")

    @minqlxtended.command("checkban", usage="<id>")
    def cmd_checkban(self, player, msg, channel):
        """ Checks whether a player has been banned, and if so, the reason (if originally specified.) """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, name, _target = resolved

        # Check manual bans first.
        manual_ban = self.is_banned(ident)
        if manual_ban:
            expires, reason = manual_ban
            if reason:
                channel.reply(f"^6{name}^7 is manually banned until ^6{expires}^7 for the following reason: ^6{reason}")
            else:
                channel.reply(f"^6{name}^7 is manually banned until ^6{expires}^7.")
            return

        # Leaver bans belong to leaverban.py. Ask it at the point of use, so load
        # order doesn't matter and a reload is picked up.
        leaverban = self.plugin("leaverban")
        if leaverban is not None and leaverban.describe_leaver_status(ident, name, channel):
            return

        channel.reply(f"^6{name}^7 is not banned.")

    # HELPERS

    def is_banned(self, steam_id):
        base_key = f"{PLAYER_KEY.format(steam_id)}:bans"
        bans = self.db.zrangebyscore(base_key, time.time(), "+inf", withscores=True)
        if not bans:
            return None

        ban_id, score = bans[-1]
        longest_ban = self.db.hgetall(f"{base_key}:{ban_id}")
        if not longest_ban:
            return None

        # The score is the expiry and zrangebyscore has excluded anything past, so this ban
        # is active. Deriving the display string from it survives a DST or timezone shift.
        expires = datetime.datetime.fromtimestamp(score).strftime(TIME_FORMAT)
        return expires, longest_ban.get("reason", "")
