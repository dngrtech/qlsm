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

# votecommands.py - a minqlxtended plugin to add new /pass and /veto client commands for moderators.

import minqlxtended

class votecommands(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        self._qlx_commandPrefix = self.get_cvar("qlx_commandPrefix")

    @minqlxtended.hook("client_command")
    def handle_client_command(self, player, command):
        parts = command.lower().split()
        if not parts:
            return
        command = parts[0]
        # /yes and /no are the engine's own vote commands, and are left alone. Overloading
        # them left a moderator no way to cast an ordinary vote without forcing it.
        if command not in ("pass", "veto"):
            return

        self.do_vote(player, command == "pass")
        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command(("pass", "veto"), permission=3, priority=minqlxtended.Priority.HIGHEST)
    def cmd_force_vote(self, player, msg, channel):
        """ Forces the current vote. """
        # Only registered as ("pass", "veto"), so anything that isn't a pass is a veto.
        command = msg[0].lower().removeprefix(self._qlx_commandPrefix)

        self.do_vote(player, command == "pass")
        return minqlxtended.Return.STOP_ALL

    def do_vote(self, player, action):
        if not self.is_vote_active():
            player.tell(f"There is no current vote to ^6{'pass' if action else 'veto'}^7.")
            return minqlxtended.Return.STOP_ALL

        if not self.db.has_permission(player.steam_id, 3):
            player.tell(f"You don't have permission to ^6{'pass' if action else 'veto'}^7 a vote.")
            return minqlxtended.Return.STOP_ALL

        if not minqlxtended.force_vote(action):
            # Refused, the vote having gone away between the check above and here, or the
            # match having ended and voteTime now belonging to the map vote.
            player.tell(f"There is no current vote to ^6{'pass' if action else 'veto'}^7.")
            return minqlxtended.Return.STOP_ALL

        word = "^2passed" if action else "^1vetoed"
        self.msg(f"{player.name}^7 {word}^7 the vote.")
