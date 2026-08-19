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

# untracked.py - a plugin for minqlxtended to prevent untrackable players from engaging in a match.
# Created 07/11/2024.

import minqlxtended
import requests

# (connect, read), and one connection pool rather than a handshake per player.
UNTRACKED_TIMEOUT = (3.05, 10)
_session = requests.Session()

ACTION_PREVENT_TEAM_CHANGE = 1
ACTION_PREVENT_PLAYER_CONNECTION = 2

PLAYER_CONNECTION_MESSAGE = "Untrackable players are ^1not allowed^7 to connect to this server.\n"
PLAYER_DISALLOW_GAMEPLAY_MESSAGE = "Untrackable players are ^1not allowed^7 to join the match."

class untracked(minqlxtended.Plugin):
    _qlx_untrackedPlayerAction = minqlxtended.setting("qlx_untrackedPlayerAction", 0) # 0 = do nothing, 1 = prevent player team changes, 2 = prevent player connection

    def __init__(self):
        super().__init__()

        # Cached per session: trackability doesn't change while somebody is connected,
        # and pruning on disconnect keeps the set bounded.
        self.tracked_players = set()
        # Untrackable ids survive the disconnect so the connect gate below can refuse a
        # reconnect, and clear each new game so a fixed QLStats profile is re-queried.
        self.untracked_players = set()

        self._cache_variables()

    @minqlxtended.hook("new_game")
    def handle_new_game(self):
        self._cache_variables()

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        # Only the trackable cache is per-session, since clearing it each new_game costs a
        # thread and an HTTP request per connected player per map change.
        self.tracked_players.discard(player.steam_id)

    def _cache_variables(self):
        """ Snapshots cross-plugin and game state for the worker thread. """
        # Bounds the set and gives an untrackable player a fresh lookup each game.
        self.untracked_players.clear()

        balance = self.plugin("balance")
        self._balance_loaded = balance is not None

        # Snapshot here, on the game thread. check_player_trackable runs on a worker,
        # where self.game is not safe to touch.
        game = self.game
        self._current_map = game.map if game is not None else ""

        if self._balance_loaded:
            self._api_url = balance._api_url

    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot): # initial connection event
        if self._balance_loaded:
            # Use the event's flag here; ServerFlag.BOT isn't set on the entity yet.
            if (not is_bot) and (player.steam_id in self.untracked_players) and (self._qlx_untrackedPlayerAction == ACTION_PREVENT_PLAYER_CONNECTION):
                return PLAYER_CONNECTION_MESSAGE

            self.check_player_trackable(player, is_bot, self.handle_untracked_player)

    @minqlxtended.hook("player_loaded")
    @minqlxtended.next_frame
    def handle_player_loaded(self, player): # fires when clients re-prime after map change etc, along with initial game join
        if self._balance_loaded:
            # player_loaded fires long after ClientConnect, so SVF_BOT is on the entity
            # by now.
            is_bot = player.is_bot
            self.check_player_trackable(player, is_bot, self.handle_untracked_player)

            if (not is_bot) and (player.steam_id in self.untracked_players):
                if self._qlx_untrackedPlayerAction == ACTION_PREVENT_PLAYER_CONNECTION:
                    self.msg(f"^1Untrackable Player^7: {player.name}^7 is not QLStats trackable, their connection is blocked.")
                elif self._qlx_untrackedPlayerAction == ACTION_PREVENT_TEAM_CHANGE:
                    self.msg(f"^1Untrackable Player^7: {player.name}^7 is not QLStats trackable, they cannot join the match.")
                else:
                    self.msg(f"^1Untrackable Player^7: {player.name}^7 is not QLStats trackable.")

    # target is only supplied by team_switch_attempt (the raw argument the client sent,
    # e.g. "follow1"); team_switch, which shares this handler, has no such thing.
    @minqlxtended.hook("team_switch_attempt", priority=minqlxtended.Priority.HIGHEST)
    @minqlxtended.hook("team_switch", priority=minqlxtended.Priority.HIGHEST)
    def handle_team_switch(self, player, _, new_team, target=None):
        if new_team == minqlxtended.Team.SPECTATOR:
            return

        if not player.valid:
            return

        if (not player.is_bot) and (player.steam_id in self.untracked_players) and (self._qlx_untrackedPlayerAction >= ACTION_PREVENT_TEAM_CHANGE):
            if player.team != minqlxtended.Team.SPECTATOR:
                player.team = "spectator"

            player.tell(PLAYER_DISALLOW_GAMEPLAY_MESSAGE)
            return minqlxtended.Return.STOP_ALL

    @minqlxtended.next_frame
    def handle_untracked_player(self, player):
        # Called from check_player_trackable on a worker thread, and every line below
        # mutates engine state, so @next_frame puts it back on the game thread.
        if (player.valid) and (player.connection_state == minqlxtended.ConnectionState.ACTIVE):
            if self._qlx_untrackedPlayerAction == ACTION_PREVENT_PLAYER_CONNECTION:
                player.kick(self.clean_text(PLAYER_CONNECTION_MESSAGE))
            elif self._qlx_untrackedPlayerAction == ACTION_PREVENT_TEAM_CHANGE:
                if player.team != minqlxtended.Team.SPECTATOR:
                    player.team = "spectator"

                player.tell(PLAYER_DISALLOW_GAMEPLAY_MESSAGE)

    @minqlxtended.thread
    def check_player_trackable(self, player, is_bot, callback_untracked) -> bool:
        # is_bot comes from the caller, since Player.is_bot dereferences the entity and
        # this worker may run while the game thread frees the slot. The SVF_BOT bit isn't
        # set yet during player_connect either.
        if (is_bot) or (player.steam_id in self.tracked_players): # skip bots and pre-validated players.
            return

        if player.steam_id in self.untracked_players: # kick the arse of the existing ones.
            return callback_untracked(player)

        url = f"{self._api_url}{player.steam_id}"
        try:
            res = _session.get(url, headers={"X-QuakeLive-Map": self._current_map},
                               timeout=UNTRACKED_TIMEOUT)
        except requests.RequestException as e:
            # Don't cache a result on failure; we'll retry on the next relevant event.
            self.logger.warning(f"untracked: failed to query trackability for {player.steam_id}: {e}")
            return
        if res.status_code == requests.codes.ok:
            # A 200 with a non-JSON body, from a captive portal or maintenance page, would
            # otherwise raise out of this worker and repeat on every player_loaded.
            try:
                data = res.json()
            except ValueError:
                self.logger.warning(
                    f"untracked: trackability response for {player.steam_id} wasn't JSON.")
                return
            if not isinstance(data, dict):
                return
            if str(player.steam_id) in data.get("untracked", []):
                self.untracked_players.add(player.steam_id)
                return callback_untracked(player)

        self.tracked_players.add(player.steam_id) # prevent future requests by caching the result per-game
