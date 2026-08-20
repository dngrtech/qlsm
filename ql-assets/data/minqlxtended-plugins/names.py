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
import re

_re_remove_excessive_colors = re.compile(r"(?:\^.)+(\^.)")
_name_key = "minqlx:players:{}:colored_name"

class names(minqlxtended.Plugin):
    _qlx_enforceSteamName = minqlxtended.setting("qlx_enforceSteamName", True)
    # essentials.py owns this cvar; the default here must stay in sync with it.
    _qlx_commandPrefix = minqlxtended.setting("qlx_commandPrefix", "!")

    def __init__(self):
        super().__init__()

        self.steam_names = {}
        # steam id -> registered name, or None for "no registered name". Absent means not
        # looked up yet. handle_userinfo runs on the game thread for every userinfo change,
        # and a client can send those as often as it likes.
        self.registered_names = {}
        # Steam ids whose next userinfo change is one this plugin just caused. Per player,
        # or one registration swallows whichever other change arrives next.
        self.name_set = set()

    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot):
        self.steam_names[player.steam_id] = player.clean_name

    @minqlxtended.hook("player_loaded")
    def handle_player_loaded(self, player):
        # The one read per session; handle_userinfo works from the cache after this.
        db_name = self.db.get(_name_key.format(player.steam_id))
        self.registered_names[player.steam_id] = db_name
        if db_name:
            if not self._qlx_enforceSteamName or self.clean_text(db_name).lower() == player.clean_name.lower():
                self._assign_name(player, db_name)

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        self.steam_names.pop(player.steam_id, None)
        self.registered_names.pop(player.steam_id, None)
        self.name_set.discard(player.steam_id)

    @minqlxtended.hook("userinfo")
    def handle_userinfo(self, player, changed, infostring):
        # Make sure we're not doing anything if our script set the name.
        if player.steam_id in self.name_set:
            self.name_set.discard(player.steam_id)
            return

        if "name" in changed:
            current_clean = self.clean_text(changed["name"])
            # From the cache. `registered` is None both for no registered name and for one
            # not read yet, after a mid-session reload.
            registered = self.registered_names.get(player.steam_id)
            if registered is None or player.steam_id not in self.steam_names:
                self.steam_names[player.steam_id] = current_clean
            elif self.steam_names[player.steam_id] == current_clean:
                changed["name"] = registered
                return changed
            else:
                del self.db[_name_key.format(player.steam_id)]
                self.registered_names[player.steam_id] = None
                player.tell("Your registered name has been reset.")

    @minqlxtended.command(("name", "setname"), client_cmd_perm=0, usage="<name>")
    def cmd_name(self, player, msg, channel):
        """ Re-colours the player's name to the string specified, or clears custom colouring if nothing specified. """
        name_key = _name_key.format(player.steam_id)

        if len(msg) < 2:
            if name_key not in self.db:
                return minqlxtended.Return.USAGE
            else:
                del self.db[name_key]
                self.registered_names[player.steam_id] = None
                player.tell("Your registered name has been removed.")
                return minqlxtended.Return.STOP_ALL

        name = self.clean_excessive_colors(" ".join(msg[1:]))
        if len(name.encode()) > 36:
            player.tell("The name is too long. Consider using fewer colors or a shorter name.")
            return minqlxtended.Return.STOP_ALL
        elif self.clean_text(name).lower() != player.clean_name.lower() and self._qlx_enforceSteamName:
            player.tell("The new name must match your current Steam name.")
            return minqlxtended.Return.STOP_ALL
        elif any(c in name for c in "\\;\""):
            # The infostring format cannot carry these, and format_infostring raises on
            # them part-way through the assignment below.
            player.tell("The characters '^6\\^7', '^6;^7' and '^6\"^7' cannot be used. Sorry for the inconvenience.")
            return minqlxtended.Return.STOP_ALL
        elif not self.clean_text(name).strip():
            player.tell("Blank names cannot be used. Sorry for the inconvenience.")
            return minqlxtended.Return.STOP_ALL

        name = "^7" + name
        self._assign_name(player, name)
        self.db[name_key] = name
        self.registered_names[player.steam_id] = name
        player.tell(f"The name has been registered. To make me forget about it, a simple ^6{self._qlx_commandPrefix}name^7 will do it.")
        return minqlxtended.Return.STOP_ALL

    def _assign_name(self, player, name):
        """Set a player's name and flag the userinfo event it causes as ours."""
        # An assignment matching the client's current userinfo diffs to nothing, so no
        # userinfo event is raised and the flag would sit in name_set until the player's
        # next name change, then swallow it.
        if player.cvars.get("name") == name:
            return

        self.name_set.add(player.steam_id)
        player.name = name

    def clean_excessive_colors(self, name):
        """Removes excessive colors and only keeps the ones that matter."""
        def sub_func(match):
            return match.group(1)

        return _re_remove_excessive_colors.sub(sub_func, name)
