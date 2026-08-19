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

"""
A plugin that allows a race server to start and keep a game going even without having
a minimum of two players on a server, like you usually do.
"""

import minqlxtended

class solorace(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        # What the server config asked for. Race turns warmup off; every other gametype,
        # and unloading this plugin, gets this value back.
        self._g_doWarmup = self.get_cvar("g_doWarmup") or "1"

    def unload(self):
        self.set_cvar("g_doWarmup", self._g_doWarmup)

    @minqlxtended.hook("team_switch")
    def handle_team_switch(self, player, old_team, new_team):
        game = self.game
        if game is None:
            return  # mid map change; Plugin.game hands back None rather than raising

        if (game.type_short == minqlxtended.Gametype.RACE) and (old_team == minqlxtended.Team.FREE) and (game.state == minqlxtended.GameState.IN_PROGRESS) and (not self.teams()["free"]):
            minqlxtended.console_command("map_restart")

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        # Race only. FFA and the other non-team gametypes also put players on "free",
        # and restarting the map when one of them leaves is wrong.
        game = self.game
        if game is None or game.type_short != minqlxtended.Gametype.RACE:
            return

        if (len(self.teams()["free"]) == 1) and (player.team == minqlxtended.Team.FREE):
            minqlxtended.console_command("map_restart")

    @minqlxtended.hook("new_game")
    def handle_new_game(self):
        game = self.game
        if game is None:
            return

        if game.type_short == minqlxtended.Gametype.RACE:
            self.set_cvar("g_doWarmup", "0")
            game.is_training_map = True
        else:
            self.set_cvar("g_doWarmup", self._g_doWarmup)
