# Copyright (C) 2025 Doomsday
# This is an extension plugin for minqlx to list the last maps played with !lm

# You can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.

# You should have received a copy of the GNU General Public License
# along with minqlx. If not, see <http://www.gnu.org/licenses/>.

# Created by Doomsday
# https://github.com/D00MSDAYDEVICE
# https://www.youtube.com/@HIT-CLIPS

# You are free to modify this plugin.
# This plugin comes with no warranty or guarantee.

import minqlx
import time

class lastmaps(minqlx.Plugin):
    def __init__(self):
        self.version = "1.2.1"  # Set your version number here
        self.add_hook("game_end", self.on_game_end)
        self.add_hook("map", self.on_map_load)
        self.add_command("lastmaps", self.cmd_lastmaps)
        self.add_command("lm", self.cmd_lastmaps)
        self.add_command("lmv", self.cmd_version, 3)    # New command for version display

        self.map_history = []
        self.current_map = None
        self.map_start_time = None

    def cmd_version(self, player, msg, channel):
        player.tell("^3Lastmaps Plugin Version:^7 {}".format(self.version))
    
    def on_map_load(self, mapname, factory):
        self.current_map = mapname
        self.map_start_time = time.time()

        # Delay 5 minutes, then add current map (if not already added by game_end)
        minqlx.delay(300)(self.add_current_map)

    def on_game_end(self, data):
        self.add_current_map()

    def add_current_map(self):
        if not self.current_map:
            return

        if self.map_history and self.map_history[-1] == self.current_map:
            return  # Already added

        self.map_history.append(self.current_map)

        if len(self.map_history) > 5:
            self.map_history.pop(0)

        self.msg("^6Last Maps Played:^7 {}".format(", ".join(self.map_history)))

    def cmd_lastmaps(self, player, msg, channel):
        if not self.map_history:
            player.tell("^1No maps have been tracked since server restart.")
            return

        self.msg("^6Last Maps Played:^7 {}".format(", ".join(self.map_history)))

