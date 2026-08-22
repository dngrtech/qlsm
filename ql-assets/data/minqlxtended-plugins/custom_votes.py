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

# custom_votes.py - a plugin for minqlxtended to enable the ability to have custom vote functionality in-game.

"""
The following cvars are used on this plugin:
    qlx_disablePlayerRemoval: Prevents non-privileged players from using '/cv kick' or '/cv tempban'. Default: 0
    qlx_disableCvarVoting: Prevents anyone from calling a CVAR vote. Default: 1
    qlx_disableServerRebootVote: Prevents anyone from calling a server reboot vote. Default: 0
    qlx_cvarVotePermissionRequired: Required permission level to call a CVAR vote. Default: 4
    qlx_glasshouse: Kicks the caller of a failed kick/clientkick/tempban vote; permission level 1+ exempt. Default: 1
"""

import minqlxtended
import random
import re
from time import time

ENGINE_VOTE_EXECUTION_DELAY = 3  # seconds

# '/cv cvar <name> <value>'. The vote string goes to the console verbatim when the vote
# passes, so the value rejects the characters SetTag() strips in hooks.c.
_RE_CVAR_VOTE = re.compile(r"^(?P<name>[A-Za-z0-9_]{1,64}) +(?P<value>[^;\"\\\n\r]{1,128})$")

# Cvars '/cv cvar' will not write. qlx_perm_<command> is re-read live on every eligibility
# check and 0 means everyone, so a passed 'qlx_perm_rcon 0' hands arbitrary console
# execution to the server. qlx_owner grants permission 5 ahead of the cache. Matched
# case-insensitively, as Cvar_FindVar does.
_BLOCKED_CVAR_PREFIXES = ("qlx_perm_", "qlx_ccmd_perm_", "rcon")
_BLOCKED_CVARS = frozenset((
    "qlx_owner",
    "qlx_cvarvotepermissionrequired",
    "qlx_disablecvarvoting",
    "qlx_disableplayerremoval",
    "qlx_disableserverrebootvote",
    "fs_game",
    "g_password",
    "sv_privatepassword",
    "sv_privateclientpassword",
    "sv_pure",
))

