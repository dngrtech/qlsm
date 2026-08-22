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

import minqlxtended

class workshop(minqlxtended.Plugin):
    _qlx_workshopReferences = minqlxtended.setting("qlx_workshopReferences", "", type=list)

    @minqlxtended.hook("map")
    def handle_map(self, mapname, factory):
        # An empty cvar parses to [''], so drop the blank entries.
        references = [item for item in self._qlx_workshopReferences if item]
        if not references:
            return

        # Game() raises while CS_SERVERINFO is empty, which self.game turns into None.
        game = self.game
        if game is None:
            return

        game.workshop_items += references
