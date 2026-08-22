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
import logging
import os.path
import datetime
import os

from logging.handlers import RotatingFileHandler

class log(minqlxtended.Plugin):
    _qlx_chatlogs = minqlxtended.setting("qlx_chatlogs", 10)
    _qlx_chatlogsSize = minqlxtended.setting("qlx_chatlogsSize", 3 * 10**6)  # 3 MB

    def __init__(self):
        super().__init__()

        # A named logger with its handlers reset, so reloading does not stack duplicate
        # file handlers. Propagation off, or chat lines also land in minqlxtended.log.
        self.chatlog = logging.getLogger("minqlxtended.chatlog")
        self.chatlog.setLevel(logging.INFO)
        self.chatlog.propagate = False
        for handler in self.chatlog.handlers[:]:
            self.chatlog.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

        file_dir = os.path.join(minqlxtended.get_cvar("fs_homepath"), "chatlogs")
        if not os.path.isdir(file_dir):
            os.makedirs(file_dir)

        file_path = os.path.join(file_dir, "chat.log")
        maxlogs = self._qlx_chatlogs
        maxlogsize = self._qlx_chatlogsSize
        file_fmt = logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        file_handler = RotatingFileHandler(file_path, encoding="utf-8", maxBytes=maxlogsize, backupCount=maxlogs)
        file_handler.setFormatter(file_fmt)
        # Every hook here runs on the game thread, so a direct write puts disk I/O, and
        # every so often a whole rotation, inside the frame. queued_handler hands the
        # record to a listener thread.
        self.chatlog.addHandler(minqlxtended.queued_handler(file_handler))
        self.chatlog.info(f"{'=' * 29} Logger started @ {datetime.datetime.now()} {'=' * 29}")

    @minqlxtended.hook("player_connect", priority=minqlxtended.Priority.LOWEST)
    def handle_player_connect(self, player, is_bot):
        self.chatlog.info(f"{player.clean_name}:{player.steam_id}:{player.ip if not is_bot else 'bot'} connected.")

    @minqlxtended.hook("player_disconnect", priority=minqlxtended.Priority.LOWEST)
    def handle_player_disconnect(self, player, reason):
        if reason and reason[-1] not in ("?", "!", "."):
            reason = reason + "."

        self.chatlog.info(self.clean_text(f"{player}:{player.steam_id} {reason}"))

    @minqlxtended.hook("chat", priority=minqlxtended.Priority.LOWEST)
    def handle_chat(self, player, msg, channel, recipient):
        channel_name = ""
        if channel != "chat":
            # A tell's channel addresses the speaker, so `recipient` is who it went to.
            label = f"tell {recipient}" if recipient is not None else str(channel)
            channel_name = f"[{label.upper()}] "

        self.chatlog.info(self.clean_text(f"{channel_name}<{player}:{player.steam_id}> {msg}"))

    @minqlxtended.hook("command", priority=minqlxtended.Priority.LOWEST)
    def handle_command(self, caller, command, args):
        self.chatlog.info(self.clean_text(f"[CMD] <{caller}:{caller.steam_id}> {args}"))

    @minqlxtended.hook("vote_started", priority=minqlxtended.Priority.LOWEST)
    def handle_vote_started(self, caller, vote, args):
        vote = vote.lower().strip()
        args = args.lower().strip().replace('""', "")
        if caller:
            self.chatlog.info(self.clean_text(f"[VOTE_EVENT] Vote was called: <{caller}:{caller.steam_id}> {vote} {args if args else ''}"))
        else:
            self.chatlog.info(self.clean_text(f"[VOTE_EVENT] Vote was called: <CustomVote:{minqlxtended.owner()}> {vote} {args}"))

    @minqlxtended.hook("vote_ended", priority=minqlxtended.Priority.LOWEST)
    def handle_vote_ended(self, votes, vote, args, passed):
        self.chatlog.info(self.clean_text(f"[VOTE_EVENT] Vote has ended: {votes[0]} voted yes, {votes[1]} voted no. Vote {'passed' if passed else 'failed'}."))

    @minqlxtended.hook("map", priority=minqlxtended.Priority.LOWEST)
    def handle_map(self, mapname, factory):
        self.chatlog.info(self.clean_text(f"[MAP] {mapname} ({factory})"))

    @minqlxtended.hook("game_countdown", priority=minqlxtended.Priority.LOWEST)
    def handle_game_countdown(self):
        self.chatlog.info(self.clean_text(f"[MATCH_EVENT] Match countdown started, the game will begin in {self.get_cvar('g_warmup', int)} seconds"))

    @minqlxtended.hook("game_start", priority=minqlxtended.Priority.LOWEST)
    def handle_game_start(self):
        teams = self.teams()
        if self.is_team_based_game():
            self.chatlog.info(self.clean_text(f"[MATCH_EVENT] Match has begun (Red: {len(teams['red'])}, Blue: {len(teams['blue'])})"))
        else:
            self.chatlog.info(self.clean_text(f"[MATCH_EVENT] Match has begun with {len(teams['free'])} player{'s' if len(teams['free']) != 1 else ''}"))

    @minqlxtended.hook("game_end", priority=minqlxtended.Priority.LOWEST)
    def handle_game_end(self, aborted):
        # The game module has no equivalent of the ZMQ match report's EXIT_MSG, so log
        # the score.
        if aborted:
            self.chatlog.info(self.clean_text("[MATCH_EVENT] Match was aborted."))
        elif self.is_team_based_game() and self.game is not None:
            game = self.game
            self.chatlog.info(self.clean_text(f"[MATCH_EVENT] Match ended (Red: {game.team_scores[minqlxtended.Team.RED.index]}, Blue: {game.team_scores[minqlxtended.Team.BLUE.index]})"))
        else:
            self.chatlog.info(self.clean_text("[MATCH_EVENT] Match ended."))

    def is_team_based_game(self) -> bool:
        # The enum owns the team/non-team split. self.game can be None while these hooks
        # still fire, so read the cvar.
        return minqlxtended.Gametype.from_index(self.get_cvar("g_gametype", int)).is_team_based
