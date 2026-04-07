# Edited by Doomsday April 2025
# Extended motd to multiple lines to overcome character length and format limitations/ease of use

# !setmotd <line> <message>	Set specific line of MOTD (1-10).
# !addmotd <message>        Adds a new line to the next free slot.
# !clearmotd                Clears all MOTD lines.
# !reloadmotd 				reload MOTD lines from motd.cfg in /baseq3 anytime
# Use set qlx_motd1, set qlx_motd2, etc to set from config file.
# Add /exec motd.cfg to config.cfg or simply !reloadmotd
# Config settings will not override existing motd (use !clearmotd and restart server).

# minqlx - A Quake Live server administrator bot.
# Copyright (C) 2015 Mino <mino@minomino.org>
 
# This file is part of minqlx.

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

import minqlx
import minqlx.database

MOTD_SET_KEY = "minqlx:motd"

class motd(minqlx.Plugin):
    database = minqlx.database.Redis

    def __init__(self):
        super().__init__()
        self.add_hook("player_loaded", self.handle_player_loaded, priority=minqlx.PRI_LOWEST)
        self.add_command(("setmotd", "newmotd"), self.cmd_setmotd, 4, usage="<motd>")
        self.add_command("addmotd", self.cmd_addmotd, 4, usage="<motd line>")
        self.add_command("clearmotd", self.cmd_clearmotd, 4)
        self.add_command("motd", self.cmd_getmotd)
        self.add_command("reloadmotd", self.cmd_reloadmotd, 4)

        self.home = self.get_cvar("fs_homepath")
        self.motd_key = MOTD_SET_KEY + ":{}".format(self.home)

        self.db.sadd(MOTD_SET_KEY, self.home)

        self.set_cvar_once("qlx_motdSound", "sound/vo/crash_new/37b_07_alt.wav")
        self.set_cvar_once("qlx_motdHeader", "^6======= ^7Message of the Day ^6=======^7")

        # Load MOTD from config if Redis is empty
        if self.motd_key not in self.db:
            self.load_motd_from_config()

    @minqlx.delay(2)
    def handle_player_loaded(self, player):
        try:
            motd = self.db[self.motd_key]
        except KeyError:
            return

        sound = self.get_cvar("qlx_motdSound")
        if sound and self.db.get_flag(player, "essentials:sounds_enabled", default=True):
            self.play_sound(sound, player)

        self.send_motd(player, motd)

    def cmd_getmotd(self, player, msg, channel):
        if self.motd_key in self.db:
            self.send_motd(player, self.db[self.motd_key])
        else:
            player.tell("No MOTD has been set.")
        return minqlx.RET_STOP_EVENT

    def cmd_setmotd(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE

        self.db[self.motd_key] = " ".join(msg[1:])
        player.tell("MOTD has been set.")
        return minqlx.RET_STOP_EVENT

    def cmd_addmotd(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE

        motd = self.db.get(self.motd_key, "")
        new_line = " ".join(msg[1:])
        updated = motd + "\\n" + new_line if motd else new_line
        self.db[self.motd_key] = updated
        player.tell("Line added to MOTD.")
        return minqlx.RET_STOP_EVENT

    def cmd_clearmotd(self, player, msg, channel):
        del self.db[self.motd_key]
        player.tell("MOTD has been cleared.")
        return minqlx.RET_STOP_EVENT

    def cmd_reloadmotd(self, player, msg, channel):
        self.load_motd_from_config()
        player.tell("MOTD has been reloaded from config and applied.")
        return minqlx.RET_STOP_EVENT

    def load_motd_from_config(self):
        lines = []
        for i in range(1, 11):
            line = self.get_cvar(f"qlx_motd{i}")
            if line:
                lines.append(line)

        if lines:
            self.db[self.motd_key] = "\\n".join(lines)

    def send_motd(self, player, motd):
        for line in self.get_cvar("qlx_motdHeader").split("\\n"):
            player.tell(line)
        for line in motd.split("\\n"):
            player.tell(line)