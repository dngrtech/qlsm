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

import minqlxtended

SUPPORTED_GAMETYPES = (
    minqlxtended.Gametype.ATTACK_AND_DEFEND, minqlxtended.Gametype.CA,
    minqlxtended.Gametype.CTF, minqlxtended.Gametype.DOMINATION,
    minqlxtended.Gametype.FREEZE_TAG, minqlxtended.Gametype.TDM,
)

class last_in(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        self.last_players_in = {"red": None, "blue": None}
        # Keyed by steam_id, since a denied switch attempt never produces a team_switch.
        # Pruned on disconnect, so it stays bounded to the connected players.
        self.transitioning_players = set()

    @minqlxtended.hook("team_switch", priority=minqlxtended.Priority.LOW)
    @minqlxtended.next_frame
    def handle_team_switch(self, player, old_team, new_team):
        if player.steam_id in self.transitioning_players:
            self.transitioning_players.discard(player.steam_id)
            self.last_players_in[new_team] = player

    @minqlxtended.hook("team_switch_attempt", priority=minqlxtended.Priority.HIGH)
    def handle_team_switch_attempt(self, player, old_team, new_team, target):
        if not new_team.lower().startswith("s"):
            self.transitioning_players.add(player.steam_id)

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        self.transitioning_players.discard(player.steam_id)

    @minqlxtended.command("lastin", client_cmd_perm=0)
    def cmd_last_in(self, player, msg, channel):
        """ Display the last players who joined the blue/red team. """
        if self.game.type_short not in SUPPORTED_GAMETYPES:
            channel.reply(f"The ^6{self.game.type_short.upper()}^7 game type is not supported by this command.")
            return

        red_msg, red_id = self.get_player_string(self.last_players_in["red"], "red")
        blue_msg, blue_id = self.get_player_string(self.last_players_in["blue"], "blue")

        if self.db.has_permission(player, 2):  # display more information (player ID, etc)
            channel.reply(f"Red: (^6{red_id}^7) ^1{red_msg}^7 ^6|^7 Blue: (^6{blue_id}^7) ^4{blue_msg}^7")
        else:
            channel.reply(f"Red: ^1{red_msg}^7 ^6|^7 Blue: ^4{blue_msg}^7")

    @minqlxtended.command(("c", "count"), client_cmd_perm=0)
    def cmd_count(self, player, msg, channel):
        """Lists the count of players on each team. Useful for when the scoreboard is exceeded."""
        teams = self.teams()
        is_team_game = self.get_cvar("g_gametype", int) >= 3
        if is_team_game:
            channel.reply(f"^1RED TEAM: {len(teams['red'])} ^6|^4 BLUE TEAM: {len(teams['blue'])} ^6|^7 SPECTATORS: {len(teams['spectator'])}")
        else:
            channel.reply(f"^4IN-GAME: {len(teams['free'])} ^6|^7 SPECTATORS: {len(teams['spectator'])}")

    def get_player_string(self, player, team):
        if player is None:
            return "Not recorded yet.", "No ID"

        try:
            player.update()
        except minqlxtended.NonexistentPlayerError:
            return f"{player.clean_name} ^3(disconnected)", "No ID"

        if (not player.valid):
            return f"{player.clean_name} ^3(disconnected)", "No ID"

        if (player.team != team):
            return f"{player.clean_name} ^3(left team)", player.id

        return player.clean_name, player.id
