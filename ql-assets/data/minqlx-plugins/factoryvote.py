# Copyright (C) 2025 Doomsday
# This is an extension plugin for minqlx to callvote factories
# Place the factories you want votable in factories.txt in your /baseq3 folder
# Originally created for Thunderdome tournament servers

# You can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.

# You should have received a copy of the GNU General Public License
# along with minqlx. If not, see <http://www.gnu.org/licenses/>.

# Created by Doomsday
# https://github.com/D00MSDAYDEVICE
# https://www.youtube.com/@HIT-CLIPS

# You are free to modify this plugin.
# This plugin comes with no warranty or guarantee.

# Copyright (C) 2025 Doomsday
# This is an extension plugin for minqlx to callvote factories

import minqlx
import os
import time

class factoryvote(minqlx.Plugin):
    def __init__(self):
        self.version = "1.6"
        self.add_command("factoryvote", self.cmd_factoryvote, 0)
        self.add_command("fv", self.cmd_factoryvote, 0)
        self.add_command("fvv", self.cmd_version, 0)
        self.add_command("factory", self.cmd_factory, 0)
        self.add_command("check", self.cmd_check, 0)

        self.factories = self.load_factories()
        self.selected_factory = None
        self.add_hook("game_countdown", self.handle_game_countdown)

    def cmd_version(self, player, msg, channel):
        player.tell("^3FactoryVote Plugin Version:^7 {}".format(self.version))

    def load_factories(self):
        primary = os.path.join(self.get_cvar("fs_basepath"), "baseq3", "factories.txt")
        fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), "factories.txt")

        if os.path.isfile(primary):
            factories_file = primary
            self.logger.info("factories.txt found in baseq3.")
        elif os.path.isfile(fallback):
            factories_file = fallback
            self.logger.info("factories.txt not found in baseq3, using minqlx-plugins folder.")
        else:
            self.logger.warning("factories.txt not found in baseq3 or minqlx-plugins folder.")
            return None

        with open(factories_file, "r") as f:
            factories = [line.strip() for line in f if line.strip()]
        if not factories:
            self.logger.warning("factories.txt is empty.")
        return factories

    def handle_game_countdown(self):
        if self.selected_factory:
            self.msg("^3Game starting with factory:^7 {}".format(self.selected_factory))
        else:
            self.msg("^3Game starting. No factory selected. Using default settings.")

    def cmd_factory(self, player, msg, channel):
        if self.selected_factory:
            player.tell("^3Current loaded factory:^7 {}".format(self.selected_factory))
        else:
            player.tell("^3No factory has been selected yet.")

    def cmd_check(self, player, msg, channel):
        try:
            server_factory = self.game.factory
        except Exception:
            server_factory = None

        if server_factory:
            player.tell("^3Current Factory (server):^7 {}".format(server_factory))
        else:
            player.tell("^1Could not retrieve current factory from server.")

        if self.selected_factory:
            if self.selected_factory.lower() == (server_factory or "").lower():
                player.tell("^2Plugin selected factory matches the server factory.")
            else:
                player.tell("^3Plugin selected factory:^7 {} ^3(differs from server)".format(self.selected_factory))
        else:
            player.tell("^3No factory selected via plugin yet.")

    def cmd_factoryvote(self, player, msg, channel):
        if self.factories is None:
            player.tell("^1Error:^7 factories.txt not found in baseq3.")
            return

        if not self.factories:
            player.tell("^1Error:^7 factories.txt is empty.")
            return

        if len(msg) == 1:
            player.tell("^3Available Factories:")
            for idx, factory in enumerate(self.factories, start=1):
                player.tell("^7{}: {}".format(idx, factory))
            player.tell("^3Use ^7!fv <number> ^3to start a vote.")
            return

        try:
            selection = int(msg[1])
        except ValueError:
            player.tell("^1Invalid selection. Use a number from the list.")
            return

        if selection < 1 or selection > len(self.factories):
            player.tell("^1Invalid factory number.")
            return

        self.selected_factory = self.factories[selection - 1]
        player.tell("^3You selected factory:^7 {}".format(self.selected_factory))

        # Embed the factory name directly into the vote text
        vote_text = f"Change map to {self.selected_factory} factory?"
        vote_command = f"qlx !map {self.game.map} {self.selected_factory}"

        self.callvote(vote_command, vote_text)  # Factory name shown in vote

        minqlx.delay(30)(self.check_vote_result)

    def check_vote_result(self):
        if self.game.vote_passed:
            self.msg("^2Vote passed! Loading factory:^7 {}".format(self.selected_factory))
            self.command("qlx !map {} {}".format(self.game.map, self.selected_factory))
        else:
            self.msg("^1Vote failed for factory:^7 {}".format(self.selected_factory))
