# This is an extension plugin  for minqlx.
# Copyright (C) 2018 BarelyMiSSeD (github)

# You can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.

# You should have received a copy of the GNU General Public License
# along with minqlx. If not, see <http://www.gnu.org/licenses/>.

# This is a plugin and command listing script for the minqlx admin bot.
# This plugin will list all the in game commands loaded on the server.
"""
//Server Config cvars
//Set the permission level needed to list the commands
set qlx_commandsAdmin "3"
//Enable to show only the commands the calling player can use, disable to show all commands (0=disable, 1=enable)
set qlx_commandsOnlyEligible "1"
"""

import minqlx

VERSION = "1.0"

# Hard cap on output lines per invocation to avoid flooding the client
# command buffer. Use !lc <plugin_name> to narrow results past the cap.
MAX_TELL_LINES = 20

# Number of plugin names listed per line in !plugins output.
PLUGINS_PER_LINE = 7


class commands(minqlx.Plugin):
    def __init__(self):
        # queue cvars
        self.set_cvar_once("qlx_commandsAdmin", "3")
        self.set_cvar_once("qlx_commandsOnlyEligible", "1")

        # Minqlx bot commands
        self.add_command("plugins", self.list_plugins, self.get_cvar("qlx_commandsAdmin", int))
        self.add_command(("lc", "listcmds", "listcommands"), self.cmd_list, self.get_cvar("qlx_commandsAdmin", int),
                         usage="<plugin_name>")

    def list_plugins(self, player, msg, channel):
        names = sorted(self.plugins)
        count = len(names)
        if not count:
            return
        lines = []
        for i in range(0, count, PLUGINS_PER_LINE):
            lines.append("^7, ^6".join(names[i:i + PLUGINS_PER_LINE]))
        player.tell("^1{} ^3Plugins found:".format(count))
        player.tell("^6{}".format("^7\n^6".join(lines)))

    def cmd_list(self, player, msg, channel):
        plugins = sorted(self.plugins)
        only_eligible = self.get_cvar("qlx_commandsOnlyEligible", bool)
        caller_perm = self.db.get_permission(player)
        search = msg[1].lower() if len(msg) > 1 else None
        lines = ["^1Plugin^7: ^2Number of Commands"]
        count = 0
        for name in plugins:
            if search and search not in name.lower():
                continue
            try:
                cmds = self.plugins[name].commands
            except Exception:
                minqlx.log_exception()
                continue
            entries = []
            for cmd in cmds:
                if only_eligible and caller_perm < cmd.permission:
                    continue
                entries.append("^7(^2{}^7) ^6{}".format(cmd.permission, "^7|^6".join(cmd.name)))
            if entries:
                m = len(entries)
                lines.append("^1{}^7: {} ^3Command{}".format(name, m, "s" if m > 1 else ""))
                lines.append("^7, ".join(entries))
                count += 1
        if not count:
            player.tell("^3No Plugin matches ^4{}".format(search))
            return
        for line in lines[:MAX_TELL_LINES]:
            player.tell(line)
        if len(lines) > MAX_TELL_LINES:
            player.tell("^3Output truncated. Use ^7!lc <plugin_name> ^3to narrow results.")
