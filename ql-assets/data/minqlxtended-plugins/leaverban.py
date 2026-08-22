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
import time
import requests

PLAYER_KEY = "minqlx:players:{}"

# (connect, read). Without one, a hung Discord endpoint holds a worker thread, and
# with it the GIL between socket reads, for as long as the OS lets it.
DISCORD_TIMEOUT = (3.05, 10)

# Reasons that mean the server ended the connection. My_SV_DropClient dispatches
# player_disconnect for every drop it performs, so a kick, a ban or a reliable-ring overflow
# otherwise reaches the leaver path looking like a quit. A plugin kick carrying its own text
# is indistinguishable here and still gets recorded.
#
# The cycled-out string is what the client aborts with; whether QL passes it through as the
# drop reason is unconfirmed.
SERVER_DROP_REASONS = frozenset({
    "timed out",
    "Server command overflow",
    "CL_GetServerCommand: a reliable command was cycled out",
})

class leaverban(minqlxtended.Plugin):
    _qlx_leaverBan = minqlxtended.setting("qlx_leaverBan", False)
    _qlx_leaverBanRollingWindowDays = minqlxtended.setting("qlx_leaverBanRollingWindowDays", 30)
    _qlx_leaverBanMaxLeaves = minqlxtended.setting("qlx_leaverBanMaxLeaves", 3)
    _qlx_statOtherPlayersPermission = minqlxtended.setting("qlx_statOtherPlayersPermission", 1)
    _qlx_leaverBanDiscordWebhook = minqlxtended.setting("qlx_leaverBanDiscordWebhook", "")

    def __init__(self):
        super().__init__()

        # List of players playing that could potentially be considered leavers.
        self.players_start = []
        self.pending_warnings = {}

    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot):
        if is_bot:
            return

        # Check if a player has been banned for leaving, if we're doing that.
        leaver_ban_info = self.get_player_leaver_ban_info(player.steam_id)
        if not leaver_ban_info:
            return

        if leaver_ban_info["is_banned"]:
            if self.db.has_permission(player, 1):
                self.logger.info(f"Player {player.clean_name} has at least permission level 1. Not preventing connection despite leaver ban applying.")
                return

            # If the player has left too many games, ban them.
            return f"You have been banned for leaving ^6{leaver_ban_info['current_leave_count']}^7 game{('s' if leaver_ban_info['current_leave_count'] != 1 else '')} within the last ^6{self._qlx_leaverBanRollingWindowDays}^7 days. Ban resets in {leaver_ban_info['time_remaining_human']}.\n"
        elif leaver_ban_info["current_leave_count"] >= max(1, self._qlx_leaverBanMaxLeaves - 1):
            # Warn anyone within one leave of the threshold, including players at or over it
            # whose ban has expired. The max(1, ...) keeps a clean player quiet when
            # qlx_leaverBanMaxLeaves is 1.
            self.pending_warnings[player.steam_id] = leaver_ban_info

    @minqlxtended.hook("player_loaded")
    @minqlxtended.delay(4)
    def handle_player_loaded(self, player):
        # Pop it. player_loaded fires again on every map change, so an entry left behind
        # re-fires the klaxon for the rest of the session.
        ban_info = self.pending_warnings.pop(player.steam_id, None)
        if ban_info is None:
            return

        # Update first, since player might be gone in those 4 seconds.
        try:
            player.update()
        except minqlxtended.NonexistentPlayerError:
            return

        self.warn_player(player, ban_info)

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        # Pop this before any early return. handle_player_loaded is the only other thing
        # that pops it, and it never runs for someone who drops while loading.
        self.pending_warnings.pop(player.steam_id, None)

        if player.is_bot:
            return

        game = self.game
        if game is None or game.state != minqlxtended.GameState.IN_PROGRESS:
            return  # mid map change; Plugin.game hands back None rather than raising

        if player not in self.players_start:
            return

        # Removal from players_start excuses the leave. handle_game_end records everyone
        # still on the list who is missing at the end.
        if self.is_server_drop(reason):
            self.logger.info(f"Player {player.clean_name} was dropped by the server ({reason}). Not recording leave.")
            self.players_start.remove(player)
            return

        # Anything unmatched above counts as voluntary. Log the reason so
        # SERVER_DROP_REASONS can be filled in from what a live server sends.
        self.logger.debug("%s disconnected with reason %s.", player.clean_name, reason)

        if player.team not in (minqlxtended.Team.RED, minqlxtended.Team.BLUE):
            return

        # Allow people to disconnect without getting a leave if their leaving squares the
        # sides, or if the match is a 1v1.
        remaining, opposing = self.sides_after_departure(player, player.team)
        if remaining == opposing:
            self.msg(f"^6{player.clean_name}^7 disconnected to make teams even. ^2Not recording leave.^7")
            self.players_start.remove(player)
        elif remaining == 0 and opposing == 1:
            self.msg(f"^6{player.clean_name}^7 disconnected during a 1v1. ^2Not recording leave.^7")
            self.players_start.remove(player)

    @minqlxtended.hook("game_countdown")
    def handle_game_countdown(self):
        if (self._qlx_leaverBan) and (not self.is_1v1_match()):
            self.msg("Leavers are being tracked. Repeat offenders ^6will^7 be banned.")

    @minqlxtended.hook("game_start")
    @minqlxtended.delay(1)
    def handle_game_start(self):
        teams = self.teams()
        self.players_start = teams["red"] + teams["blue"]

    @minqlxtended.hook("game_end")
    def handle_game_end(self, aborted):
        # `aborted` covers forfeits: game_end reports level.matchForfeited, so a forfeited
        # match arrives with it set and nobody is recorded as having left.
        if aborted:
            self.players_start = []
            return

        teams = self.teams()
        players_end = teams["red"] + teams["blue"]
        leavers = []

        for player in self.players_start.copy():
            if player not in players_end:
                # Populate player list.
                leavers.append(player)
                # Remove leavers from initial list so we can use it to award games completed.
                self.players_start.remove(player)

        # Every write goes through this one pipeline and executes before anything reads
        # back, so finish_player_leave below sees the leave it's judging.
        db = self.db.pipeline()
        recorded = []
        for player in self.players_start:
            db.incr(PLAYER_KEY.format(player.steam_id) + ":games_completed")
        for player in leavers:
            db.incr(PLAYER_KEY.format(player.steam_id) + ":games_left")
            if self.queue_player_leave(db, player):
                recorded.append(player)
        db.execute()

        for player in recorded:
            self.finish_player_leave(player)

        if leavers:
            self.msg(f'^7Leavers: ^6{" ".join([p.clean_name for p in leavers])}')

        self.players_start = []

    @minqlxtended.hook("team_switch")
    def handle_team_switch(self, player, old_team, new_team):
        if player.is_bot:
            return

        game = self.game
        if game is None or game.state != minqlxtended.GameState.IN_PROGRESS:
            return  # mid map change; Plugin.game hands back None rather than raising

        # Allow people to spectate without getting a leave if their leaving squares the
        # sides, or if the match is a 1v1.
        if (old_team == minqlxtended.Team.RED or old_team == minqlxtended.Team.BLUE) and (new_team == minqlxtended.Team.SPECTATOR):
            if player in self.players_start:
                remaining, opposing = self.sides_after_departure(player, old_team)
                if remaining == opposing:
                    self.msg(f"^6{player.clean_name}^7 switched to spectators to make teams even. ^2Not recording leave.^7")
                    self.players_start.remove(player)
                elif remaining == 0 and opposing == 1:
                    self.msg(f"^6{player.clean_name}^7 switched to spectators during a 1v1 match. ^2Not recording leave.^7")
                    self.players_start.remove(player)

        # Add people to the list of participating players if they join mid-game.
        elif (old_team == minqlxtended.Team.SPECTATOR) and (new_team == minqlxtended.Team.RED or new_team == minqlxtended.Team.BLUE) and (player not in self.players_start):
            self.logger.info(f"Player {player.clean_name} switched from spectator to {new_team}. Now tracking for leaves.")
            self.players_start.append(player)

    @minqlxtended.command("forgive", permission=4, usage="<id> [leaves_to_forgive]")
    def cmd_forgive(self, player, msg, channel):
        """ Removes leaves from a player, starting with the oldest. Optional number can be specified to remove that amount of leaves. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        steam_id, name, _target = resolved

        # Use the correct key format for the sorted set
        leaves_key = PLAYER_KEY.format(steam_id) + ":leaves"

        # Get current leave count in the rolling window
        current_timestamp = time.time()
        cutoff_timestamp = current_timestamp - (self._qlx_leaverBanRollingWindowDays * 24 * 60 * 60)

        current_leaves = self.db.zcount(leaves_key, cutoff_timestamp, current_timestamp)

        if current_leaves <= 0:
            channel.reply(f"^6{name}^7's leaves in the last {self._qlx_leaverBanRollingWindowDays} days are already at ^6{current_leaves}^7.")
            return

        # Check if player was banned before forgiveness
        ban_info_before = self.get_player_leaver_ban_info(steam_id)
        was_banned = ban_info_before and ban_info_before.get("is_banned", False)

        # Determine number of leaves to forgive
        if len(msg) == 2:
            leaves_to_forgive = 1
        else:
            try:
                leaves_to_forgive = int(msg[2])
            except ValueError:
                channel.reply("Unintelligible number of leaves to forgive. Please use numbers.")
                return

        # Ensure we don't try to forgive more leaves than exist
        leaves_to_forgive = min(leaves_to_forgive, current_leaves)

        if leaves_to_forgive <= 0:
            channel.reply(f"^6{name}^7 has no leaves to forgive.")
            return

        # The oldest leaves *within the rolling window*. zremrangebyrank ranks over the
        # whole set, so it would remove leaves that had already aged out and leave the
        # in-window count unchanged.
        in_window = self.db.zrangebyscore(leaves_key, cutoff_timestamp, current_timestamp)
        for member in in_window[:leaves_to_forgive]:
            self.db.zrem(leaves_key, member)

        # Get the new leave count
        new_leaves = self.db.zcount(leaves_key, cutoff_timestamp, current_timestamp)

        # Check if player is still banned after forgiveness
        ban_info_after = self.get_player_leaver_ban_info(steam_id)
        is_banned_after = ban_info_after and ban_info_after.get("is_banned", False)

        if new_leaves <= 0:
            channel.reply(f"^6{name}^7's leaves have been reduced to ^60^7.")
        else:
            channel.reply(f"^6{leaves_to_forgive}^7 leave{'s' if leaves_to_forgive != 1 else ''} {'have' if leaves_to_forgive != 1 else 'has'} been forgiven (oldest first), putting ^6{name}^7 at ^6{new_leaves}^7 leave{'s' if new_leaves != 1 else ''}.")

        # Notify about ban status change
        if was_banned and not is_banned_after:
            channel.reply(f"^6{name}^7 is no longer banned.")
        elif was_banned and is_banned_after:
            time_remaining = ban_info_after.get("time_remaining_human", "unknown")
            channel.reply(f"^6{name}^7 is still banned. Ban expires in {time_remaining}.")

    @minqlxtended.command(("gamestats", "leaves"), usage="<id>")
    def cmd_gamestats(self, player, msg, channel):
        """ Returns the player's own game leave/completion statistics (or those of another player.) """
        if len(msg) < 2:  # the player wants their own leaves returned
            target_player = player
            ident = player.steam_id
        else:
            if not self.db.has_permission(player, self._qlx_statOtherPlayersPermission):
                player.tell("You do not have permission to obtain game stats for other players.")
                return minqlxtended.Return.STOP_ALL
            # assume a SteamID64 initially, unless the integer looks like a client ID
            resolved = self.resolve_identifier(msg[1], channel)
            if resolved is None:
                return
            # Keep the resolved player, or the reply below prints a bare SteamID64 even
            # when the player is standing right there.
            ident, _name, target_player = resolved

        name = target_player.clean_name if target_player else ident

        # One round-trip for both counters instead of two.
        games_left, games_completed = self.db.mget([
            f"minqlx:players:{ident}:games_left",
            f"minqlx:players:{ident}:games_completed",
        ])

        # Each counter is created by its own INCR in handle_game_end and the two loops are
        # disjoint, so a player who has never left has no games_left key. Missing counts as
        # zero, and the total guard below covers a player with no history.
        try:
            games_left = int(games_left or 0)
            games_completed = int(games_completed or 0)
        except (TypeError, ValueError):
            channel.reply(f"^6{name}^7 has unreadable game statistics.")
            return

        total = games_left + games_completed
        if total <= 0:
            channel.reply(f"^6{name}^7 has not completed or left any games.")
            return

        completion_percentage = (games_completed / total) * 100

        self.reply_lines(channel, [
            f"^6{name}^7 has completed ^6{completion_percentage:.2f}％^7 of their total games.",
            f"    ^6{games_completed}^7 game{'s' if games_completed != 1 else ''} completed.",
            f"    ^6{games_left}^7 game{'s' if games_left != 1 else ''} left.",
        ])

    @minqlxtended.command("tracked", permission=3)
    def cmd_tracked(self, player, msg, channel):
        """ Lists all players currently being tracked for leaver bans. """
        if not self._qlx_leaverBan:
            channel.reply("Leaver bans are not enabled.")
            return minqlxtended.Return.STOP_ALL

        if not self.players_start:
            channel.reply("No players are currently being tracked for leaver bans.")
            return

        self.reply_lines(channel, ["Players currently being tracked for leaver bans:"]
                              + [f" ^6•^7 {p.clean_name}" for p in self.players_start])

    @minqlxtended.command("checkleaver", usage="<id>")
    def cmd_checkleaver(self, player, msg, channel):
        """ Checks a player's leaver-ban status: current leave count, and (if banned) expiry and time remaining. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, name, _target = resolved

        if not self._qlx_leaverBan:
            channel.reply("Leaver bans are not enabled.")
            return minqlxtended.Return.STOP_ALL

        if not self.describe_leaver_status(ident, name, channel):
            channel.reply(f"^6{name}^7 is not leaver banned.")

    def describe_leaver_status(self, steam_id, name, channel):
        """Report a player's leaver status on *channel*.

        Also called by ban.py's !checkban, so the leaver half of that report stays
        in the plugin that owns the data rather than being reimplemented there.

        :returns: bool -- False if there was nothing to say, so the caller can fall
            back to its own "not banned" message.
        """
        if not self._qlx_leaverBan:
            return False

        info = self.get_player_leaver_ban_info(steam_id)
        if not info:
            return False

        leave_count = info.get("current_leave_count", 0)

        if info.get("is_banned"):
            # One reliable command instead of three.
            self.reply_lines(channel, [
                f"^6{name}^7 is leaver banned for leaving ^6{leave_count}^7 games.",
                f"Ban duration: ^6{info.get('ban_duration_hours', 24)} hours^7 "
                f"(^6{info.get('leaves_over_threshold', 1)}^7 leaves over threshold)",
                f"Ban expires: ^6{info.get('unban_datetime', 'unknown')}^7 "
                f"(in {info.get('time_remaining_human', 'unknown')})",
            ])
            return True

        if not leave_count:
            return False

        # Show current leave count even if not banned
        leaves_until_ban = max(0, self._qlx_leaverBanMaxLeaves - leave_count)
        summary = f"^6{name}^7 is not banned but has ^6{leave_count}^7 leave{'s' if leave_count != 1 else ''}."
        if leaves_until_ban:
            channel.reply(f"{summary} ^6{leaves_until_ban}^7 more leave{'s' if leaves_until_ban != 1 else ''} until ban.")
        else:
            # At or over the threshold with an expired ban. The next leave re-bans them.
            channel.reply(f"{summary} Their next leave bans them.")
        return True

    # HELPERS

    # Markdown that would break out of the []() link the player's name is rendered
    # inside, letting them point it wherever they like in a channel admins read.
    _MARKDOWN_ESCAPE = "\\`*_~|[]()>#-"

    @classmethod
    def escape_markdown(cls, text):
        for character in cls._MARKDOWN_ESCAPE:
            text = text.replace(character, "\\" + character)
        return text

    def send_discord_notification(self, message, colour=None):
        webhook = self._qlx_leaverBanDiscordWebhook
        if not webhook:
            return

        # Read anything off the engine here, on the game thread, and hand the worker
        # nothing but plain data.
        embed = {
            "description": message,
            "footer": {"text": f"Server: {self.get_cvar('sv_hostname')}"},
        }
        if colour:
            embed["color"] = colour

        # allowed_mentions is belt-and-braces: Discord doesn't resolve mentions inside
        # embeds today, which stops being true the moment a "content" field is added.
        self._post_discord(webhook, {"embeds": [embed], "allowed_mentions": {"parse": []}})

    @minqlxtended.thread
    def _post_discord(self, webhook, payload):
        try:
            response = requests.post(webhook, json=payload, timeout=DISCORD_TIMEOUT)
            if response.status_code not in (200, 204):
                self.logger.warning("Discord webhook failed with status %s", response.status_code)
        except requests.RequestException:
            self.logger.exception("Failed to send Discord notification.")

    def queue_player_leave(self, db, player):
        """Queue this player's leave onto an already-open pipeline.

        Split from the judgement below so handle_game_end can batch every leaver's writes
        into one round-trip. The two can't share one pipeline end to end, since
        finish_player_leave reads back the very set this writes. Returns whether anything
        was queued.
        """
        if player.is_bot:
            return False

        if self.db.has_permission(player, 1):
            self.logger.info(f"Player {player.clean_name} is a bot or has at least permission level 1. Not recording leave.")
            return False

        key = PLAYER_KEY.format(player.steam_id) + ":leaves"

        current_timestamp = time.time()
        cutoff_timestamp = current_timestamp - (self._qlx_leaverBanRollingWindowDays * 24 * 60 * 60)

        # Proper zadd syntax with unique member
        db.zadd(key, {f"leave_{current_timestamp}": current_timestamp})
        self.logger.info(f"Recorded leave for player {player.clean_name} (Steam ID: {player.steam_id}).")

        # Leaves older than the cutoff. The "- 86400" moves the boundary *back* to keep an
        # extra day; adding one instead deletes leaves still inside the rolling window, so
        # every new leave forgives one from the far end and the count never accumulates.
        db.zremrangebyscore(key, 0, cutoff_timestamp - 86400)

        # Ensure we don't have more than the max leaves
        db.expire(key, 60 * 60 * 24 * self._qlx_leaverBanRollingWindowDays + 86400) # +1 day to ensure we don't expire leaves from the current day

        return True

    def finish_player_leave(self, player):
        """Judge a leave that queue_player_leave has already written and executed."""
        # Returns None whenever qlx_leaverBan is off, which is the default, so this runs
        # for every recorded leaver and must not be dereferenced blind.
        ban_info = self.get_player_leaver_ban_info(player.steam_id)
        if ban_info is None:
            return

        new_leave_count = ban_info.get("current_leave_count", 0)
        is_banned = ban_info.get("is_banned", False)

        # Outside the `if webhook:` branch, or blanking the webhook silently turns leaver
        # bans off while still recording leaves.
        if is_banned:
            try:
                player.update()
                player.kick(f"has been banned for leaving {new_leave_count} game{'s' if new_leave_count != 1 else ''} in the last {self._qlx_leaverBanRollingWindowDays} days.")
                reason = "left team"
            except minqlxtended.NonexistentPlayerError:
                reason = "disconnected"
        else:
            try:
                player.update()
                reason = "left team"
            except minqlxtended.NonexistentPlayerError:
                reason = "disconnected"

        if not self._qlx_leaverBanDiscordWebhook:
            return

        if is_banned:
            ban_duration_hours = ban_info.get("ban_duration_hours", 24)
            leaves_over_threshold = ban_info.get("leaves_over_threshold", 1)

            self.send_discord_notification(
                f"🚫 **Player Banned**:\n"
                f"**Player:** [{self.escape_markdown(player.clean_name)}](https://steamcommunity.com/profiles/{player.steam_id})\n"
                f"**Reason:** Left {new_leave_count} games in the last {self._qlx_leaverBanRollingWindowDays} days\n"
                f"**Ban duration:** {ban_duration_hours} hours ({leaves_over_threshold} leave{'s' if leaves_over_threshold != 1 else ''} over threshold)\n"
                f"**Ban expires:** {ban_info.get('unban_datetime', 'Unknown')}\n"
                f"**Time remaining:** {ban_info.get('time_remaining_human', 'Unknown')}",
                colour=0xFF0000,  # Red colour
            )
            return

        # Regular leave notification
        leaves_until_ban = self._qlx_leaverBanMaxLeaves - new_leave_count

        # Color coding based on proximity to ban
        if leaves_until_ban <= 1:
            colour = 0xFF4500  # Orange-red (very close to ban)
        elif leaves_until_ban <= 2:
            colour = 0xFFA500  # Orange (close to ban)
        else:
            colour = 0xFFFF00  # Yellow (warning)

        self.send_discord_notification(
            f"⚠️ **Player Left Match**:\n"
            f"**Player:** [{self.escape_markdown(player.clean_name)}](https://steamcommunity.com/profiles/{player.steam_id}) ({reason})\n"
            f"**Leaves in the last {self._qlx_leaverBanRollingWindowDays} days:** {new_leave_count}/{self._qlx_leaverBanMaxLeaves}\n",
            colour=colour,
        )

    def get_player_leaver_ban_info(self, steam_id: int):
        """Get comprehensive leaver ban information for a player."""
        if not self._qlx_leaverBan:
            return None

        key = PLAYER_KEY.format(steam_id) + ":leaves"

        current_timestamp = time.time()
        cutoff_timestamp = current_timestamp - (self._qlx_leaverBanRollingWindowDays * 24 * 60 * 60)

        # Leaves within the rolling window, oldest first. ZRANGEBYSCORE answers [] for a
        # missing key, so one round-trip covers the never-left player too.
        leaves_in_window = self.db.zrangebyscore(key, cutoff_timestamp, current_timestamp, withscores=True)

        # Get current leave count in the rolling window
        current_leave_count = len(leaves_in_window)

        result = {
            "is_banned": False,
            "current_leave_count": current_leave_count,
            "unban_timestamp": None
        }

        # An empty window has no newest leave to date a ban from. qlx_leaverBanMaxLeaves 0
        # satisfies the threshold test below with a count of zero.
        if not leaves_in_window:
            return result

        # Determine if player is banned and calculate unban timestamp
        is_banned = current_leave_count >= self._qlx_leaverBanMaxLeaves
        unban_timestamp = None

        if is_banned:
            # Find the newest (last) leave timestamp
            newest_leave_timestamp = leaves_in_window[-1][1]

            # Calculate ban duration: 24 hours * (leaves over threshold)
            leaves_over_threshold = current_leave_count - self._qlx_leaverBanMaxLeaves + 1
            ban_duration_hours = 24 * leaves_over_threshold

            # Calculate when ban expires (24 hours * leaves over threshold after last leave)
            unban_timestamp = newest_leave_timestamp + (ban_duration_hours * 60 * 60)

            # If the unban time has already passed, player should not be banned
            if unban_timestamp <= current_timestamp:
                is_banned = False
                unban_timestamp = None
            else:
                # Player is actually banned
                result["is_banned"] = True
                result["unban_timestamp"] = unban_timestamp
                result["leaves_over_threshold"] = leaves_over_threshold
                result["ban_duration_hours"] = ban_duration_hours

                unban_datetime = datetime.datetime.fromtimestamp(unban_timestamp)
                time_remaining = unban_timestamp - current_timestamp

                # Format time remaining
                days = int(time_remaining // (24 * 3600))
                hours = int((time_remaining % (24 * 3600)) // 3600)
                minutes = int((time_remaining % 3600) // 60)

                parts = []
                if days > 0:
                    parts.append(f"{days} day{'s' if days != 1 else ''}")
                if hours > 0:
                    parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
                if minutes > 0:
                    parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

                time_remaining_human = ", ".join(parts) if parts else "Less than 1 minute"

                result.update({
                    "unban_datetime": unban_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                    "time_remaining_seconds": time_remaining,
                    "time_remaining_hours": time_remaining / 3600,
                    "time_remaining_days": time_remaining / (24 * 3600),
                    "time_remaining_human": time_remaining_human
                })

        return result

    def warn_player(self, player, ban_info):
        """Warn a player about their leave count using the ban info structure."""
        leave_count = ban_info.get("current_leave_count", 0)

        player.center_print("^1BAN WARNING^7\nReview the console for more information.")
        self.play_sound("sound/world/klaxon2.wav", player=player)
        player.tell(f"\n^7You have left ^6{leave_count}^7 game{'s' if leave_count != 1 else ''} over the past ^6{self._qlx_leaverBanRollingWindowDays}^7 days.")

        # Calculate how many more leaves until ban
        leaves_until_ban = self._qlx_leaverBanMaxLeaves - leave_count
        if leaves_until_ban > 0:
            player.tell(f"^7You will be banned if you leave ^6{leaves_until_ban}^7 more game{'s' if leaves_until_ban != 1 else ''}.")

        player.tell("^7If you keep leaving you ^6will^7 be banned.\n")

    @staticmethod
    def is_server_drop(reason) -> bool:
        """Whether the server, rather than the player, ended the connection."""
        if not reason:
            return False
        return reason in SERVER_DROP_REASONS or reason.startswith("was kicked")

    def sides_after_departure(self, player, team):
        """Sizes of *team* and its opposite once *player* is off *team*.

        player_disconnect fires ahead of SV_DropClient, so self.teams() still counts the
        leaver; team_switch fires after the move and doesn't. Discounting the player when
        they're still listed gives both callers the same numbers to judge.
        """
        teams = self.teams()
        opposing = minqlxtended.Team.BLUE if team == minqlxtended.Team.RED else minqlxtended.Team.RED
        remaining = len(teams[team]) - (1 if player in teams[team] else 0)
        return remaining, len(teams[opposing])

    def is_1v1_match(self) -> bool:
        # `and` here. With `or` a 1v5 counts as a 1v1, and leaving one of those is
        # exactly what someone wants to do.
        teams = self.teams()
        return len(teams["red"]) == 1 and len(teams["blue"]) == 1