class custom_votes(minqlxtended.Plugin):
    _qlx_disablePlayerRemoval = minqlxtended.setting("qlx_disablePlayerRemoval", False)
    _qlx_disableCvarVoting = minqlxtended.setting("qlx_disableCvarVoting", True)
    _qlx_disableServerRebootVote = minqlxtended.setting("qlx_disableServerRebootVote", False)
    _qlx_cvarVotePermissionRequired = minqlxtended.setting("qlx_cvarVotePermissionRequired", 4)
    # The glasshouse rule: a frivolous kick/ban vote costs the caller their own slot
    # when it fails.
    _qlx_glasshouse = minqlxtended.setting("qlx_glasshouse", True)

    # Registered but kept out of !listcv: crouchslide is disabled, and mute is an
    # alias of silence.
    _UNLISTED_VOTES = ("crouchslide", "mute")

    def __init__(self):
        super().__init__()

        self.last_vote_ended_time = 0

        # Glasshouse state, both SteamID64s. A vote is open for ~30 seconds, so holding a
        # Player would let the new occupant of that slot be kicked in the caller's place.
        self._glasshouse_pending = None  # set by vote_tempban, confirmed at vote_started
        self._glasshouse_armed = None

    @minqlxtended.command(("listcv", "cvlist", "listcvs"))
    def cmd_listcv(self, player, msg, channel):
        """Lists the available custom call-votes available on this server."""
        # Built from the registrations, so the listing can't drift from what runs. Sent
        # through reply_lines, since thirty tells is thirty of a client's 64 ring slots.
        votes = minqlxtended.CUSTOM_VOTES.votes
        hidden = set(self._UNLISTED_VOTES)
        if self._qlx_disableCvarVoting:
            hidden.add("cvar")

        entries = []
        for name in sorted(votes):
            if name in hidden:
                continue
            _plugin, usage, description = votes[name]
            invocation = f"/cv {name} {usage}".rstrip()
            entries.append((invocation, description))

        width = max(len(invocation) for invocation, _description in entries)
        lines = ["^3Extra call-vote commands available on this server:^7"]
        lines += [f"^5   {invocation:<{width}} - {description}" for invocation, description in entries]

        self.reply_lines(player, lines)

        return minqlxtended.Return.STOP_ALL

    # The reboot countdown. Each step is a @delay callback, so play_sound, msg and
    # center_print all run on the game thread.
    _REBOOT_STEPS = (
        (0, "sound/world/klaxon1",
         "^1!!! ^7The server is rebooting in ^610^7 seconds.",
         "^7The server is rebooting in\n^610^7 seconds"),
        (3, "sound/world/klaxon1",
         "^1!!! ^7Use ^2/reconnect^7 to connect once disconnected.",
         "^7Use ^2/reconnect^7 to connect once disconnected."),
        (6, "sound/world/klaxon1",
         "^1!!! ^7The server will be back online in ^65^7 seconds.",
         "^7The server will be back online in\n^65^7 seconds."),
        (9, "sound/world/buzzer", None, None),
    )

    @minqlxtended.command("quit", permission=5)
    def cmd_quit(self, player, msg, channel):
        """Reboots the server after a klaxon countdown."""
        self._begin_reboot()

    def _begin_reboot(self):
        self.msg("^3Preparing to reboot the server...")

        try:
            self.set_cvar("g_speed", "0")
            self.set_cvar("g_gravity", "0")
        except Exception:
            self.logger.exception("Failed to freeze the server before rebooting.")

        for offset, sound, message, centre in self._REBOOT_STEPS:
            self._schedule_reboot_step(offset, sound, message, centre)

        self._schedule_quit(10)

    def _schedule_reboot_step(self, offset, sound, message, centre):
        @minqlxtended.delay(offset)
        def step():
            self.play_sound(sound)
            if message:
                self.msg(message)
            if centre:
                self.center_print(centre)

        step()

    def _schedule_quit(self, offset):
        @minqlxtended.delay(offset)
        def quit_now():
            minqlxtended.console_command("quit")

        quit_now()

    def _forceconnect(self, client_id, server_port):
        """Point one client at another server by overriding activeAction in its view of
        CS_SYSTEMINFO.

        send_player_configstring merges the key into the client's existing systeminfo
        and quotes the value, which contains spaces the client would otherwise tokenise.

        """
        return self.send_player_configstring(
            client_id, minqlxtended.CS_SYSTEMINFO,
            {"activeAction": f"connect thepurgery.com:{server_port};clearcvar activeAction"})

    @minqlxtended.command("forceconnect", permission=5, usage="<player_id> <server_port>")
    def cmd_forceconnect(self, player, msg, channel):
        if len(msg) < 3:
            return minqlxtended.Return.USAGE

        try:
            client_id = int(msg[1])
            server_port = int(msg[2])
        except ValueError:
            return minqlxtended.Return.USAGE

        if not 0 <= client_id < minqlxtended.MAX_CLIENTS:
            channel.reply("Invalid client ID.")
            return minqlxtended.Return.STOP_ALL

        try:
            target_player = self.player(client_id)
        except minqlxtended.NonexistentPlayerError:
            target_player = None

        if not target_player:
            channel.reply("Invalid client ID.")
            return minqlxtended.Return.STOP_ALL

        self._forceconnect(target_player.id, server_port)

    @minqlxtended.command("forceconnect_all", permission=5, usage="<server_port>")
    def cmd_forceconnect_all(self, player, msg, channel):
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        try:
            server_port = int(msg[1])
        except ValueError:
            return minqlxtended.Return.USAGE

        self._forceconnect_all(server_port)

    def _forceconnect_all(self, server_port):
        # @delay staggers the sends half a second apart, all on the game thread.
        for i, p in enumerate(self.players()):
            if p.is_bot or not p.valid:
                continue
            self._forceconnect_later((i + 1) * 0.5, p.id, server_port)

    def _forceconnect_later(self, offset, client_id, server_port):
        @minqlxtended.delay(offset)
        def send():
            self._forceconnect(client_id, server_port)

        send()

    @minqlxtended.command("excessiveweaps", permission=5, usage="<on/off>")
    def cmd_excessive_weaps(self, player, msg, channel):
        """Sets or resets the excessive weapon reload rates."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        if msg[1] == "on":
            self._apply_excessive_weapons(True)
        elif msg[1] == "off":
            self._apply_excessive_weapons(False)

    def _apply_excessive_weapons(self, enabled):
        if enabled:
            minqlxtended.set_cvar("weapon_reload_sg", "200")
            minqlxtended.set_cvar("weapon_reload_rl", "200")
            minqlxtended.set_cvar("weapon_reload_rg", "50")
            minqlxtended.set_cvar("weapon_reload_prox", "200")
            minqlxtended.set_cvar("weapon_reload_pg", "40")
            minqlxtended.set_cvar("weapon_reload_ng", "800")
            minqlxtended.set_cvar("weapon_reload_mg", "40")
            minqlxtended.set_cvar("weapon_reload_hmg", "40")
            minqlxtended.set_cvar("weapon_reload_gl", "200")
            minqlxtended.set_cvar("weapon_reload_gauntlet", "100")
            minqlxtended.set_cvar("weapon_reload_cg", "30")
            minqlxtended.set_cvar("weapon_reload_bfg", "75")
            minqlxtended.set_cvar("qlx_excessiveWeapons", "1")
            self.msg("Excessive weapons are enabled.")
        else:
            minqlxtended.console_command("reset weapon_reload_sg")
            minqlxtended.console_command("reset weapon_reload_rl")
            if self.get_cvar("pmove_airControl", int):
                minqlxtended.set_cvar("weapon_reload_rg", "1200")
            else:
                minqlxtended.console_command("reset weapon_reload_rg")
            minqlxtended.console_command("reset weapon_reload_prox")
            minqlxtended.console_command("reset weapon_reload_pg")
            minqlxtended.console_command("reset weapon_reload_ng")
            minqlxtended.console_command("reset weapon_reload_mg")
            minqlxtended.console_command("reset weapon_reload_hmg")
            minqlxtended.console_command("reset weapon_reload_gl")
            minqlxtended.console_command("reset weapon_reload_gauntlet")
            minqlxtended.console_command("reset weapon_reload_cg")
            minqlxtended.console_command("reset weapon_reload_bfg")
            minqlxtended.set_cvar("qlx_excessiveWeapons", "0")
            self.msg("Excessive weapons are disabled.")

    @minqlxtended.hook("vote_called")
    def handle_vote_called(self, caller, vote, args):
        """The policy gates every vote passes through, engine built-ins and registered
        custom votes alike: this hook runs before CUSTOM_VOTES gets its turn, and a
        veto here reaches both.
        """
        vote = vote.lower().strip()

        # Read once, up front. Plugin.game hands back None during a map change, and the
        # registered callbacks read game state, so their names are consumed here.
        game = self.game
        if game is None:
            if vote in minqlxtended.CUSTOM_VOTES.votes:
                return minqlxtended.Return.STOP_ALL
            return

        if self.is_vote_active():
            caller.tell("A vote is already in progress.")
            return minqlxtended.Return.STOP_ALL

        if (not (self.get_cvar("g_allowSpecVote", bool))) and (caller.team == minqlxtended.Team.SPECTATOR) and (not self.db.has_permission(caller, 1)):
            caller.tell("You are not allowed to call a vote as spectator.")
            return minqlxtended.Return.STOP_ALL

        if (not (self.get_cvar("g_allowVoteMidGame", bool))) and (game.state != minqlxtended.GameState.WARMUP) and (not self.db.has_permission(caller, 1)):
            caller.tell("Voting is not permitted while the game is in-progress.")
            return minqlxtended.Return.STOP_ALL

        if (self.last_vote_ended_time + ENGINE_VOTE_EXECUTION_DELAY) > time():
            caller.tell("A vote is being executed.")
            return minqlxtended.Return.STOP_ALL

        if vote in ("kick", "clientkick"):
            # A veto-or-fall-through rather than a registered vote, so the engine's built-in
            # kick still proceeds on the allowed path.
            if self._qlx_disablePlayerRemoval and (not self.db.has_permission(caller, 1)):
                caller.tell("Voting to kick/clientkick is disabled in this server.")
                caller.tell("^2/cv spec <id>^7 and ^2/cv silence <id>^7 exist as substitutes to kicking.")
                return minqlxtended.Return.STOP_ALL

    @minqlxtended.hook("vote_ended")
    def handle_vote_ended(self, votes, vote, args, passed):
        self.last_vote_ended_time = time()

    ## The glasshouse rule: a kick, clientkick or tempban vote called by an
    ## unprivileged player kicks the caller instead when it fails.

    @minqlxtended.hook("vote_started", priority=minqlxtended.Priority.LOWEST)
    def handle_vote_started(self, caller, vote, args):
        pending, self._glasshouse_pending = self._glasshouse_pending, None

        if not self._qlx_glasshouse:
            return

        # caller is None for votes a plugin started via minqlxtended.callvote(). Our own
        # registered votes pass the calling player through.
        if caller is None:
            return

        vote = vote.lower().strip()
        is_kick_vote = vote in ("kick", "clientkick")
        is_our_tempban = (vote == minqlxtended.CUSTOM_VOTES.EXECUTE_COMMAND
                          and pending == caller.steam_id)
        if (is_kick_vote or is_our_tempban) and (not self.db.has_permission(caller, 1)):
            self._glasshouse_armed = caller.steam_id
            self.msg(f"^3If this vote fails, ^7{caller.name}^3 will be kicked instead.")

    @minqlxtended.hook("vote_ended", priority=minqlxtended.Priority.LOWEST)
    def handle_glasshouse_vote_ended(self, votes, vote, args, passed):
        steam_id, self._glasshouse_armed = self._glasshouse_armed, None
        if passed or steam_id is None:
            return

        # Re-resolve now, so we kick whoever holds that SteamID64 at this moment, or
        # nobody, if they already left.
        caller = self.player(steam_id)
        if caller is not None:
            caller.kick("was kicked for calling an unsuccessful kick/ban vote.")

    @minqlxtended.hook("new_game")
    def handle_new_game(self):
        # A vote still open when the map loads never produces the falling edge of
        # level->voteTime that vote_ended needs, so the next failed vote would kick whoever
        # armed it a map ago.
        self._glasshouse_pending = None
        self._glasshouse_armed = None

    ## Vote callbacks. Each returns a CustomVote to start its vote, or None after
    ## telling the caller why not. The framework announces the vote and casts the
    ## caller's own yes.

    @minqlxtended.vote("randommap", description="Randomly picks a map and calls it as a vote.")
    def vote_randommap(self, caller, args):
        essentials = self.plugin("essentials")
        if essentials is None:
            caller.tell("The ^4essentials^7 plug-in isn't currently loaded. This vote cannot function.")
            return None

        mappool = essentials.mappool
        if not mappool:
            caller.tell("No map pool is configured on this server, so a random map can't be chosen.")
            return None

        target_map, target_factory = random.choice(list(mappool.items()))
        target_factory = random.choice(target_factory)
        return minqlxtended.CustomVote(f"random map {target_map} {target_factory}",
                                       f"map {target_map} {target_factory}")

    @minqlxtended.vote("infiniteammo", description="Enables infinite ammo on all weapons.")
    def vote_infiniteammo(self, caller, args):
        return self._toggle_vote("g_infiniteAmmo", "infinite ammo")

    @minqlxtended.vote("freecam", description="Enables free-camming around the arena in a team-based game.")
    def vote_freecam(self, caller, args):
        return self._toggle_vote("g_teamSpecFreeCam", "team spectator free cam")

    @minqlxtended.vote("floordamage", description="Permits damage to go through floors/walls/surfaces etc.")
    def vote_floordamage(self, caller, args):
        return self._toggle_vote("g_forceDmgThroughSurface", "damage through floors/walls")

    @minqlxtended.vote("crouchslide", description="Enable/disable Q4-style crouch sliding.")
    def vote_crouchslide(self, caller, args):
        # return self._toggle_vote("pmove_CrouchSlide", "crouch sliding")
        caller.tell("Voting to modify crouch sliding is disabled on this server.")
        return None

    @minqlxtended.vote("alltalk", description="Enables voice communication between teams during the game.")
    def vote_alltalk(self, caller, args):
        return self._toggle_vote("g_allTalk", "voice chat between teams")

    @minqlxtended.vote("allready", description="Forces the game to start.")
    def vote_allready(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("You can't vote to begin the game when the game is already on.")
            return None

        return minqlxtended.CustomVote("begin game now", "allready")

    @minqlxtended.vote("abort", description="Abort the current game.")
    def vote_abort(self, caller, args):
        if self.game.state == minqlxtended.GameState.WARMUP:
            caller.tell("You can't vote to abort the game when the game isn't in progress.")
            return None

        return minqlxtended.CustomVote("abort the game", "abort")

    @minqlxtended.vote("chatsounds", description="Enables the chat-activated sounds triggered by words.")
    def vote_chatsounds(self, caller, args):
        return self._plugin_toggle_vote("fun", "chat-activated sounds")

    @minqlxtended.vote("balancing", description="Enables/disables the elo/glicko team balancing system.")
    def vote_balancing(self, caller, args):
        return self._plugin_toggle_vote("balance", "glicko-based team balancing")

    @minqlxtended.vote(("silence", "mute"), usage="<id>", description="Silences a player for 10 minutes.")
    def vote_silence(self, caller, args):
        if self.plugin("silence") is None:
            caller.tell("The ^6silence^7 plug-in isn't currently loaded. This vote cannot function.")
            return None

        target_player = self._target_player(caller, args)
        if target_player is None:
            return None

        # Mirrors the threshold silence.cmd_silence enforces, or a vote could pass against
        # an admin that !silence then refuses, leaving nothing for !unsilence to undo.
        if target_player.privileges != minqlxtended.Privilege.NONE or self.db.has_permission(target_player, 2):
            caller.tell("The player specified is privileged, and cannot be silenced.")
            return None

        # By SteamID64, since the slot can change hands in the 30 seconds a vote is open.
        # Leave the muting to !silence, which records it; a bare `mute` would run even
        # when !silence declined.
        steam_id = target_player.steam_id
        return minqlxtended.CustomVote(f"silence {target_player.clean_name} for 10 minutes",
                                       lambda: self._execute_silence(steam_id))

    @minqlxtended.vote("tempban", usage="<id>", description="Ban the specified player until the map changes.")
    def vote_tempban(self, caller, args):
        if self._qlx_disablePlayerRemoval:
            # Either a QL privilege or a minqlxtended permission is enough on its own,
            # hence the `and`. Admins who were never !addmod'd still hold a privilege.
            if caller.privileges == minqlxtended.Privilege.NONE and (not self.db.has_permission(caller, 1)):
                caller.tell("Voting to tempban is disabled on this server.")
                caller.tell("^2/cv spec <id>^7 and ^2/cv silence <id>^7 exist as substitutes to kicking/tempbanning.")
                return None

        target_player = self._target_player(caller, args)
        if target_player is None:
            return None

        if target_player.privileges != minqlxtended.Privilege.NONE or self.db.has_permission(target_player, 1):
            caller.tell("The player specified is either privileged or banned, and cannot be tempbanned.")
            return None

        steam_id, name = target_player.steam_id, target_player.clean_name
        # The engine sees this as an opaque qlx_custom_vote token, so handle_vote_started
        # can't recognise it by name. Flag it here and confirm when the vote starts.
        self._glasshouse_pending = caller.steam_id
        return minqlxtended.CustomVote(f"^1ban {name} until the map changes",
                                       lambda: self._execute_tempban(steam_id, name))

    @minqlxtended.vote("spec", usage="<id>", description="Move the player specified to the spectators.")
    def vote_spec(self, caller, args):
        target_player = self._target_player(caller, args)
        if target_player is None:
            return None

        if target_player.team == minqlxtended.Team.SPECTATOR:
            caller.tell("That player is already in the spectators.")
            return None

        steam_id, name = target_player.steam_id, target_player.clean_name
        return minqlxtended.CustomVote(f"move {name} to the spectators",
                                       lambda: self._execute_spec(steam_id, name))

    @minqlxtended.vote("excessive", usage="[on/off]", description="Enables/disables excessive weapons.")
    def vote_excessive(self, caller, args):
        args = args.strip().lower()
        if self.game.state != minqlxtended.GameState.WARMUP and args == "on":
            caller.tell("Voting to alter excessive weapons is only allowed during the warm-up period.")
            return None

        if args in ("on", "off"):
            enabled = args == "on"
            return minqlxtended.CustomVote(f"excessive weapons: {args}",
                                           lambda: self._apply_excessive_weapons(enabled))

        caller.tell("^2/cv excessive [on/off]^7 is the usage for this callvote command.")
        return None

    @minqlxtended.vote("lock", usage="(team)", description="Lock both or specified team(s).")
    def vote_lock(self, caller, args):
        args = args.strip().lower()
        # An empty argument locks every team.
        if not args:
            return minqlxtended.CustomVote("lock all teams", "lock")
        if args == "blue":
            return minqlxtended.CustomVote("lock the ^4blue^3 team", "lock blue")
        if args == "red":
            return minqlxtended.CustomVote("lock the ^1red^3 team", "lock red")

        caller.tell("^2/cv lock^7 or ^2/cv lock <blue/red>^7 is the usage for this callvote command.")
        return None

    @minqlxtended.vote("unlock", usage="(team)", description="Unlock both or specified team(s).")
    def vote_unlock(self, caller, args):
        args = args.strip().lower()
        if not args:
            return minqlxtended.CustomVote("unlock all teams", "unlock")
        if args == "blue":
            return minqlxtended.CustomVote("unlock the ^4blue^3 team", "unlock blue")
        if args == "red":
            return minqlxtended.CustomVote("unlock the ^1red^3 team", "unlock red")

        caller.tell("^2/cv unlock^7 or ^2/cv unlock <blue/red>^7 is the usage for this callvote command.")
        return None

    @minqlxtended.vote("roundtimelimit", usage="[90/120/180]", description="Changes the round time limit (specified in seconds).")
    def vote_roundtimelimit(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to alter the round time limit is only allowed during the warm-up period.")
            return None

        return self._limit_vote(caller, "roundtimelimit", args.strip().lower(), ["90", "120", "180"], "round time limit")

    @minqlxtended.vote("balance", description="Balances the teams using the glicko algorithm.")
    def vote_balance(self, caller, args):
        if self.plugin("balance") is None:
            caller.tell("The ^6balance^7 plug-in isn't currently loaded. This vote cannot function.")
            return None

        teams = self.teams()
        if ((len(teams["red"]) + len(teams["blue"])) % 2 != 0) or ((len(teams["red"]) + len(teams["blue"])) == 0):
            caller.tell("Voting to balance isn't possible while the number of players across both teams is uneven.")
            caller.tell(
                f"There are ^1{len(teams['red'])}^7 player{'s' if len(teams['red']) != 1 else ''} on red, and ^4{len(teams['blue'])}^7 player{'s' if len(teams['blue']) != 1 else ''} on blue."
            )
            return None

        return minqlxtended.CustomVote("balance the teams", self._start_balance)

    @minqlxtended.vote("lgammo", usage="[150/200]", description="Change starting lightning gun ammo.")
    def vote_lgammo(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to alter lightning gun ammo is only allowed during the warm-up period.")
            return None

        return self._limit_vote(caller, "g_startingAmmo_lg", args.strip().lower(), ["150", "200"], "lightning gun ammo")

    @minqlxtended.vote("glammo", usage="[5/10]", description="Change starting grenade launcher ammo.")
    def vote_glammo(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to alter grenade launcher ammo is only allowed during the warm-up period.")
            return None

        return self._limit_vote(caller, "g_startingAmmo_gl", args.strip().lower(), ["10", "5"], "grenade launcher ammo")

    @minqlxtended.vote("lgdamage", usage="[6/7]", description="Changes Lightning Gun damage/knockback.")
    def vote_lgdamage(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to alter lightning gun damage is only allowed during the warm-up period.")
            return None

        args = args.strip().lower()
        if args == "6":
            return minqlxtended.CustomVote("^7Lightning gun damage: 6", "set g_damage_lg 6; set g_knockback_lg 1.75")
        if args == "7":
            return minqlxtended.CustomVote("^7Lightning gun damage: 7 (with appropriate knockback)", "set g_damage_lg 7; set g_knockback_lg 1.50")

        caller.tell("^2/cv lgdamage [6/7]^7 is the usage for this callvote command.")
        return None

    @minqlxtended.vote("rgdamage", usage="[80/100]", description="Changes Railgun damage.")
    def vote_rgdamage(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to alter railgun damage is only allowed during the warm-up period.")
            return None

        return self._limit_vote(caller, "g_damage_rg", args.strip().lower(), ["80", "100"], "railgun damage")

    @minqlxtended.vote("rounddelay", usage="[3/5/7/10]", description="Round delay between rounds (in seconds).")
    def vote_rounddelay(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to alter the per-round countdown delay is only allowed during the warm-up period.")
            return None

        args = args.strip().lower()
        if args not in ("3", "5", "7", "10"):
            caller.tell("^2/cv rounddelay [3/5/7/10]^7 is the usage for this callvote command.")
            return None

        return minqlxtended.CustomVote(f"per-round countdown delay: {args} seconds",
                                       f"set g_roundWarmupDelay {int(args) * 1000};")

    @minqlxtended.vote("runes", description="Enables/disables runes.")
    def vote_runes(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to alter runes is only allowed during the warm-up period.")
            return None

        return self._toggle_vote("g_runes", "runes", map_restart=True)

    @minqlxtended.vote("cvar", usage="<cvar> <value>", description="Change the cvar specified.")
    def vote_cvar(self, caller, args):
        if self._qlx_disableCvarVoting:
            caller.tell("Voting to change server CVARs is disabled on this server.")
            return None

        # Matched against the un-lowercased argument, since a vote that carries a *value*
        # through to the engine needs it verbatim.
        raw_args = args.strip()
        match = _RE_CVAR_VOTE.match(raw_args)
        if match is None:
            caller.tell("^2/cv cvar <variable> <value>^7 is the usage for this callvote command.")
            caller.tell("The value cannot contain ^6; \" \\^7 or newlines.")
            return None

        name = match.group("name")
        lowered = name.lower()
        if lowered in _BLOCKED_CVARS or lowered.startswith(_BLOCKED_CVAR_PREFIXES):
            caller.tell(f"^6{name}^7 cannot be changed by a vote on this server.")
            return None

        required = self._qlx_cvarVotePermissionRequired
        if not self.db.has_permission(caller, required):
            caller.tell(f"^1Insufficient privileges to change a server cvar.^7 Permission Level required: ^6{required}^7.")
            return None

        return minqlxtended.CustomVote(f"Server CVAR change: {raw_args}^3",
                                       f'set {name} "{match.group("value")}"')

    @minqlxtended.vote("do", usage="[now/later]", description="Forces the suggested switch now, or at the start of the next round.")
    def vote_do(self, caller, args):
        args = args.strip().lower()
        if len(args) <= 1:
            caller.tell("Please use one of the following options:")
            caller.tell("  ^2/cv do later^7 forces the switch at the beginning of the next round.")
            caller.tell("  ^2/cv do now^7 forces the switch at the end of the vote.")
            return None

        balance = self.plugin("balance")
        if balance is None:
            caller.tell("The ^6balance^7 plug-in isn't currently loaded. This vote cannot function.")
            return None

        if not balance.suggested_pair:
            caller.tell("A switch hasn't been suggested yet by ^6!teams^7, a suggestion is required before ^2do^7 can execute.")
            return None

        if args == "now":
            return minqlxtended.CustomVote("force the suggested switch now", self._execute_do_now)
        if args == "later":
            return minqlxtended.CustomVote("force the suggested switch at the start of the next round", self._execute_do_later)

        caller.tell("You have specified an invalid argument, either ^2now^7 or ^2later^7 are accepted arguments.")
        return None

    @minqlxtended.vote("reboot", description="Restarts the Quake server (takes 5 seconds).")
    def vote_reboot(self, caller, args):
        if self._qlx_disableServerRebootVote:
            caller.tell("Voting to reboot is disabled on this server.")
            return None

        return minqlxtended.CustomVote("reboot the ^1QUAKE LIVE^3 server", self._begin_reboot)

    @minqlxtended.vote("go", description="Balances and begins the game.")
    def vote_go(self, caller, args):
        if self.game.state != minqlxtended.GameState.WARMUP:
            caller.tell("Voting to go is not permitted during an active game.")
            return None

        responses = [
            "let's get a move on already",
            "let's get going",
            "don't be a scrote, let's get on with it",
            "are we playing or what?",
            "you layabouts, let's get on with it!",
            "F3 dudes",
        ]
        return minqlxtended.CustomVote(random.choice(responses), self._execute_go)

    @minqlxtended.vote("servershift", usage="<1-32>", description="Shifts all players to the specified server number.")
    def vote_servershift(self, caller, args):
        try:
            server_id = int(args.strip())
            server_port = (server_id - 1) + 27960
            if server_id > 32 or server_id < 1:
                raise ValueError
        except ValueError:
            caller.tell("Server ID must be specified as a number between ^61^7 and ^632^7 (Server #^61^7, #^62^7 etc.)")
            return None

        if caller.team == minqlxtended.Team.SPECTATOR and (not self.db.has_permission(caller, 1)):
            caller.tell("Voting to server shift can be done by in-match players only.")
            return None

        if self.game.state != minqlxtended.GameState.WARMUP and (not self.db.has_permission(caller, 1)):
            caller.tell("Voting to server shift is allowed during warm-up only.")
            return None

        if server_port == self.get_cvar("net_port", int):
            caller.tell("Voting to server shift to the same server is not permitted.")
            return None

        return minqlxtended.CustomVote(f"shift to server number #{server_id}",
                                       lambda: self._forceconnect_all(server_port))

    @minqlxtended.vote("grapple", description="Enable/disable the grappling hook.")
    def vote_grapple(self, caller, args):
        # weapon_t starts at 1 and g_startingWeapons reserves no bit for its 0, so the
        # grappling hook is 1 << (Weapon.GRAPPLING_HOOK - 1) == 512. Shifting by the member
        # itself gives 1024, which is the nailgun.
        g_startingWeapons, enabled = minqlxtended.toggle_starting_weapon(
            self.get_cvar("g_startingWeapons", int), minqlxtended.Weapon.GRAPPLING_HOOK)
        word = "on" if enabled else "off"

        return minqlxtended.CustomVote(f"grappling hook: {word}",
                                       f"set g_startingWeapons {g_startingWeapons}")

    ## Shared callback machinery.

    def _toggle_vote(self, cvar, vote_text, map_restart=False):
        if self.get_cvar(cvar, bool):
            value, word = "0", "off"
        else:
            value, word = "1", "on"

        execute = f"set {cvar} {value}; map_restart" if map_restart else f"set {cvar} {value}"
        return minqlxtended.CustomVote(f"{vote_text}: {word}", execute)

    def _limit_vote(self, caller, cvar, value, valid_values, vote_text, map_restart=False):
        if self.get_cvar(cvar) == value:
            caller.tell(f"The {vote_text} is already set to ^6{value}^7.")
            return None

        if value not in valid_values:
            caller.tell(f"Invalid value specified for the ^3{vote_text}^7 vote.")
            caller.tell(f"  Acceptable values are ^2{'^7, ^2'.join(valid_values)}^7.")
            return None

        execute = f"set {cvar} {value}; map_restart" if map_restart else f"set {cvar} {value}"
        return minqlxtended.CustomVote(f"{vote_text}: {value}", execute)

    def _plugin_toggle_vote(self, plugin_name, vote_text):
        load = self.plugin(plugin_name) is None
        word = "on" if load else "off"
        return minqlxtended.CustomVote(f"{vote_text}: {word}",
                                       lambda: self._set_plugin_loaded(plugin_name, load))

    def _target_player(self, caller, args):
        """The player the caller named by client id, or None after telling them why not."""
        try:
            target_player = self.player(int(args.strip()))
        except (ValueError, minqlxtended.NonexistentPlayerError):
            target_player = None

        if not target_player:
            caller.tell("^1Invalid ID.^7 Use a client ID from the ^2/players^7 command.")
            return None

        return target_player

    def _player_by_steam_id(self, steam_id):
        for p in self.players():
            if p.steam_id == steam_id:
                return p
        return None

    ## Execute paths for the callable votes. These run when the engine executes the
    ## passed vote, a few seconds after the result.

    def _execute_silence(self, steam_id):
        if self.plugin("silence") is None:
            self.msg("The ^6silence^7 plug-in is no longer loaded; the silence was not recorded.")
            return

        minqlxtended.console_command(
            f"qlx !silence {steam_id} 10 minutes You were voted silent for 10 minutes.")

    def _execute_tempban(self, steam_id, name):
        # Resolve by SteamID64 here, at execution: the slot id could have changed hands
        # during the 30 seconds the vote was open.
        target_player = self._player_by_steam_id(steam_id)
        if target_player is None:
            self.msg(f"^6{name}^7 left before the vote passed; nobody was tempbanned.")
            return

        minqlxtended.console_command(f"tempban {target_player.id}")

    def _execute_spec(self, steam_id, name):
        target_player = self._player_by_steam_id(steam_id)
        if target_player is None:
            self.msg(f"^6{name}^7 left before the vote passed; nobody was moved.")
            return

        minqlxtended.console_command(f"put {target_player.id} spec")

    def _set_plugin_loaded(self, plugin_name, loaded):
        try:
            if loaded and self.plugin(plugin_name) is None:
                minqlxtended.load_plugin(plugin_name)
            elif not loaded and self.plugin(plugin_name) is not None:
                minqlxtended.unload_plugin(plugin_name)
        except Exception:
            self.logger.exception(f"Failed to {'load' if loaded else 'unload'} the {plugin_name} plugin.")

    def _start_balance(self):
        # Through the console rather than balance's internals, since cmd_balance owns the
        # gametype and even-team validation and its rating fetch is callback-driven.
        if self.plugin("balance") is None:
            self.msg("The ^6balance^7 plug-in is no longer loaded, so the teams were not balanced.")
            return

        minqlxtended.console_command("qlx !balance")

    def _execute_do_now(self):
        balance = self.plugin("balance")
        if balance is not None and balance.suggested_pair:
            balance.execute_suggestion()

    def _execute_do_later(self):
        balance = self.plugin("balance")
        if balance is None or balance.suggested_pair is None:
            return

        balance.suggested_agree[0] = True
        balance.suggested_agree[1] = True
        self.msg("The switch will occur at the beginning of the next round.")

    def _execute_go(self):
        self._start_balance()
        game = self.game
        if game is not None and game.state == minqlxtended.GameState.WARMUP:
            game.allready()
