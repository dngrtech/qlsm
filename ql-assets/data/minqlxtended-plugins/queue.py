# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2016 mattiZed (github)
# Copyright (C) 2016 Melodeiro (github)
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

# queue.py - a plugin for minqlxtended to allow players to queue politely for fair and even gameplay.
# Everything here runs on the main game thread and nothing here blocks, so don't reach for
# @minqlxtended.thread: it only races the shared _queue/_afk/_tags. The debounced re-push
# uses @minqlxtended.delay.

import time

import minqlxtended

NO_CLANTAG_FLAG_NAME = "no_clantag"

# Push requests landing this close together share one scheduled run.
PUSH_COALESCE_WINDOW = 0.25

def _known_gametype(game):
    """The gametype, or None when there's no game or it's one this build can't name.

    Game.type_short raises for a g_gametype with no name behind it.
    """
    if game is None:
        return None
    try:
        return game.type_short
    except ValueError:
        return None

_tag_key = "minqlx:players:{}:clantag"

class queue(minqlxtended.Plugin):
    _qlx_queueSetAfkPermission = minqlxtended.setting("qlx_queueSetAfkPermission", 2)
    _qlx_queueAFKTag = minqlxtended.setting("qlx_queueAFKTag", "^3AFK")

    def __init__(self):
        super().__init__()

        self._queue = []
        self._afk = []
        self._tags = {}

        # These flags must exist before initialize() or any scheduled push runs.
        self.is_endscreen = False  # set True between game_end and the next new_game
        self._push_pending = []  # deadlines of the pushFromQueue runs currently armed
        self._tags_dirty = False  # main-thread debounce for the tag refresh pass

        self.initialize()

    def initialize(self):
        # No unlock here: the state is read live, so there's nothing to seed, and nothing
        # here touches self.game, which is None mid map change.
        for p in self.players():
            self.updTag(p)

    ## Basic List Handling (Queue and AFK)
    def addToQueue(self, player, pos=-1):
        """Safely adds players to the queue"""
        if player not in self._queue:
            if pos == -1:
                self._queue.append(player)
            else:
                self._queue.insert(pos, player)
                for p in self._queue:
                    self.updTag(p)
            for p in self.teams()['spectator']:
                p.center_print(f"{player.name}^7 joined the queue")
        if player in self._queue:
            player.center_print("You are in the queue to play")
        self.updTag(player)
        self.pushFromQueue()

    def remFromQueue(self, player, update=True):
        """Safely removes player from the queue"""
        if player in self._queue:
            self._queue.remove(player)
        for p in self._queue:
            self.updTag(p)
        if update:
            self.updTag(player)

    def pushFromQueue(self, delay=0):
        """Debounced request to fill/even teams from the queue.

        Each requested delay matters: handle_vote_ended asks for 4 seconds because the
        engine applies a passed vote about 3 seconds after vote_ended, and a push before
        then reads the old teamsize. A request folds into a pending run only when that run
        fires at about the same time; otherwise it arms its own.
        """
        deadline = time.time() + (delay if delay and delay > 0 else 0)
        for pending in self._push_pending:
            if abs(pending - deadline) <= PUSH_COALESCE_WINDOW:
                return
        self._push_pending.append(deadline)

        if delay and delay > 0:
            @minqlxtended.delay(delay)
            def run():
                self._fire_push(deadline)
            run()
        else:
            @minqlxtended.next_frame
            def run():
                self._fire_push(deadline)
            run()

    def _fire_push(self, deadline):
        # Cleared first so the re-arm in _check_for_place opens a fresh 0.5s window.
        try:
            self._push_pending.remove(deadline)
        except ValueError:
            pass
        self._do_push()

    def _do_push(self):
        if not self._queue:
            return
        # Reached from @delay/@next_frame callbacks, which can land after a map change.
        # Game() raises then, and self.game hands back None.
        game = self.game
        if game is None:
            return
        if game.state != minqlxtended.GameState.IN_PROGRESS and game.state != minqlxtended.GameState.WARMUP:
            return
        if self.is_endscreen:
            return
        self._check_for_place()

    def _check_for_place(self):
        """Check if there is space and players in the queue, and put them in the game."""
        maxplayers = self.get_maxplayers()
        teams = self.teams()
        red_amount = len(teams["red"])
        blue_amount = len(teams["blue"])
        free_amount = len(teams["free"])
        pushed = False

        # Read live off the game module, however the lock was made.
        red_locked = minqlxtended.Game.is_team_locked("red")
        blue_locked = minqlxtended.Game.is_team_locked("blue")

        if self.game.is_team_based:
            diff = red_amount - blue_amount
            if diff > 0 and not blue_locked:
                pushed = self._push_to_team(diff, "blue")
            elif diff < 0 and not red_locked:
                pushed = self._push_to_team(-diff, "red")
            elif red_amount + blue_amount < maxplayers:
                if len(self._queue) > 1 and not blue_locked and not red_locked:
                    pushed = self._push_to_both()
                elif self.game.state == minqlxtended.GameState.WARMUP:  # for the case if there is 1 player in queue
                    if not red_locked and red_amount < int(self.game.teamsize):
                        pushed = self._push_to_team(1, "red")
                    elif not blue_locked and blue_amount < int(self.game.teamsize):
                        pushed = self._push_to_team(1, "blue")
        else:
            if free_amount < maxplayers:
                pushed = self._push_to_team(maxplayers - free_amount, "free")

        # Only re-arm if we actually placed someone, so we keep draining the queue across
        # 0.5s cycles without spinning forever when nobody can currently be placed.
        if pushed:
            self.pushFromQueue(0.5)

    def _live_state(self, player):
        """The queued player's connection state read fresh, or None once they are gone.

        Queue entries are Player objects captured when the player joined the queue, and a
        Player's snapshot is frozen until update() replaces it. Reading connection_state off
        an unrefreshed entry reports whatever it was at queue time.
        """
        try:
            player.update()
        except minqlxtended.NonexistentPlayerError:
            return None
        return player.connection_state

    def _push_to_team(self, amount, team):
        """Move up to `amount` front-of-queue, ACTIVE spectators onto `team`.

        Disconnected/zombie entries are dropped; still-loading (connected/primed) entries
        are kept in place. Returns True if at least one player was placed.
        """
        if self.is_endscreen:
            return False
        placed = 0
        changed = False
        spectators = self.teams()['spectator']
        i = 0
        while placed < amount and i < len(self._queue):
            qplayer = self._queue[i]
            state = self._live_state(qplayer)
            if state == minqlxtended.ConnectionState.ACTIVE and qplayer in spectators:
                self._queue.pop(i)
                qplayer.put(team)
                placed += 1
                changed = True
                spectators = self.teams()['spectator']  # refresh the now-stale snapshot
            elif state not in (minqlxtended.ConnectionState.CONNECTED, minqlxtended.ConnectionState.PRIMED):
                self._queue.pop(i)  # gone for good; drop and re-inspect this index
                changed = True
            else:
                i += 1  # connected/primed: still loading, keep and move past it
        if changed:
            for p in self._queue:
                self.updTag(p)
        return placed > 0

    def _push_to_both(self):
        """Place the two front-of-queue players onto red and blue at once."""
        if self.is_endscreen or len(self._queue) <= 1:
            return False
        spectators = self.teams()['spectator']
        first = self._queue[0]
        first_state = self._live_state(first)
        if first_state == minqlxtended.ConnectionState.ACTIVE and first in spectators:
            second = self._queue[1]
            second_state = self._live_state(second)
            if second_state == minqlxtended.ConnectionState.ACTIVE and second in spectators:
                self._queue.pop(0).put("red")
                self._queue.pop(0).put("blue")
                for p in self._queue:
                    self.updTag(p)
                return True
            elif second_state not in (minqlxtended.ConnectionState.CONNECTED, minqlxtended.ConnectionState.PRIMED):
                self.remFromQueue(second)
        elif first_state not in (minqlxtended.ConnectionState.CONNECTED, minqlxtended.ConnectionState.PRIMED):
            self.remFromQueue(first)
        return False

    def remAFK(self, player, update=True):
        """Safely removes players from afk list"""
        if player in self._afk:
            self._afk.remove(player)
            if update:
                self.updTag(player)

    def posInQueue(self, player):
        """Returns position of the player in queue"""
        try:
            return self._queue.index(player)
        except ValueError:
            return -1

    ## AFK Handling
    def setAFK(self, player):
        """Returns True if player's state could be set to AFK"""
        if player in self.teams()['spectator'] and player not in self._afk:
            self._afk.append(player)
            self.remFromQueue(player)
            return True
        return False

    def remTag(self, player):
        self._tags.pop(player.steam_id, None)
        clan = self.plugin("clan")
        if clan is not None:
            clan.clear_prefix(player.id)

    def updTag(self, player=None):
        """Request a tag refresh.

        Every call site just marks the tags dirty. One coalesced pass per frame does a
        single scan and writes only for the players whose tag changed.
        """
        self._mark_tags_dirty()

    def _mark_tags_dirty(self):
        if self._tags_dirty:
            return
        self._tags_dirty = True
        self._apply_tags()

    @minqlxtended.next_frame
    def _apply_tags(self):
        self._tags_dirty = False

        players = self.players()
        if not players:
            self._tags.clear()
            return

        # One scan for everyone, rather than one per player being updated.
        spectators = {p.id for p in self.teams(player_list=players)["spectator"]}
        queue_positions = {p.steam_id: i for i, p in enumerate(self._queue)}
        afk = {p.steam_id for p in self._afk}

        game = self.game
        tagged_gametype = _known_gametype(game) is not None

        clan = self.plugin("clan")
        live = set()
        standalone = []

        if clan is not None:
            # Nothing here mirrors clan.py's state, so drop anything the standalone path
            # left behind while clan.py was absent.
            self._tags.clear()

        for player in players:
            live.add(player.steam_id)

            position = queue_positions.get(player.steam_id)
            if position is not None:
                prefix = f"^7(^5{position + 1}^7)"
            elif player.steam_id in afk:
                prefix = f"^7(^5{self._qlx_queueAFKTag}^7)"
            elif not tagged_gametype:
                prefix = ""
            elif player.id in spectators:
                prefix = "^7(^5s^7)"
            else:
                prefix = ""

            if clan is not None:
                # clan.py owns cn/xcn and dirty-checks set_prefix against its own
                # _prefixes, so a cache here would go stale the moment it's reloaded.
                clan.set_prefix(player.id, prefix)
                continue

            if self._tags.get(player.steam_id, "") == prefix:
                continue
            self._tags[player.steam_id] = prefix
            standalone.append((player, prefix))

        if standalone:
            self._apply_tags_standalone(standalone)

        # Drop anyone who has since disconnected.
        for steam_id in [s for s in self._tags if s not in live]:
            del self._tags[steam_id]

    def _apply_tags_standalone(self, changed):
        """Fallback composer for when clan.py isn't loaded.

        clan.py is the sole writer of cn/xcn whenever it's loaded; two handlers writing the
        pair puts two pairs in the configstring, and which one a reader honours is anyone's
        guess.

        Runs on the game thread, so the whole pass is held to two Redis round-trips: one
        MGET for the no-clantag flags, one for the stored tags.
        """
        flags = self.db.get_flags([p for p, _ in changed], NO_CLANTAG_FLAG_NAME)
        clan_tags = self.db.mget([_tag_key.format(p.steam_id) for p, _ in changed])

        for (player, prefix), clan_tag in zip(changed, clan_tags):
            tag = prefix
            if clan_tag and not flags.get(player.steam_id, False):
                tag = f"{prefix} {clan_tag}" if prefix else clan_tag

            minqlxtended.update_configstring_variables(
                minqlxtended.CS_PLAYERS + player.id, {"cn": tag or None, "xcn": tag or None}
            )

    def get_maxplayers(self):
        maxplayers = int(self.game.teamsize)
        if self.game.is_team_based:
            maxplayers = maxplayers * 2
        if maxplayers == 0:
            maxplayers = self.get_cvar("sv_maxclients", int)
        return maxplayers

    ## Plugin Handles and Commands
    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        self.remAFK(player, False)
        self.remFromQueue(player, False)
        self.remTag(player)
        self.pushFromQueue(0.5)

    @minqlxtended.hook("player_loaded")
    def handle_player_loaded(self, player):
        self.updTag(player)

    @minqlxtended.hook("team_switch")
    def handle_team_switch(self, player, old_team, new_team):
        if new_team != minqlxtended.Team.SPECTATOR:
            self.remFromQueue(player)
            self.remAFK(player)
        else:
            self.updTag(player)
            self.pushFromQueue(0.5)

    @minqlxtended.hook("team_switch_attempt")
    def handle_team_switch_attempt(self, player, old_team, new_team, target):
        game = self.game
        if _known_gametype(game) is None:
            return

        if new_team != minqlxtended.Team.SPECTATOR and old_team == minqlxtended.Team.SPECTATOR:
            teams = self.teams()
            maxplayers = self.get_maxplayers()
            if len(teams["red"]) + len(teams["blue"]) == maxplayers or len(teams["free"]) == maxplayers or self.game.state == minqlxtended.GameState.IN_PROGRESS or len(self._queue) > 0 or minqlxtended.Game.is_team_locked("red") or minqlxtended.Game.is_team_locked("blue"):
                self.remAFK(player)
                self.addToQueue(player)
                return minqlxtended.Return.STOP_ALL

    @minqlxtended.hook("client_command")
    def handle_client_command(self, player, command):
        if (command.lower().strip() == "team s") and (player.team == minqlxtended.Team.SPECTATOR):
            self.remFromQueue(player)
            if player not in self._queue:
                player.center_print("You are set to spectate only")

    @minqlxtended.hook("vote_ended")
    def handle_vote_ended(self, votes, vote, args, passed):
        if vote.lower().strip() == "teamsize":
            self.pushFromQueue(4)

    @minqlxtended.hook("new_game")
    def handle_new_game(self):
        self.is_endscreen = False

        game = self.game
        if game is None:
            return  # mid map change; Plugin.game hands back None rather than raising

        if _known_gametype(game) is None:
            self._queue = []
            for p in self.players():
                self.updTag(p)
        else:
            self.pushFromQueue()

    @minqlxtended.hook("game_end")
    def handle_game_end(self, aborted):
        self.is_endscreen = True

    @minqlxtended.command(("q", "queue", "que"))
    def cmd_lq(self, player, msg, channel):
        """ Display the current queue. """
        msg = "^7No one in queue."
        if self._queue:
            msg = "^1Queue^7: "
            count = 1
            for p in self._queue:
                msg += f'{p.name}^7({count}) '
                count += 1
        channel.reply(msg)

        if self._afk:
            msg = "^3Away^7 >> "
            for p in self._afk:
                msg += p.name + " "

            channel.reply(msg)

    @minqlxtended.command("afk", usage="<optional player ID>")
    def cmd_afk(self, player, msg, channel):
        """ Marks the calling player as AFK (or the player specified.) """
        if len(msg) > 1:
            if not self.db.has_permission(player, self._qlx_queueSetAfkPermission):
                player.tell("^7You do not have permission to set other players AFK.")
                return minqlxtended.Return.STOP_ALL

            matches = self.find_player(msg[1])
            if not matches:
                player.tell(f"^7No players matching ^6{msg[1]}^7 were found.")
                return minqlxtended.Return.STOP_ALL
            if len(matches) > 1:
                player.tell(f"^7More than one player matches ^6{msg[1]}^7. Please be more specific.")
                return minqlxtended.Return.STOP_ALL

            guy = matches[0]
            if self.setAFK(guy):
                player.tell(f"Status for {guy.name}^7 has been set to ^3AFK^7.")
            else:
                player.tell(f"Couldn't set status for {guy.name}^7 to ^3AFK^7.")
            return minqlxtended.Return.STOP_ALL

        if self.setAFK(player):
            player.tell("^7Your status has been set to ^3AFK^7.")
        else:
            player.tell("^7Couldn't set your status to ^3AFK^7.")

    @minqlxtended.command("here")
    def cmd_playing(self, player, msg, channel):
        """ Marks the calling player as available. """
        self.remAFK(player)
        self.updTag(player)
        player.tell("Your status has been set to ^2AVAILABLE^7.")

    @minqlxtended.command(("teamsize", "ts"), priority=minqlxtended.Priority.HIGH)
    def cmd_teamsize(self, playing, msg, channel):
        self.pushFromQueue(0.5)

    @minqlxtended.hook("console_print")
    def handle_console_print(self, text):
        # Only a nudge: the lock state is read live through Game.is_team_locked wherever it
        # matters, so missing this costs a delayed push and can't wedge the queue.
        if "team is now unlocked" in text:
            self.pushFromQueue(0.5)
