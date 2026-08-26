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
from os.path import basename

MOTD_SET_KEY = "minqlx:motd"

class motd(minqlxtended.Plugin):
    # A sound of "0" disables the welcome sound.
    _qlx_motdSound = minqlxtended.setting("qlx_motdSound", "sound/vo/crash_new/37b_07_alt.wav")
    _qlx_motdHeader = minqlxtended.setting("qlx_motdHeader", "^6======= ^7Message of the Day ^6=======^7")

    def __init__(self):
        super().__init__()

        # homepath doesn't change runtime, so we can just save it for the sake of efficiency.
        self.home = basename(self.get_cvar("fs_homepath"))
        self.motd_key = f"{MOTD_SET_KEY}:{self.home}"

        # Add this server to the MOTD set.
        self.db.sadd(MOTD_SET_KEY, self.home)

    @minqlxtended.hook("player_loaded", priority=minqlxtended.Priority.LOWEST)
    @minqlxtended.delay(2)
    def handle_player_loaded(self, player):
        """Send the message of the day to the player in a tell.

        This should be set to lowest priority so that we don't execute anything if "ban" or
        a similar plugin determines the player should be kicked.
        """
        try:
            motd = self.db[self.motd_key]
        except KeyError:
            return

        welcome_sound = self._qlx_motdSound
        if welcome_sound == "0":
            welcome_sound = ""

        if welcome_sound and self.db.get_flag(player, "essentials:sounds_enabled", default=True):
            self.play_sound(welcome_sound, player)
        self.send_motd(player, motd)

    @minqlxtended.command(("setmotd", "newmotd"), permission=4, usage="<motd>")
    def cmd_setmotd(self, player, msg, channel):
        """ Set the message of the day for this server to the one specified. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        self.db.sadd(MOTD_SET_KEY, self.home)
        self.db[self.motd_key] = " ".join(msg[1:])
        player.tell("The MOTD has been set.")
        return minqlxtended.Return.STOP_EVENT

    @minqlxtended.command(("setmotdall", "newmotdall"), permission=4, usage="<motd>")
    def cmd_setmotdall(self, player, msg, channel):
        """ Set the message of the day for all servers to the one specified. """
        # A bare "!setmotdall" would otherwise join an empty list and wipe every server's
        # MOTD at once.
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        motds = self.db.smembers(MOTD_SET_KEY)
        db = self.db.pipeline()
        for path in motds:
            motd_key = f"{MOTD_SET_KEY}:{path}"
            db.set(motd_key, " ".join(msg[1:]))
        db.execute()
        player.tell("All MOTDs have been set.")
        return minqlxtended.Return.STOP_EVENT

    @minqlxtended.command(("getmotd", "motd"))
    def cmd_getmotd(self, player, msg, channel):
        """ Shows the current message of the day for this server. """
        if self.motd_key in self.db:
            self.send_motd(player, self.db[self.motd_key])
        else:
            player.tell("No MOTD has been set.")
        return minqlxtended.Return.STOP_EVENT

    @minqlxtended.command(("clearmotd", "removemotd", "remmmotd"), permission=4)
    def cmd_clearmotd(self, player, msg, channel):
        """ Clears the message of the day on this server. """
        if self.motd_key in self.db:
            del self.db[self.motd_key]
            player.tell("The MOTD has been cleared.")
        else:
            player.tell("No MOTD has been set.")
        return minqlxtended.Return.STOP_EVENT

    @minqlxtended.command(("clearmotdall", "removemotdall", "remmmotdall"), permission=4)
    def cmd_clearmotdall(self, player, msg, channel):
        """ Clears the message of the day on all servers. """
        motds = [f"{MOTD_SET_KEY}:{m}" for m in self.db.smembers(MOTD_SET_KEY)]
        if motds:
            self.db.delete(*motds)
        player.tell("All MOTDs have been cleared.")
        return minqlxtended.Return.STOP_EVENT

    @minqlxtended.command("addmotd", permission=4, usage="<more_motd>")
    def cmd_addmotd(self, player, msg, channel):
        """ Appends the specified text to the existing message of the day on this server. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        motd = self.db.get(self.motd_key)
        if not motd:
            self.db[self.motd_key] = " ".join(msg[1:])
            player.tell("No MOTD was set, so a new one was made.")
        else:
            leading_space = "" if len(motd) > 2 and motd[-2:] == "\\n" else " "
            self.db[self.motd_key] = motd + leading_space + " ".join(msg[1:])
            player.tell("The MOTD has been updated.")

        return minqlxtended.Return.STOP_EVENT

    @minqlxtended.command("addmotdall", permission=4, usage="<more_motd>")
    def cmd_addmotdall(self, player, msg, channel):
        """ Appends the specified text to the existing message of the day on all servers. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        # One mget to read and one pipeline to write, matching cmd_setmotdall above.
        addition = " ".join(msg[1:])
        keys = [f"{MOTD_SET_KEY}:{path}" for path in self.db.smembers(MOTD_SET_KEY)]

        db = self.db.pipeline()
        for motd_key, motd in zip(keys, self.db.mget(keys) if keys else []):
            if not motd:
                db.set(motd_key, addition)
            else:
                leading_space = "" if len(motd) > 2 and motd[-2:] == "\\n" else " "
                db.set(motd_key, motd + leading_space + addition)
        db.execute()

        player.tell("Added to all MOTDs.")
        return minqlxtended.Return.STOP_EVENT

    def send_motd(self, player, motd):
        # One reliable command rather than one per line. This fires two seconds after
        # player_loaded, while the client is still draining gamestate, and a real MOTD is
        # easily 15 lines out of a 64-slot ring.
        self.reply_lines(player, self._qlx_motdHeader.split("\\n") + motd.split("\\n"))
