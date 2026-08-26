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

# branding.py - a plugin for minqlxtended to brand your server.

"""
Branding.py is a minqlx plugin that permits you to personalise your server with your own information.
Simply put the plugin in the 'minqlx-plugins' folder, !load the plugin, and set these cvars:

    qlx_serverBrandName                  - Where the map name usually appears, the text set in this cvar will appear instead.
    qlx_serverBrandTopField              - Where the map author credit (line 1) appears, the text set in this cvar will appear after the credit.
    qlx_serverBrandBottomField           - Where the map author credit (line 2) appears, the text set in this cvar will appear after the credit.

    qlx_connectMessage                   - When the player is at the awaiting challenge screen when they first connect to the server, text will appear here.
    qlx_loadedMessage                    - When the player gets to the menu after connecting, and clicks Join or Spectate, they'll get centre print from this cvar.
    qlx_countdownMessage                 - When the countdown begins, this text will appear mid-screen. (like the qlx_loadedMessage does)
    qlx_endOfGameMessage                 - When the game finishes, it'll put the text in this cvar in the text box on the left.

    qlx_brandingPrependMapName           - This cvar will put the map name before your qlx_serverBrandName.                     Default: 0
    qlx_brandingAppendGameType           - Will add the game type after your qlx_serverBrandName.                               Default: 0
    qlx_rainbowBrandName                 - Make the entire map name (qlx_serverBrandName) appear in rainbow colouring.          Default: 0

Once set, change maps, and you'll see the map loading screen is changed.
"""

import minqlxtended

CS_MESSAGE = 3
CS_AUTHOR = 678
CS_AUTHOR2 = 679

class branding(minqlxtended.Plugin):
    _qlx_serverBrandName = minqlxtended.setting("qlx_serverBrandName", "")
    _qlx_serverBrandTopField = minqlxtended.setting("qlx_serverBrandTopField", "")
    _qlx_serverBrandBottomField = minqlxtended.setting("qlx_serverBrandBottomField", "")
    _qlx_connectMessage = minqlxtended.setting("qlx_connectMessage", "")
    _qlx_loadedMessage = minqlxtended.setting("qlx_loadedMessage", "")
    _qlx_countdownMessage = minqlxtended.setting("qlx_countdownMessage", "")
    _qlx_endOfGameMessage = minqlxtended.setting("qlx_endOfGameMessage", "")
    _qlx_brandingPrependMapName = minqlxtended.setting("qlx_brandingPrependMapName", False)
    _qlx_brandingAppendGameType = minqlxtended.setting("qlx_brandingAppendGameType", False)
    _qlx_rainbowBrandName = minqlxtended.setting("qlx_rainbowBrandName", False)

    def __init__(self):
        super().__init__()

        self.connected_players = set()

    @minqlxtended.hook("new_game")
    def handle_map(self):
        # new_game is dispatched from game-module init, where Game() raises and
        # Plugin.game hands back None.
        game = self.game
        if game is None:
            return

        message = minqlxtended.configstring(CS_MESSAGE)
        author = minqlxtended.configstring(CS_AUTHOR)
        author2 = minqlxtended.configstring(CS_AUTHOR2)

        if self._qlx_serverBrandName and self._qlx_brandingPrependMapName and self._qlx_brandingAppendGameType:
            message = f"{game.map_title} {self._qlx_serverBrandName} {game.type}"
        elif self._qlx_serverBrandName and self._qlx_brandingPrependMapName:
            message = f"{game.map_title} {self._qlx_serverBrandName}"
        elif self._qlx_serverBrandName and self._qlx_brandingAppendGameType:
            message = f"{self._qlx_serverBrandName} {game.type}"
        elif self._qlx_serverBrandName:
            message = self._qlx_serverBrandName

        if self._qlx_serverBrandTopField:
            author = f"{(game.map_subtitle1 + ' - ') if game.map_subtitle1 else ''}{self._qlx_serverBrandTopField}"

        if self._qlx_serverBrandBottomField:
            author2 = f"{(game.map_subtitle2 + ' - ') if game.map_subtitle2 else ''}{self._qlx_serverBrandBottomField}"

        if self._qlx_rainbowBrandName:
            # Thanks Mino for this bit!
            def rotating_colors():
                i = 0
                while True:
                    res = (i % 7) + 1
                    i += 1
                    yield res

            r = rotating_colors()
            res = ""
            for ch in self.clean_text(message):
                res += f"^{next(r)}{ch}"
            message = res

        minqlxtended.set_configstring(CS_MESSAGE, message)
        minqlxtended.set_configstring(CS_AUTHOR, author)
        minqlxtended.set_configstring(CS_AUTHOR2, author2)

    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot):
        if (self._qlx_connectMessage) and (player.steam_id not in self.connected_players):
            self.connected_players.add(player.steam_id)
            return f"{self._qlx_connectMessage}\n^7This server is running ^4branding.py^7. ^2http://github.com/tjone270/Quake-Live^7.\n"

    @minqlxtended.hook("player_loaded")
    def handle_player_loaded(self, player):
        if self._qlx_loadedMessage:
            player.center_print(self._qlx_loadedMessage)

        self.connected_players.discard(player.steam_id)

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        # Prune players who disconnected before they finished loading.
        self.connected_players.discard(player.steam_id)

    @minqlxtended.hook("game_countdown")
    def handle_game_countdown(self):
        if self._qlx_countdownMessage:
            self.center_print(self._qlx_countdownMessage)

    @minqlxtended.hook("game_end")
    def handle_game_end(self, aborted):
        if self._qlx_endOfGameMessage:
            self.msg(self._qlx_endOfGameMessage)
