# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2016 mattiZed (github) aka mattiZed (ql)
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

# pummel.py - a plugin for minqlxtended to track and report on player pummels.

import minqlxtended

# DB related
PLAYER_KEY = "minqlx:players:{}"

class pummel(minqlxtended.Plugin):
    @minqlxtended.hook("kill")
    def handle_kill(self, victim, killer, mod):
        game = self.game
        if game is None:
            return  # mid map change; Plugin.game hands back None rather than raising

        if mod == minqlxtended.MeansOfDeath.GAUNTLET and game.state == minqlxtended.GameState.IN_PROGRESS:
            if (killer.is_bot or victim.is_bot):
                return # ignore bot related action.

            self.play_sound("sound/vo_evil/humiliation1")

            @minqlxtended.thread
            def f(self, victim, killer):
                self.db.sadd(f"{PLAYER_KEY.format(killer.steam_id)}:pummeled", str(victim.steam_id))
                # incr hands back the new counter, so there's no second round-trip.
                killer_score = self.db.incr(f"{PLAYER_KEY.format(killer.steam_id)}:pummeled:{str(victim.steam_id)}")

                # A counter that doesn't exist yet comes back as None, so read it as 0.
                victim_score = self.db.get(f"{PLAYER_KEY.format(victim.steam_id)}:pummeled:{str(killer.steam_id)}") or 0

                self.msg(f"^1PUMMEL!^7 {killer.name} ^1{killer_score}^7:^1{victim_score}^7 {victim.name}")
            f(self, victim, killer)

    @minqlxtended.command("pummel")
    def cmd_pummel(self, player, msg, channel):
        """ Shows the calling player all the players they've pummeled who are currently connected to this server. """
        pummels = self.db.smembers(f"{PLAYER_KEY.format(player.steam_id)}:pummeled")
        teams = self.teams()
        players = teams["spectator"] + teams["red"] + teams["blue"] + teams["free"]

        # Match first, then fetch every counter in one mget. self.db[...] raises KeyError
        # on a counter that isn't there, where mget yields None.
        matched = [pl for pl in players if str(pl.steam_id) in pummels]

        msg = ""
        if matched:
            keys = [f"{PLAYER_KEY.format(player.steam_id)}:pummeled:{pl.steam_id}" for pl in matched]
            for pl, count in zip(matched, self.db.mget(keys)):
                msg += pl.name + ": ^1" + (count or "0") + "^7 "

        if msg == "":
            self.msg(f"{player}^7 has not pummeled anybody on this server.")
        else:
            self.msg(f"Pummel stats for {player}^7:")
            self.msg(msg)
