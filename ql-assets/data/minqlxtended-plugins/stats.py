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

# stats.py - a plugin for minqlxtended which provides statistics per-round on player gameplay

import minqlxtended

class stats(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        self.old_damage = {}

    @minqlxtended.hook("round_end")
    def handle_round_end(self, round_number, winning_team, time):
        # `time` is how long this round took, in milliseconds.
        time_elapsed = time // 1000

        prefix = f"^3DMG: ^5Round #{round_number}: {time_elapsed} secs.^7"

        try:
            best_player, best_damage = self.getPlayerWithHighestDamage(round_number)
            # A round where nobody's damage increased leaves no best player at all.
            if best_player is not None:
                if best_player.valid:
                    colour = "^1" if best_player.team == minqlxtended.Team.RED else "^4"
                    name = best_player.clean_name
                else:
                    colour, name = "^3", "(disconnected)"
                self.msg(f"{prefix} {colour}{name}^5 leads with {best_damage} damage dealt this round.")
                return
        except (minqlxtended.NonexistentPlayerError, AttributeError, KeyError, TypeError, ValueError):
            pass

        self.msg(f"{prefix} ^3No damage leader recorded this round.")

    @minqlxtended.hook("new_game")
    def handle_new_game(self):
        self.old_damage = {}

    def getPlayerWithHighestDamage(self, round_number):
        teams = self.teams()
        players = (teams["red"] + teams["blue"])
        best_player = None
        best_damage = 0
        # Rebuilt from the current roster each round, so departed players fall out.
        damage_this_round = {}
        for player in players:
            # Every attribute on PlayerStats is a fresh engine call through the
            # property, so take one snapshot per player.
            damage = player.stats.damage_dealt
            # Keyed by steam id, since the engine reuses client ids and the slot's next
            # occupant would inherit the previous player's damage total.
            damage_this_round[player.steam_id] = damage
            try:
                last_damage = self.old_damage[player.steam_id]
            except KeyError:
                last_damage = damage
            if round_number != 1:
                delta = (damage - last_damage)
                if (damage > last_damage):
                    if (delta > best_damage):
                        best_player = player
                        best_damage = delta
            else:
                if (damage > best_damage):
                    best_player = player
                    best_damage = damage

        self.old_damage = damage_this_round

        return (best_player, best_damage)
