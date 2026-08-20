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

"""Player-facing views over the installed-map scan, plus a spawn-point visualiser.

!mapinfo and !factories read pk3 data (minqlxtended.map_info / .factories), so their
handlers validate on the game thread and do the disk work on an inner @thread worker.
!spawnvis is pure entity surgery and stays on the game thread throughout.
"""

import minqlxtended

class maptools(minqlxtended.Plugin):
    _qlx_spawnvisDuration = minqlxtended.setting("qlx_spawnvisDuration", 15)
    _qlx_spawnvisItem = minqlxtended.setting("qlx_spawnvisItem", "item_health_small")

    def __init__(self):
        super().__init__()

        self._markers = []  # entity numbers of live !spawnvis markers
        self._marker_classname = ""
        self._cleanup_timer = None

    @minqlxtended.hook("map")
    def handle_map(self, mapname, factory):
        # Entity numbers don't survive a map change. Cancel the pending cleanup with them,
        # or it fires on the new map and frees a later !spawnvis' markers early.
        if self._cleanup_timer is not None:
            self._cleanup_timer.cancel()
            self._cleanup_timer = None
        self._markers.clear()

    # !mapinfo

    @minqlxtended.command("mapinfo", client_cmd_perm=0, usage="[mapname]")
    def cmd_mapinfo(self, player, msg, channel):
        """Shows a map's .arena details: long name, author, declared gametypes, source."""
        if len(msg) > 1:
            target = msg[1]
        elif self.game is not None:
            target = self.game.map
        else:
            return minqlxtended.Return.USAGE

        @minqlxtended.thread
        def work():
            info = minqlxtended.map_info(target)
            if info is None:
                channel.reply(f"Map ^6{target}^7 is not installed on this server.")
                return

            arena = info.arena
            longname = arena.longname if arena and arena.longname else "(no .arena entry)"
            author = arena.author if arena and arena.author else "unknown author"
            workshop = f" ^7[workshop ^6{info.workshop_id}^7]" if info.workshop_id else ""
            if arena and arena.gametypes:
                gametypes = ", ".join(gt.title for gt in arena.gametypes)
            elif arena and arena.type_tokens:
                gametypes = " ".join(arena.type_tokens)
            else:
                gametypes = "undeclared"

            self.reply_lines(channel, [
                f"^6{info.name}^7: {longname} by {author}{workshop}",
                f"Gametypes: ^6{gametypes}^7 - bot support: ^6{'yes' if info.has_aas else 'no'}^7 - "
                f"provided by ^6{len(info.sources)}^7 pk3(s).",
            ])

        work()

    # !factories

    @minqlxtended.command("factories", client_cmd_perm=0)
    def cmd_factories(self, player, msg, channel):
        """Lists every factory the installed .factories files declare."""

        @minqlxtended.thread
        def work():
            found = minqlxtended.factories()
            if not found:
                channel.reply("No .factories files were found on this server.")
                return
            lines = [f"^6{f.id}^7: {f.title} ({f.basegt_raw or '?'})" for f in found]
            lines.append(f"^6{len(found)}^7 factories installed.")
            self.reply_lines(channel, lines)

        work()

    # !spawnvis

    @minqlxtended.command("spawnvis", permission=2)
    def cmd_spawnvis(self, player, msg, channel):
        """Marks every spawn point with a visible item for a few seconds."""
        if self._markers:
            channel.reply("Spawn markers are already up.")
            return

        item = self._qlx_spawnvisItem
        duration = self._qlx_spawnvisDuration

        spots = minqlxtended.spawn_points()
        for spot in spots:
            ent = minqlxtended.spawn_entity(item, {"origin": tuple(spot.s.origin)})
            if ent is not None:
                self._markers.append(ent.number)
        self._marker_classname = item

        if not self._markers:
            channel.reply(
                f"Found ^6{len(spots)}^7 spawn points but no ^6{item}^7 marker spawned - this gametype's "
                "item rules probably filtered it; try another qlx_spawnvisItem.")
            return

        self._cleanup_timer = self.delay(duration, self._clear_markers)
        channel.reply(f"Marking ^6{len(self._markers)}^7 of ^6{len(spots)}^7 spawn points with ^6{item}^7 for ^6{duration}^7 seconds.")

    def _clear_markers(self):
        self._cleanup_timer = None
        for number in self._markers:
            ent = minqlxtended.Entity(number)
            # Entity numbers are reused: only free a slot that still holds our marker.
            if ent.inuse and ent.classname == self._marker_classname:
                minqlxtended.remove_entity(number)
        self._markers.clear()
