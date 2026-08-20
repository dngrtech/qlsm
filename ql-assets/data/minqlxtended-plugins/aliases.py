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

# aliases.py - a plugin for minqlxtended to show player aliases

import minqlxtended

NOALIASES_FLAG_NAME = "noaliases"

class aliases(minqlxtended.Plugin):
    _linelimit = minqlxtended.setting("qlx_aliasLimitOutputLines", 15)

    @minqlxtended.command("alias", usage="<id>")
    def cmd_alias(self, player, msg, channel):
        """Provides a list of aliases the server is aware of for the player ID/Steam ID provided."""
        # Validate here rather than in the worker. @minqlxtended.thread returns the
        # Thread, so a Return.USAGE computed inside one is thrown away.
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        # Resolve everything touching engine state here, on the game thread. Reading
        # .is_bot/.steam_id/.name from the worker races the slot being freed and reused.
        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return minqlxtended.Return.STOP_ALL
        steam_id, player_name, target_player = resolved

        if target_player is not None and target_player.is_bot:
            channel.reply("Bots do not have aliases!")
            return minqlxtended.Return.STOP_ALL

        self._lookup_aliases(player.name, msg[0], steam_id, player_name, channel)
        return minqlxtended.Return.STOP_ALL

    @minqlxtended.thread
    def _lookup_aliases(self, caller_name, command, steam_id, player_name, channel):
        # Plain data only: no Player objects, no engine calls.
        player_iplist = list(self.db.smembers(f"minqlx:players:{steam_id}:ips"))

        lineused = 1
        response = f"{player_name}^7's aliases:\n"

        if self.db.get_flag(steam_id, NOALIASES_FLAG_NAME):
            self.logger.info(f"{caller_name} ran {command} on {player_name} who has the '{NOALIASES_FLAG_NAME}' flag set.")
            name = self.db.get(f"minqlx:players:{steam_id}:current_name")
            if name:
                response += f" ^6•^7 {steam_id}:\n    ^6•^7 {self.clean_text(name)}"
            channel.reply(response)
            return

        data = dict()
        steamids = list()

        for ip_address in player_iplist:
            steamids += list(self.db.smembers(f"minqlx:ips:{ip_address}"))

        steamids = self.dedupe(steamids)

        for steamid in steamids:
            data[steamid] = list(self.db.lrange(f"minqlx:players:{steamid}", 0, -1))

        for sid, names in data.items():
            if lineused == self._linelimit:
                break
            used_names = list()
            response += f" ^6•^7 {sid}:\n"
            for name in names:
                if name not in used_names:
                    if lineused == self._linelimit:
                        response += f"^1Remaining aliases truncated (line limit set to {self._linelimit})^7\n"
                        break
                    response += f"    ^6•^7 {self.clean_text(name)}\n"
                    lineused += 1
                    used_names.append(name)

        channel.reply(response)

    @minqlxtended.command("setnoaliases", permission=4, client_cmd_perm=4, usage="<id>")
    def cmd_setnoaliases(self, player, msg, channel):
        """Set/unset the 'noaliases' flag for players, preventing that player's aliases from being listed by the !alias command."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, _name, target_player = resolved

        if target_player:
            name = target_player.clean_name
        else:
            name = ident

        flag = not self.db.get_flag(ident, NOALIASES_FLAG_NAME)
        self.db.set_flag(ident, NOALIASES_FLAG_NAME, flag)

        word = "now has" if flag else "no longer has"
        channel.reply(f"Player ^6{name}^7 {word} the 'no aliases' flag.")

    @minqlxtended.command("clearaliases", permission=5)
    def cmd_clearaliases(self, player, msg, channel):
        """Clears all alias records from the server database."""
        if player.steam_id != minqlxtended.owner():
            player.tell("You must be the owner of the server to execute this command.")
            return

        channel.reply("Clearing all aliases in the background...")
        self._clear_aliases(channel)

    @minqlxtended.thread
    def _clear_aliases(self, channel):
        # minqlx:players holds every steam id ever seen, tens of thousands of keys on a
        # mature database, so batch the deletes.
        players = self.db.smembers("minqlx:players")
        ips = self.db.smembers("minqlx:ips")

        # !alias also walks the IP correlation index to find which steam ids share an
        # address, and prints current_name for players carrying the 'noaliases' flag.
        keys = [f"minqlx:players:{p}" for p in players]
        keys += [f"minqlx:players:{p}:current_name" for p in players]
        keys += [f"minqlx:players:{p}:ips" for p in players]
        keys += [f"minqlx:ips:{ip}" for ip in ips]
        keys.append("minqlx:ips")

        for start in range(0, len(keys), 500):
            self.db.delete(*keys[start:start + 500])

        channel.reply(f"All aliases for all players ({len(players)} players in total) were cleared.")

    def dedupe(self, lst):
        return list(dict.fromkeys(lst))
