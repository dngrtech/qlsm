# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2025-2026 Thomas Jones <me@thomasjones.id.au>

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

# infectedmm.py - a plugin for minqlxtended to recreate the Infected Mastermind game mode from yore.

import minqlxtended

INFECTED_MASTERMIND_BOT_NAME = "Infected Mastermind"
INFECTED_MASTERMIND_BOT = "uriel"
INFECTED_TEAM = "red"
STANDARD_TEAM = "blue"
ITEM_PLASMAGUN = 16

class infectedmm(minqlxtended.Plugin):
    _g_rrInfectedMastermindHealthBonus = minqlxtended.setting("g_rrInfectedMastermindHealthBonus", 50)
    _g_rrInfectedMastermindFragBonus = minqlxtended.setting("g_rrInfectedMastermindFragBonus", 3)
    # _g_rrInfectedMastermindSpeed = minqlxtended.setting("g_rrInfectedMastermindSpeed", 1.0)  # don't know how to implement this yet
    # _g_rrInfectedMastermindDrops = minqlxtended.setting("g_rrInfectedMastermindDrops", True) # don't know what this does yet

    def __init__(self):
        super().__init__()
        self.add_hook("new_game", self.handle_new_game)

        self._infected_mastermind_bot = None
        self._loaded = False

        if self.is_infected_mastermind_gametype:
            self._add_hooks()

    @minqlxtended.next_frame
    def handle_new_game(self):
        if (not self.is_infected_mastermind_gametype) and (self.infected_mastermind_bot):
            self.remove_infected_mastermind_bot()

        if (not self.is_infected_mastermind_gametype) and (self._loaded):
            self._remove_hooks()
        elif (self.is_infected_mastermind_gametype) and (not self._loaded):
            self._add_hooks()

        if not self.is_infected_mastermind_gametype:
            return

        if not self.get_cvar("bot_enable", bool):
            self.set_cvar("bot_enable", "1")
            self.msg("Restarting the map to load in bot AAS for Infected Mastermind.")
            self.game.map = self.game.map
            return

        @minqlxtended.delay(self.get_cvar("g_warmupDelay", int) / 2)
        def f(self):
            if not self.infected_mastermind_bot:
                self.add_infected_mastermind_bot(spec=True)
            elif (self.infected_mastermind_bot.team != minqlxtended.Team.SPECTATOR) and (self.game.state == minqlxtended.GameState.WARMUP):
                self.infected_mastermind_bot.team = "spectator"

        f(self)

    def _add_hooks(self):
        self.add_hook("player_connect", self.handle_player_connect)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.add_hook("game_start", self.handle_game_start)
        self.add_hook("game_end", self.handle_game_end)
        self.add_hook("kill", self.handle_kill)
        self.add_hook("team_switch_attempt", self.handle_team_switch_attempt)
        self.add_hook("round_countdown", self.handle_round_countdown)
        self.add_hook("player_spawn", self.handle_player_spawn)
        self.logger.debug("Infected Mastermind hooks added.")
        self._loaded = True

    def _remove_hooks(self):
        self.remove_hook("player_connect", self.handle_player_connect)
        self.remove_hook("player_disconnect", self.handle_player_disconnect)
        self.remove_hook("game_start", self.handle_game_start)
        self.remove_hook("game_end", self.handle_game_end)
        self.remove_hook("kill", self.handle_kill)
        self.remove_hook("team_switch_attempt", self.handle_team_switch_attempt)
        self.remove_hook("round_countdown", self.handle_round_countdown)
        self.remove_hook("player_spawn", self.handle_player_spawn)
        self.logger.debug("Infected Mastermind hooks removed.")
        self._loaded = False

    def handle_player_connect(self, player, is_bot):
        if not self.is_infected_mastermind_gametype:
            return

        if self.is_infected_mastermind_bot(player):
            self._infected_mastermind_bot = player

    def handle_player_disconnect(self, player, reason):
        if self.is_infected_mastermind_bot(player):
            self._infected_mastermind_bot = None

    @minqlxtended.next_frame
    def handle_game_start(self):
        if not self.is_infected_mastermind_gametype:
            return

        if not self.infected_mastermind_bot:
            # `addbot` is a console command, so the bot doesn't exist yet when it
            # returns. Add it straight onto the infected team and let player_connect
            # pick it up once it joins.
            self.add_infected_mastermind_bot(spec=False, delay=0)
            return

        self.infected_mastermind_bot.team = INFECTED_TEAM

    @minqlxtended.next_frame
    def handle_game_end(self, aborted):
        if not self.is_infected_mastermind_gametype:
            return

        if not self.infected_mastermind_bot:
            return

        self.infected_mastermind_bot.team = "spectator"

    @minqlxtended.next_frame
    def handle_kill(self, victim, killer, mod):
        if not self.is_infected_mastermind_gametype:
            return

        if (killer) and (victim == self.infected_mastermind_bot) and (killer != self.infected_mastermind_bot):
            self.play_sound("sound/world/screech1.wav", player=killer)  # play sound to killer
            killer.center_print(f"You slayed the ^1{INFECTED_MASTERMIND_BOT_NAME}^7!")
            self.center_print(f"{killer.name}^7 looted the Mastermind!")
            self.logger.info(f"{killer.name} killed the mastermind, increasing score by the frag bonus.")
            killer.score += self._g_rrInfectedMastermindFragBonus  # killer gets a bonus if they kill the mastermind

            position = victim.position
            minqlxtended.spawn_item(ITEM_PLASMAGUN, int(position.x), int(position.y), int(position.z) + 10)  # drop Plasma Gun at bot's position

    def handle_team_switch_attempt(self, player, old_team, new_team, target):
        if not self.is_infected_mastermind_gametype:
            return

        if self.is_infected_mastermind_bot(player):
            if new_team == STANDARD_TEAM:
                return minqlxtended.Return.STOP_ALL  # mastermind bot cannot ever switch to standard team
            elif (self.game.state != minqlxtended.GameState.WARMUP) and (new_team != INFECTED_TEAM):
                return minqlxtended.Return.STOP_ALL  # mastermind bot can only switch to the infected team during active games

    @minqlxtended.next_frame
    def handle_round_countdown(self, round_number):
        if not self.is_infected_mastermind_gametype:
            return

        if not self.infected_mastermind_bot:
            self.msg(f"Where did {INFECTED_MASTERMIND_BOT_NAME}^7 go? Adding a new one.")
            self.add_infected_mastermind_bot(spec=False, delay=0)

        for player in self.players():
            if self.is_infected_mastermind_bot(player):
                self.transfer_player(player, INFECTED_TEAM)  # mastermind is always infected at the start of a round
            elif player.team == minqlxtended.Team.SPECTATOR:
                continue  # spectator players are not moved to any team
            elif player.team == INFECTED_TEAM:
                self.transfer_player(player, STANDARD_TEAM)  # infected players are moved to the standard team

    @minqlxtended.next_frame
    def handle_player_spawn(self, player):
        if not self.is_infected_mastermind_gametype:
            return

        if self.is_infected_mastermind_bot(player):
            player.health += self._g_rrInfectedMastermindHealthBonus * len(
                self.teams()[STANDARD_TEAM]
            )  # mastermind gets a health bonus based on the number of uninfected players
            player.weapons = minqlxtended.NO_WEAPONS._replace(pg=True)  # nothing but Plasma Gun in inventory
            player.ammo = minqlxtended.NO_AMMO._replace(pg=-1)  # infinite ammo
            player.weapon = minqlxtended.Weapon.PLASMAGUN  # select Plasma Gun weapon

    def add_infected_mastermind_bot(self, spec: bool = True, delay: int = 1000):
        if not self.get_cvar("bot_enable", bool):
            self.logger.warning("Bots are disabled, cannot add mastermind bot. Falling back to standard Infected mode.")
            minqlxtended.set_cvar("g_rrInfected", "1", force=True)
            return

        if self.infected_mastermind_bot:
            self.logger.debug("Mastermind bot already exists, not adding another.")
            return

        self.logger.debug(
            f"Adding mastermind bot '{INFECTED_MASTERMIND_BOT_NAME}' ({INFECTED_MASTERMIND_BOT}) to the {'spectators' if spec else INFECTED_TEAM} team."
        )

        minqlxtended.console_command(f'addbot {INFECTED_MASTERMIND_BOT} 5 {"s" if spec else INFECTED_TEAM} {delay} "{INFECTED_MASTERMIND_BOT_NAME}"')

    def remove_infected_mastermind_bot(self, reason: str = "was quarantined"):
        if not self.infected_mastermind_bot:
            self.logger.debug("No mastermind bot to remove.")
            return

        self.logger.debug(f"Removing mastermind bot '{self.infected_mastermind_bot.name}' ({self.infected_mastermind_bot.model})")
        self.infected_mastermind_bot.kick(reason)

    def is_infected_mastermind_bot(self, player) -> bool:
        return (player.is_bot) and (player.name.startswith(INFECTED_MASTERMIND_BOT_NAME)) and (player.model.lower() == INFECTED_MASTERMIND_BOT.lower())

    @property
    def is_infected_mastermind_gametype(self):
        return (self.get_cvar("g_rrInfected", int) == 2) and (self.game) and (self.game.type_short == minqlxtended.Gametype.RED_ROVER)

    @property
    def infected_mastermind_bot(self) -> minqlxtended.Player | None:
        if self._infected_mastermind_bot:
            try:
                self._infected_mastermind_bot.update()
                return self._infected_mastermind_bot
            except minqlxtended.NonexistentPlayerError:
                self._infected_mastermind_bot = None

        for player in self.players():
            if self.is_infected_mastermind_bot(player):
                self._infected_mastermind_bot = player

        return self._infected_mastermind_bot

    def transfer_player(self, player, new_team):
        """Transfer a player to a new team without losing their stats and score."""
        stats, score = player.stats, player.score  # save stats and score
        player.team = new_team  # move player to new team
        player.stats, player.score = stats, score  # restore stats and score
