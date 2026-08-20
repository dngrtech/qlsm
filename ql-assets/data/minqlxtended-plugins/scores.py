# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2026 Thomas Jones <me@thomasjones.id.au>

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

from time import time

import minqlxtended

# How long a player must wait between scoreboard refreshes.
BACKOFF_SECONDS = 2.0

TEAM_COLOURS = {
    "spectator": "^7",
    "red": "^1",
    "blue": "^4",
    "free": "^6",
}

class scores(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        self.backoff_players = {}

    @minqlxtended.hook("new_game", priority=minqlxtended.Priority.LOWEST)
    def handle_new_game(self):
        self.backoff_players = {player.steam_id: 0 for player in self.players()}

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        # Otherwise every player who has ever pressed TAB stays in the dict for the
        # life of the process.
        self.backoff_players.pop(player.steam_id, None)

    @minqlxtended.hook("client_command", priority=minqlxtended.Priority.LOWEST)
    def handle_client_command(self, player, cmd):
        if cmd.lower().strip() != "score": # the scoreboard key, usually TAB
            return

        now = time()
        last = self.backoff_players.get(player.steam_id)
        if last is not None and (now - last) < BACKOFF_SECONDS:
            return # still inside the backoff window

        self.backoff_players[player.steam_id] = now

        # The scoreboard title, as it currently reads.
        message = [f"{minqlxtended.configstring(minqlxtended.CS_MESSAGE)}^7"]

        team = player.team
        team_colour = TEAM_COLOURS[team]

        # Every attribute on PlayerStats is a fresh engine call through the property,
        # so take one snapshot rather than five.
        stats = player.stats

        # Add the player's statistics if they're not a spectator
        if team != minqlxtended.Team.SPECTATOR:
            damage = stats.damage_dealt
            damage_quantified = str(damage) if damage < 1000 else f"{damage/1000:.1f}k" if damage < 10000 else f"{damage//1000}k"
            message.append(f"^7S: {team_colour}{stats.score}^7, K/D: {team_colour}{stats.kills}^7/{team_colour}{stats.deaths}^7, D: {team_colour}{damage_quantified}^7, {team_colour}{stats.ping}^7ms")
        else:
            message.append(f"^7Spectating | Ping: {team_colour}{stats.ping}^7ms")

        self.update_scoreboard_title(player, " - ".join(message))

    def update_scoreboard_title(self, player, message):
        # Use the helper rather than a hand-built `cs` command: it chunks into bcs0/1/2
        # and terminates properly. The title embeds CS_MESSAGE, which branding fills from
        # an admin-set cvar, so it can be long and full of quotes.
        self.send_configstring_to(player.id, minqlxtended.CS_MESSAGE, message)
