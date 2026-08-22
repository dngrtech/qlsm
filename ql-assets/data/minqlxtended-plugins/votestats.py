# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
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

# votestats.py - a minqlxtended plugin to show who votes yes or no in-game/vote results.
# If you want to re-privatise votes, set the following cvar to 1: qlx_privatiseVotes

import minqlxtended

VOTES_ENABLED_FLAG = "votestats:votes_enabled"

class votestats(minqlxtended.Plugin):
    _qlx_privatiseVotes = minqlxtended.setting("qlx_privatiseVotes", False)

    def __init__(self):
        super().__init__()

        self.has_voted = []

    @minqlxtended.command("votes")
    def cmd_votes(self, player, msg, channel):
        """ Prevents 'x voted y' messages from appearing for the calling player. Use again to re-enable these messages. """
        flag = self.db.get_flag(player, VOTES_ENABLED_FLAG, default=True)
        self.db.set_flag(player, VOTES_ENABLED_FLAG, not flag)
        if flag:
            word = "disabled"
        else:
            word = "enabled"
        player.tell(f"Player votes have been ^4{word}^7.")
        return minqlxtended.Return.STOP_ALL

    @minqlxtended.hook("vote", priority=minqlxtended.Priority.LOWEST)
    def process_vote(self, player, yes):
        if self._qlx_privatiseVotes:
            return

        if player in self.has_voted:
            return

        if yes:
            word = "^2yes"
        else:
            word = "^1no"

        # A `tell` per recipient per vote is N commands, and every voter triggers another
        # N, so 16 players voting is 256. That overruns each client's reliable command
        # queue, which drops the overflow, so send one message to whoever wants it.
        players = self.players()
        enabled = self.db.get_flags(players, VOTES_ENABLED_FLAG, default=True)
        recipients = [p for p in players if enabled[p.steam_id]]
        self.tell_many(recipients, f"{player.name}^7 voted {word}^7.")

        self.has_voted.append(player)

    @minqlxtended.hook("new_game")
    def handle_new_game(self):
        # A vote still running at a map change never reaches vote_ended, so the previous
        # map's voters have to be cleared here too.
        self.has_voted = []

    @minqlxtended.hook("vote_ended", priority=minqlxtended.Priority.LOWEST)
    def handle_vote_ended(self, votes, vote, args, passed):
        self.has_voted = []
        self.msg(f"Vote results: ^2{votes[0]}^7 - ^1{votes[1]}^7.")

        if passed:
            if vote.lower().strip() == "map":
                changingToMapAndMode = args.lower().split()
                if len(changingToMapAndMode) > 1:
                    theMsg = f"The map is changing to ^6{changingToMapAndMode[0]}^7, with new factory ^6{changingToMapAndMode[1]}^7."
                else:
                    theMsg = f"The map is changing to ^6{changingToMapAndMode[0]}^7."

                self.msg(theMsg)
