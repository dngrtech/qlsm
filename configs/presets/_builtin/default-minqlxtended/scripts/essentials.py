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
import datetime
import itertools
import time
import re
import os

from random import randint
from collections import deque

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TIME_FORMAT = "%H:%M:%S"

class essentials(minqlxtended.Plugin):
    _qlx_commandPrefix = minqlxtended.setting("qlx_commandPrefix", "!")
    _qlx_votepass = minqlxtended.setting("qlx_votepass", True)
    _qlx_votepassThreshold = minqlxtended.setting("qlx_votepassThreshold", 0.33, minimum=0, maximum=1)
    _qlx_teamsizeMinimum = minqlxtended.setting("qlx_teamsizeMinimum", 1)
    _qlx_teamsizeMaximum = minqlxtended.setting("qlx_teamsizeMaximum", 8)
    _qlx_enforceMappool = minqlxtended.setting("qlx_enforceMappool", False)

    def __init__(self):
        super().__init__()

        # Vote counter. We use this to avoid automatically passing votes we shouldn't.
        self.vote_count = itertools.count()
        self.last_vote = 0

        # A short history of recently executed commands.
        self.recent_cmds = deque(maxlen=11)
        # A short history of recently disconnected players.
        self.recent_dcs = deque(maxlen=10)

        # Map voting stuff. fs_homepath takes precedence.
        self.mappool = None
        mphome = os.path.join(self.get_cvar("fs_homepath", str), "baseq3", self.get_cvar("sv_mappoolfile"))
        if os.path.isfile(mphome):
            self.mappool = self.parse_mappool(mphome)
        else:
            mpbase = os.path.join(self.get_cvar("fs_basepath", str), "baseq3", self.get_cvar("sv_mappoolfile"))
            if os.path.isfile(mpbase):
                self.mappool = self.parse_mappool(mpbase)

    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot):
        # The engine reads stay on the game thread. The Redis round-trips go to a worker
        # and the welcome line comes back through the `then` callback.
        clean_name = player.clean_name
        self.run_in_thread(self.update_player, player.steam_id, player.name, player.ip,
                           then=lambda is_new: self.welcome_new_player(clean_name, is_new))

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        self.recent_dcs.appendleft((player, time.time()))
        self.run_in_thread(self.update_seen_player, player.steam_id)

    @minqlxtended.hook("vote_called")
    def handle_vote_called(self, caller, vote, args):
        # Enforce teamsize min/max limits.
        vote = vote.lower().strip()
        if vote == "teamsize":
            try:
                args = int(args)
            except ValueError:
                return

            if args > self._qlx_teamsizeMaximum:
                caller.tell(f"The team size is larger than what the server allows (maximum of ^6{self._qlx_teamsizeMaximum}^7)")
                return minqlxtended.Return.STOP_ALL
            elif args < self._qlx_teamsizeMinimum:
                caller.tell(f"The team size is smaller than what the server allows (minimum of ^6{self._qlx_teamsizeMinimum}^7.)")
                return minqlxtended.Return.STOP_ALL

        # Enforce map pool.
        if (vote == "map") and (self.mappool) and (self._qlx_enforceMappool):
            split_args = args.split()
            if len(split_args) == 0:
                caller.tell("Available maps and factories:")
                self.tell_mappool(caller, indent=2)
                return minqlxtended.Return.STOP_ALL

            map_name = split_args[0].lower()
            factory = split_args[1] if len(split_args) > 1 else self.game.factory
            if map_name in self.mappool:
                if factory and factory not in self.mappool[map_name]:
                    caller.tell(f"This factory is not allowed on that map. Use ^6{self._qlx_commandPrefix}mappool^7 to see available options.")
                    return minqlxtended.Return.STOP_ALL
            else:
                caller.tell(f"This map is not allowed. Use ^6{self._qlx_commandPrefix}mappool^7 to see available options.")
                return minqlxtended.Return.STOP_ALL

    @minqlxtended.hook("vote_started")
    def handle_vote_started(self, caller, vote, args):
        if self._qlx_votepass:
            self.last_vote = next(self.vote_count)
            self.force(self._qlx_votepassThreshold, self.last_vote)

    @minqlxtended.hook("command", priority=minqlxtended.Priority.LOW)
    def handle_command(self, caller, command, args):
        self.recent_cmds.appendleft((caller, command, args))

    @minqlxtended.hook("client_command")
    def handle_client_command(self, player, command):
        command = command.lower().strip()
        if command == "players":
            self.send_player_list(player)
            return minqlxtended.Return.STOP_ALL
        elif command == "players.":
            self.send_player_list(player, ease_sight=True)
            return minqlxtended.Return.STOP_ALL

    @minqlxtended.command(("id", "players"), client_cmd_perm=0)
    def cmd_list_players(self, player, msg, channel):
        """Sends the player list to the caller."""
        self.send_player_list(player)
        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command(("disconnects", "dcs"), permission=1)
    def cmd_disconnects(self, player, msg, channel):
        """Sends the list of most recent player disconnects to the caller."""
        if len(self.recent_dcs) == 0:
            player.tell("No players have disconnected yet.")
        else:
            self.reply_lines(player, [f"The most recent ^6{len(self.recent_dcs)}^7 player disconnects:"]
                             + [f"  {p.name} ({p.steam_id}): ^6{round(time.time() - t)}^7 seconds ago"
                                for p, t in self.recent_dcs])

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command(("commands", "cmds"), permission=2)
    def cmd_commands(self, player, msg, channel):
        """Sends the list of the most recently used commands to the caller."""
        if len(self.recent_cmds) == 1:
            player.tell("No commands have been recorded yet.")
        else:
            viewer_perm = self.db.get_permission(player)
            lines = [f"The most recent ^6{len(self.recent_cmds) - 1}^7 commands executed:"]
            for caller, command, args in list(self.recent_cmds)[1:]:
                # Don't leak the arguments of commands the viewer isn't allowed to
                # run (e.g. rcon/eval/db arguments typed by higher-permission admins).
                if getattr(command, "permission", 0) > viewer_perm:
                    args = "<hidden>"
                lines.append(f"  {caller.name} executed: {args}")
            self.reply_lines(player, lines)

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("shuffle", permission=1, client_cmd_perm=1)
    def cmd_shuffle(self, player, msg, channel):
        """Forces a shuffle instantly."""
        self.game.shuffle()

    @minqlxtended.command(("pause", "timeout"), permission=1)
    def cmd_pause(self, player, msg, channel):
        """Pauses the game."""
        self.game.pause()

    @minqlxtended.command(("unpause", "timein"), permission=1)
    def cmd_unpause(self, player, msg, channel):
        """Unpauses the game."""
        self.game.unpause()

    @minqlxtended.command("slap", permission=2, usage="<id> [damage]")
    def cmd_slap(self, player, msg, channel):
        """Slaps a player with optional damage specified."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], player, "Invalid ID.")
        if target_player is None:
            return minqlxtended.Return.STOP_ALL

        if len(msg) > 2:
            try:
                dmg = int(msg[2])
            except ValueError:
                player.tell("Invalid damage value.")
                return minqlxtended.Return.STOP_ALL
        else:
            dmg = 0

        try:
            self.game.slap(target_player, dmg)
        except ValueError:
            # Dead, or spectating. The slot resolved, so it isn't a bad id.
            player.tell(f"{target_player.name}^7 is not alive to be slapped.")
            return minqlxtended.Return.STOP_ALL

        if dmg:
            self.msg(f"{target_player.name}^7 was slapped for {dmg} damage!")
        else:
            self.msg(f"{target_player.name}^7 was slapped!")

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("slay", permission=2, usage="<id>")
    def cmd_slay(self, player, msg, channel):
        """Kills the specified player instantly."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], player, "Invalid ID.")
        if target_player is None:
            return minqlxtended.Return.STOP_ALL

        self.game.slay(target_player)
        self.msg(f"{target_player.name}^7 was slain!")
        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("sounds", client_cmd_perm=0, usage="<0/1>")
    def cmd_enable_sounds(self, player, msg, channel):
        """Prevents custom sounds from playing for the calling player. Use again to re-enable these sounds."""
        flag = self.db.get_flag(player, "essentials:sounds_enabled", default=True)
        self.db.set_flag(player, "essentials:sounds_enabled", not flag)

        word = "enabled" if (not flag) else "disabled"

        player.tell(f"Sounds have been ^6{word}^7. Use ^6{self._qlx_commandPrefix}sounds^7 to change this again.")

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("sound", permission=1, usage="<path>")
    def cmd_sound(self, player, msg, channel):
        """Plays a sound for the those who have it enabled."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        if not self.db.get_flag(player, "essentials:sounds_enabled", default=True):
            player.tell(f"Sounds are disabled. Use ^6{self._qlx_commandPrefix}sounds^7 to enable them again.")
            return minqlxtended.Return.STOP_ALL

        # play_sound validates the path as it builds the command, so an invalid one raises
        # on the first iteration with nothing sent. An rcon caller has no slot to hear it.
        try:
            for p in self._sounds_enabled_players(self.players()):
                self.play_sound(msg[1], p)
        except ValueError as e:
            player.tell(f"Invalid sound: {e}")

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("music", permission=1, usage="<path>")
    def cmd_music(self, player, msg, channel):
        """Plays music, but only for those with music volume on and the sounds flag on."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        if not self.db.get_flag(player, "essentials:sounds_enabled", default=True):
            player.tell(f"Sounds are disabled. Use ^6{self._qlx_commandPrefix}sounds^7 to enable them again.")
            return minqlxtended.Return.STOP_ALL

        # Play to everyone who hasn't disabled sounds. See cmd_sound.
        try:
            for p in self._sounds_enabled_players(self.players()):
                self.play_music(msg[1], p)
        except ValueError as e:
            player.tell(f"Invalid music: {e}")

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("stopsound", permission=1)
    def cmd_stopsound(self, player, msg, channel):
        """Stops all sounds playing. Useful if someone plays one of those really long ones."""
        if not self.db.get_flag(player, "essentials:sounds_enabled", default=True):
            player.tell(f"Sounds are disabled. Use ^6{self._qlx_commandPrefix}sounds^7 to enable them again.")
            return minqlxtended.Return.STOP_ALL

        self.stop_sound()

    @minqlxtended.command("stopmusic", permission=1)
    def cmd_stopmusic(self, player, msg, channel):
        """Stops any music playing."""
        if not self.db.get_flag(player, "essentials:sounds_enabled", default=True):
            player.tell(f"Sounds are disabled. Use ^6{self._qlx_commandPrefix}sounds^7 to enable them again.")
            return minqlxtended.Return.STOP_ALL

        self.stop_music()

    @minqlxtended.command("kick", permission=2, usage="<id>")
    def cmd_kick(self, player, msg, channel):
        """Kicks a player. A reason can also be provided, which appears for the player in the 'server disconnected' dialog."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        if len(msg) > 2:
            target_player.kick(" ".join(msg[2:]))
        else:
            target_player.kick()

    @minqlxtended.command(("kickban", "tempban"), permission=2, usage="<id>")
    def cmd_kickban(self, player, msg, channel):
        """Kicks a player and prevent the player from joining for the remainder of the current map."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.tempban()

    @minqlxtended.command("yes", permission=2)
    def cmd_yes(self, player, msg, channel):
        """Passes the currently active vote."""
        if self.is_vote_active():
            self.force_vote(True)
        else:
            channel.reply("There is no active vote!")

    @minqlxtended.command("no", permission=2)
    def cmd_no(self, player, msg, channel):
        """Vetoes the currently active vote."""
        if self.is_vote_active():
            self.force_vote(False)
        else:
            channel.reply("There is no active vote!")

    @minqlxtended.command("random", permission=1, usage="<limit>")
    def cmd_random(self, player, msg, channel):
        """Presents a random number in chat."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        try:
            n = randint(1, int(msg[1]))
        except ValueError:
            player.tell("Invalid upper limit. Use a positive integer.")
            return minqlxtended.Return.STOP_ALL

        channel.reply(f"^3Random number is: ^5{n}^7")

    @minqlxtended.command("cointoss", permission=1)
    def cmd_cointoss(self, player, msg, channel):
        """Tosses a coin, and returns HEADS or TAILS in chat."""
        channel.reply(f"^3The coin is: ^5{'HEADS' if randint(0, 1) else 'TAILS'}^7")

    @minqlxtended.command(("switch", "swap"), permission=1, usage="<id> <id>")
    def cmd_switch(self, player, msg, channel):
        """Switches the teams of the two players specified."""
        if len(msg) < 3:
            return minqlxtended.Return.USAGE

        player1 = self.resolve_player(msg[1], channel, "The first ID is invalid.")
        if player1 is None:
            return

        player2 = self.resolve_player(msg[2], channel, "The second ID is invalid.")
        if player2 is None:
            return

        self.game.switch(player1, player2)

    @minqlxtended.command("red", permission=1, usage="<id>")
    def cmd_red(self, player, msg, channel):
        """Moves the specified player to the red team."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.put("red")

    @minqlxtended.command("blue", permission=1, usage="<id>")
    def cmd_blue(self, player, msg, channel):
        """Moves the specified player to the blue team."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.put("blue")

    @minqlxtended.command(("spectate", "spec", "spectator"), permission=1, usage="<id>")
    def cmd_spectate(self, player, msg, channel):
        """Moves the specified player to the spectator team."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.put("spectator")

    @minqlxtended.command("free", permission=1, usage="<id>")
    def cmd_free(self, player, msg, channel):
        """Moves the specified player to the free team (the 'team' used in non-team gametypes like Free For All.)"""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.put("free")

    @minqlxtended.command("addmod", permission=5, usage="<id>")
    def cmd_addmod(self, player, msg, channel):
        """Give a player classic moderator status."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.addmod()

    @minqlxtended.command("addadmin", permission=5, usage="<id>")
    def cmd_addadmin(self, player, msg, channel):
        """Give a player classic administrator status."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.addadmin()

    @minqlxtended.command("demote", permission=5, usage="<id>")
    def cmd_demote(self, player, msg, channel):
        """Remove classic administrator/moderator status from someone."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.demote()

    @minqlxtended.command("mute", permission=1, usage="<id>")
    def cmd_mute(self, player, msg, channel):
        """Mutes the specified player."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        if target_player == player:
            channel.reply("I refuse.")
        else:
            target_player.mute()

    @minqlxtended.command("unmute", permission=1, usage="<id>")
    def cmd_unmute(self, player, msg, channel):
        """/Unmutes the specified player."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        target_player = self.resolve_player(msg[1], channel, "Invalid ID.")
        if target_player is None:
            return

        target_player.unmute()

    @minqlxtended.command("lock", permission=1, usage="[team]")
    def cmd_lock(self, player, msg, channel):
        """Locks the specified team."""
        if len(msg) > 1:
            if msg[1][0].lower() == "s":
                self.game.lock("spectator")
            elif msg[1][0].lower() == "r":
                self.game.lock("red")
            elif msg[1][0].lower() == "b":
                self.game.lock("blue")
            else:
                player.tell("Invalid team.")
                return minqlxtended.Return.STOP_ALL
        else:
            self.game.lock()

    @minqlxtended.command("unlock", permission=1, usage="[team]")
    def cmd_unlock(self, player, msg, channel):
        """Unlocks the specified team."""
        if len(msg) > 1:
            if msg[1][0].lower() == "s":
                self.game.unlock("spectator")
            elif msg[1][0].lower() == "r":
                self.game.unlock("red")
            elif msg[1][0].lower() == "b":
                self.game.unlock("blue")
            else:
                player.tell("Invalid team.")
                return minqlxtended.Return.STOP_ALL
        else:
            self.game.unlock()

    @minqlxtended.command("allready", permission=2)
    def cmd_allready(self, player, msg, channel):
        """Forces all players to ready up."""
        if self.game.state == minqlxtended.GameState.WARMUP:
            self.game.allready()
        else:
            channel.reply("But the game's already in progress, you silly goose!")

    @minqlxtended.command("abort", permission=2)
    def cmd_abort(self, player, msg, channel):
        """Forces a game currently in progress to go back to warm-up."""
        if self.game.state != minqlxtended.GameState.WARMUP:
            self.game.abort()
        else:
            channel.reply("But the game isn't even on, you doofus!")

    @minqlxtended.command(("map", "changemap"), permission=2, usage="<mapname> [factory]")
    def cmd_map(self, player, msg, channel):
        """Changes the map to the one specified (using the optionally specifiable factory.)"""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        # TODO: Give feedback on !map.
        self.change_map(msg[1], msg[2] if len(msg) > 2 else None)

    @minqlxtended.command(("help", "about", "version"), client_cmd_perm=0)
    def cmd_help(self, player, msg, channel):
        """Provide minqlxtended version information."""
        channel.reply(f"minqlxtended: ^6{minqlxtended.__version__}^7 - Plugins: ^6{minqlxtended.plugins_version()}")
        channel.reply("See ^4github.com/tjone270/minqlxtended^7 for more information.")
        channel.reply("See ^4thepurgery.com/customcommands^7 for the commands list.")

    @minqlxtended.command("firstseen", usage="<id>/<steam_id>")
    def cmd_first_seen(self, player, msg, channel):
        """Responds with the first time a player was seen on the server."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        steam_id, _, target_player = resolved

        if target_player:
            name = target_player.name + "^7"
        else:
            name = "that player" if steam_id != minqlxtended.owner() else "my ^4master^7"

        key = f"minqlx:players:{steam_id}:first_seen"
        if key in self.db:
            then = datetime.datetime.strptime(self.db[key], DATETIME_FORMAT)
            td = datetime.datetime.now() - then
            r = re.match(r"((?P<d>.*) days*, )?(?P<h>..?):(?P<m>..?):.+", str(td))
            if r.group("d"):
                channel.reply(
                    f"^7I first saw {name} ^6{int(r.group('d'))}^7 day{self.plural(r.group('d'))}, ^6{int(r.group('h'))}^7 hour{self.plural(r.group('h'))} and ^6{int(r.group('m'))}^7 minute{self.plural(r.group('m'))} ago."
                )
            else:
                channel.reply(
                    f"^7I first saw {name} ^6{int(r.group('h'))}^7 hour{self.plural(r.group('h'))} and ^6{int(r.group('m'))}^7 minute{self.plural(r.group('m'))} ago."
                )
        else:
            if f"minqlx:players:{steam_id}" in self.db:
                channel.reply("^7That player is ^6too old^7 to have that date recorded.")
            else:
                channel.reply(f"^7I have never seen ^6{name}^7 before.")

    @minqlxtended.command(("seen", "lastseen"), usage="<steam_id>")
    def cmd_last_seen(self, player, msg, channel):
        """Responds with the last time a player was seen on the server."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        try:
            steam_id = int(msg[1])
            if steam_id < minqlxtended.MAX_CLIENTS:
                channel.reply("Invalid SteamID64.")
                return
        except ValueError:
            channel.reply("Unintelligible SteamID64.")
            return

        p = self.player(steam_id)
        if p:
            channel.reply(f"That would be {p.name}^7, who is currently on this very server!")
            return

        key = f"minqlx:players:{steam_id}:last_seen"
        name = "that player" if steam_id != minqlxtended.owner() else "my ^6master^7"
        if key in self.db:
            then = datetime.datetime.strptime(self.db[key], DATETIME_FORMAT)
            td = datetime.datetime.now() - then
            r = re.match(r"((?P<d>.*) days*, )?(?P<h>..?):(?P<m>..?):.+", str(td))
            if r.group("d"):
                channel.reply(
                    f"^7I last saw {name} ^6{int(r.group('d'))}^7 day{self.plural(r.group('d'))}, ^6{int(r.group('h'))}^7 hour{self.plural(r.group('h'))} and ^6{int(r.group('m'))}^7 minute{self.plural(r.group('m'))} ago."
                )
            else:
                channel.reply(
                    f"^7I last saw {name} ^6{int(r.group('h'))}^7 hour{self.plural(r.group('h'))} and ^6{int(r.group('m'))}^7 minute{self.plural(r.group('m'))} ago."
                )
        else:
            channel.reply(f"^7I have never seen {name} before.")

    @minqlxtended.command("time", usage="[timezone_offset]")
    def cmd_time(self, player, msg, channel):
        """Responds with the current time."""
        tz_offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
        tz_offset = tz_offset // 60 // 60 * -1
        if len(msg) > 1:
            try:
                tz_offset = int(msg[1])
            except ValueError:
                channel.reply("Unintelligible time zone offset.")
                return
        tz = datetime.timezone(offset=datetime.timedelta(hours=tz_offset))
        now = datetime.datetime.now(tz)
        if tz_offset > 0:
            channel.reply(f"The current time is: ^6{now.strftime(TIME_FORMAT)} UTC+{tz_offset}")
        elif tz_offset < 0:
            channel.reply(f"The current time is: ^6{now.strftime(TIME_FORMAT)} UTC{tz_offset}")
        else:
            channel.reply(f"The current time is: ^6{now.strftime(TIME_FORMAT)} UTC")

    @minqlxtended.command(("teamsize", "ts"), permission=2, usage="<size>")
    def cmd_teamsize(self, player, msg, channel):
        """Alters the teamsize to that specified. If 0 is specified, remove the teamsize restriction."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        try:
            n = int(msg[1])
        except ValueError:
            channel.reply("^7Unintelligible size.")
            return

        if n < 0:  # don't know why this would be attempted - but nice to harden against unexpected behaviour
            channel.reply("The teamsize must be a positive number.")
            return
        elif n > 64:  # imaginary maximum - insane to go higher.
            channel.reply("The teamsize must be less than 64.")
            return

        self.game.teamsize = n
        if n:
            self.msg(f"The teamsize has been set to ^6{n}^7 by {player.name}^7.")
        else:
            self.msg(f"The teamsize has been set to ^6unrestricted^7 by {player.name}^7.")

        return minqlxtended.Return.STOP_ALL

    @minqlxtended.command("rcon", permission=5)
    def cmd_rcon(self, player, msg, channel):
        """Sends a console command to the server."""
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        with minqlxtended.redirect_print(channel):
            minqlxtended.console_command(" ".join(msg[1:]))

    @minqlxtended.command(("mappool", "maps", "maplist"), client_cmd_perm=0)
    def cmd_mappool(self, player, msg, channel):
        """If a map pool is currently enforced, responds with the currently allowed maps."""
        if not self.mappool:
            player.tell("The map pool is currently unavailable.")
            return

        self.tell_mappool(player)

        if not self._qlx_enforceMappool:
            player.tell("No map pool is currently enforced. You are free to vote any map.")

        return minqlxtended.Return.STOP_ALL

    # HELPERS

    def welcome_new_player(self, clean_name, is_new_player):
        if is_new_player:
            self.msg(f"^6{clean_name}^7 connected for the first time to this server, please make them feel welcome!")

    def update_player(self, steam_id, name, ip):
        """Updates the list of recent names and IPs used by the player,
        and adds entries to the player list and IP entries.

        Runs on a worker thread. The caller reads the player's details on the game
        thread and passes them in as plain values.

        """
        is_new_player = False

        base_key = f"minqlx:players:{steam_id}"
        db = self.db.pipeline()

        # Add to IP set and make IP entry.
        if ip:
            db.sadd("minqlx:ips", ip)
            db.sadd(f"minqlx:ips:{ip}", steam_id)
            db.set(f"{base_key}:last_ip", ip)
            db.sadd(f"{base_key}:ips", ip)

        # Make or update player entry.
        if base_key not in self.db:
            is_new_player = True
            db.lpush(base_key, name)
            db.sadd("minqlx:players", steam_id)
            db.set(f"{base_key}:first_seen", datetime.datetime.now().strftime(DATETIME_FORMAT))
        else:
            names = [self.clean_text(n) for n in self.db.lrange(base_key, 0, -1)]
            if self.clean_text(name) not in names:
                db.lpush(base_key, name)
                db.ltrim(base_key, 0, 19)

        if name:
            # Record the player's latest name.
            db.set(f"{base_key}:current_name", name)

        db.execute()

        return is_new_player

    def update_seen_player(self, steam_id):
        key = f"minqlx:players:{steam_id}:last_seen"
        self.db[key] = datetime.datetime.now().strftime(DATETIME_FORMAT)

    @minqlxtended.delay(29)
    def force(self, require, vote_id):
        if self.last_vote != vote_id:
            # This is not the vote we should be resolving.
            return

        votes = self.current_vote_count()
        if self.is_vote_active() and votes and votes[0] > votes[1]:
            if require:
                teams = self.teams()
                players = teams["red"] + teams["blue"] + teams["free"]
                # ZeroDivisionError if the vote resolves with nobody on a team,
                # which is when a vote gets abandoned.
                if not players:
                    return
                if sum(votes) / len(players) < require:
                    return
            minqlxtended.force_vote(True)

    def parse_mappool(self, path):
        """Read and parse the map pool file into a dictionary.

        Structure as follows:
        {'campgrounds': ['ca', 'ffa'], 'overkill': ['ca']}

        """
        mappool = {}
        try:
            with open(path, "r") as f:
                lines = f.readlines()
        except OSError:
            minqlxtended.log_exception()
            return None

        for line in lines:
            li = line.lstrip()
            # Ignore commented lines.
            if not li.startswith("#") and "|" in li:
                # Split the *stripped* line, or an indented entry keeps its leading
                # whitespace in the key and never matches a map name.
                key, value = li.split("|", 1)
                # Maps are case-insensitive, but not factories.
                key = key.lower()

                if key in mappool:
                    mappool[key].append(value.strip())
                else:
                    mappool[key] = [value.strip()]

        return mappool

    def tell_mappool(self, player, indent=0):
        out = ""
        for m in sorted(self.mappool.items(), key=lambda x: x[0]):
            out += f"Map: {' ' * indent}^6{m[0]:25}^7 Factories: ^6{', '.join(val for val in m[1])}^7\n"
        player.tell(out.rstrip("\n"))

    def plural(self, sample):
        return "s" if int(sample) != 1 else ""

    def _sounds_enabled_players(self, players):
        """Return the subset of players who haven't disabled custom sounds, reading
        every flag in one round-trip."""
        flags = self.db.get_flags(players, "essentials:sounds_enabled", default=True)
        return [p for p in players if flags[p.steam_id]]

    def send_player_list(self, target_player, ease_sight=False):
        players = self.players()
        # Every permission in one round-trip.
        owner = minqlxtended.owner()
        perm_keys = [f"minqlx:players:{p.steam_id}:permission" for p in players]
        perm_values = self.db.mget(perm_keys) if perm_keys else []
        permissions = {}
        for p, v in zip(players, perm_values):
            if p.steam_id == owner:
                permissions[p.steam_id] = 5
                continue
            try:
                # Anything unreadable is level 0, the way get_permission treats it.
                permissions[p.steam_id] = int(v) if v else 0
            except (TypeError, ValueError):
                permissions[p.steam_id] = 0

        lines = ["^6 Steam ID            ID    Ping  Perm  Player"]
        for player in players:
            type_chars = [f"^{str(permissions[player.steam_id]) * 2}^7", " "]
            if player.steam_id == owner:
                type_chars[1] = "*"  # owner
            elif player.is_bot:
                type_chars[0] = "^00^7"
                type_chars[1] = "ʙ"  # bot

            ping = player.ping
            ping_colour = "7"
            if ping > 160:
                ping_colour = "1"
            elif ping > 80:
                ping_colour = "3"
            elif ping > 0:
                ping_colour = "2"

            line = f" {player.steam_id} | {player.id:>2} | ^{ping_colour}{ping:>3}ms^7 | {''.join(type_chars)} | {player.name}"

            if ease_sight:  # fenix849
                line = line.replace(" ", ".")

            lines.append(line)

        self.reply_lines(target_player, lines)
