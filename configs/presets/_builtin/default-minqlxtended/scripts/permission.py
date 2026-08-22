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

"""Database agnostic way of getting and setting a player's permissions.

It assumes the database driver interprets integers as SteamID64s and
being able to handle minqlxtended.Player instances.

"""

import minqlxtended

class permission(minqlxtended.Plugin):
    @minqlxtended.command("setperm", permission=5, usage="<id> <level>")
    def cmd_setperm(self, player, msg, channel):
        """Sets the specified player's permission level to that specified."""
        if len(msg) < 3:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, _name, target_player = resolved

        try:
            level = int(msg[2])
            if level < 0 or level > 5:
                raise ValueError
        except ValueError:
            channel.reply("Invalid permission level. Use a level between 0 and 5.")
            return

        self.db.set_permission(ident, level)
        name = target_player.name if target_player else str(ident)

        channel.reply(f"^6{name}^7 was given permission level ^6{level}^7.")

    @minqlxtended.command("getperm", permission=5, usage="<id>")
    def cmd_getperm(self, player, msg, channel):
        """Responds with the specified player's permission level."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, _name, target_player = resolved

        if ident == minqlxtended.owner():
            channel.reply("That's my master.")
            return

        perm = self.db.get_permission(ident)
        name = target_player.name if target_player else str(ident)
        channel.reply(f"^6{name}^7 has permission level ^6{perm}^7.")

    @minqlxtended.command("listperms", permission=5)
    def cmd_listperms(self, player, msg, channel):
        """Lists all players with a permission level greater than 0."""
        # Thread the Redis work, never the handler itself. @minqlxtended.thread makes it
        # return a Thread, which discards Return.USAGE.
        self._list_perms(channel)

    @minqlxtended.thread
    def _list_perms(self, channel):
        # SCAN rather than KEYS, so a large dataset doesn't block the Redis server. The
        # permission and name lookups batch into two round-trips.
        perm_keys = list(self.db.scan_iter(match="minqlx:players:*:permission"))
        steam_ids = [key.split(":")[2] for key in perm_keys]

        players_permissions = {}
        if perm_keys:
            perm_values = self.db.mget(perm_keys)
            name_values = self.db.mget([f"minqlx:players:{sid}:current_name" for sid in steam_ids])
            for sid, perm_value, name_value in zip(steam_ids, perm_values, name_values):
                if not perm_value:
                    continue
                permission = int(perm_value)
                if permission > 0:
                    players_permissions[name_value if name_value else sid] = permission

        players_permissions = dict(sorted(players_permissions.items(), key=lambda x: x[1]))

        if not players_permissions:
            channel.reply("No players with permission levels greater than 0.")
            return

        # One reliable command rather than one per admin, since a long permissions list
        # eats the caller's 64-slot ring.
        self.reply_lines(channel, ["^7Permissions list:"]
                         + [f" {name}^7: ^6{permission}^7" for name, permission in players_permissions.items()])

    @minqlxtended.command("myperm", channels=("chat", "red_team_chat", "blue_team_chat", "spectator_chat", "free_chat", "client_command"))
    def cmd_myperm(self, player, msg, channel):
        """Respond with the calling player's permission level."""
        if player.steam_id == minqlxtended.owner():
            channel.reply("You can do anything to me, master.")
            return

        perm = self.db.get_permission(player)
        # get_permission defaults a missing key to 0, so telling "level 0" from "never
        # seen" means asking whether the key is there.
        if perm == 0 and f"minqlx:players:{player.steam_id}:permission" not in self.db:
            channel.reply("I do not know you.")
        else:
            channel.reply(f"You have permission level ^6{perm}^7.")
