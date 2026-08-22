# block.py — per-player chat blocking.
#
# Lets any player stop seeing chat from a specific other player, without admin
# involvement and without affecting what anyone else sees.
#
# This is NOT the same as !mute / !silence, which set the engine's server-wide
# `muted` flag and silence a player for everyone. A block is per-viewer:
# only the player who issued it stops receiving the messages.
#
# How it works
# ------------
# Quake Live delivers chat per recipient rather than as a broadcast: one
# SV_SendServerCommand call per client, each with that client's id. minqlx hooks
# that function's entry, so returning False from a "server_command" handler drops
# exactly one recipient's copy before it reaches the wire. Chat keeps its native
# rendering, colours and sound; nothing is suppressed and re-sent.
#
# Only "chat" and "tchat" are filtered. Server announcements travel as "print"
# and "cp" broadcasts (client_id -1), so admin messages can never be blocked.

import minqlxtended
from redis.exceptions import RedisError as _RedisError

PLAYER_KEY = "minqlx:players:{}"

# Bots occupy the same low integer range as client ids, which is why
# Plugin.player() treats values under 64 as client slots rather than SteamIDs.
BOT_STEAM_ID_MAX = 64

# The only two server commands that carry player chat.
CHAT_PREFIXES = ("chat \"", "tchat \"")

_DIGITS = "0123456789"


def blocks_key(steam_id):
    return PLAYER_KEY.format(steam_id) + ":blocks"


def parse_speaker_cid(cmd):
    """Return the speaking player's client id from a chat/tchat payload.

    Quake Live emits chat as:
        chat "02 Doomsday^7\x19: ^2hello"
        tchat "02 \x19(Doomsday^7\x19) (upper courtyard^7)\x19: ^5hello"

    Both carry the speaker's client id, zero-padded to two digits, immediately
    after the opening quote. Client ids never exceed 64, so two digits always
    suffice.

    Returns None when the payload does not match that shape. Callers treat None
    as "deliver the message": failing open is deliberate, because silently eating
    chat over a parse bug is far worse than a block that quietly does nothing.
    """
    i = cmd.find("\"")
    if i == -1:
        return None
    digits = cmd[i + 1:i + 3]
    if len(digits) != 2 or digits[0] not in _DIGITS or digits[1] not in _DIGITS:
        return None
    return int(digits)


class block(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()
        # PRI_LOWEST deliberately. Handlers that return a modified string overwrite
        # the dispatcher's return_value, so anything running after us could undo our
        # decision to drop the message. Running last makes that impossible.
        self.add_hook("server_command", self.handle_server_command, priority=minqlxtended.Priority.LOWEST)
        self.add_hook("player_loaded", self.handle_player_loaded)
        self.add_hook("player_disconnect", self.handle_player_disconnect)

        # client_cmd_perm=0 also exposes these from the console (/block 3), which
        # bypasses chat entirely.
        self.add_command("block", self.cmd_block, 0, client_cmd_perm=0, usage="<id>")
        self.add_command("unblock", self.cmd_unblock, 0, client_cmd_perm=0, usage="<id>")
        self.add_command("blocklist", self.cmd_blocklist, 0, client_cmd_perm=0)

        self.set_cvar_once("qlx_blockMaxEntries", "50")

        self._blocks = {}   # blocker_sid -> set(blocked_sid), mirrors Redis
        self._active = {}   # viewer_cid  -> set(blocked_cid), derived for the hot path

        # Repopulate for anyone already connected so a mid-game reload is seamless.
        for p in self.players():
            self._load_blocks(p.steam_id)
        self._rebuild_active()

    # ====================================================================
    #                               HOOKS
    # ====================================================================

    def handle_server_command(self, player, cmd):
        # Hot path. This hook also carries every configstring, score update and
        # centerprint on the server, so the cheap rejections come first and
        # nothing is parsed or allocated until a block is known to be in play.
        if player is None:
            return
        if not cmd.startswith(CHAT_PREFIXES):
            return

        blocked = self._active.get(player.id)
        if not blocked:
            return

        speaker_cid = parse_speaker_cid(cmd)
        if speaker_cid is not None and speaker_cid in blocked:
            # Drops this recipient's copy only; everyone else still receives it.
            #
            # RET_STOP_EVENT, never a literal False. RET_NONE is 0, so `False == 0`
            # is True and the dispatcher would treat a returned False as "continue",
            # silently delivering the message. RET_STOP_EVENT sets the dispatcher's
            # return_value to False, which is what makes the engine skip the send,
            # while still letting other plugins' handlers see the command.
            return minqlxtended.Return.STOP_EVENT

    def handle_player_loaded(self, player):
        self._load_blocks(player.steam_id)
        self._rebuild_active()

    def handle_player_disconnect(self, player, reason):
        # Redis remains the source of truth; this only frees memory.
        self._blocks.pop(player.steam_id, None)
        self._rebuild_active()

    # ====================================================================
    #                             COMMANDS
    # ====================================================================
    #
    # Every command returns RET_STOP_ALL so that the triggering "say" never
    # reaches the engine. Without it, typing "!block 3" in chat would broadcast
    # to everyone, including the player being blocked, which defeats the point.
    # All replies go through player.tell() rather than channel.reply() for the
    # same reason.

    def cmd_block(self, player, msg, channel):
        """Stops you seeing chat from a player. Use the ID shown by /players.

        Example: !block 3"""
        if len(msg) < 2:
            player.tell("^7Usage: ^6!block <id>^7 — use the ID from ^6/players^7.")
            return minqlxtended.Return.STOP_ALL

        target_sid, name = self._resolve_target(player, msg[1])
        if target_sid is None:
            return minqlxtended.Return.STOP_ALL

        if target_sid == player.steam_id:
            player.tell("^7You cannot block yourself.")
            return minqlxtended.Return.STOP_ALL
        if target_sid < BOT_STEAM_ID_MAX:
            player.tell("^7You cannot block a bot.")
            return minqlxtended.Return.STOP_ALL

        current = self._blocks.get(player.steam_id, set())
        if target_sid in current:
            player.tell("^7You have already blocked ^6{}^7.".format(name))
            return minqlxtended.Return.STOP_ALL

        max_entries = self.get_cvar("qlx_blockMaxEntries", int)
        if len(current) >= max_entries:
            player.tell("^7Your block list is full (^6{}^7). Use ^6!unblock^7 first.".format(max_entries))
            return minqlxtended.Return.STOP_ALL

        try:
            self.db.sadd(blocks_key(player.steam_id), target_sid)
        except _RedisError as e:
            minqlxtended.get_logger(self).warning("block: sadd failed for %s: %s", player.steam_id, e)
            player.tell("^1Could not save the block. Try again later.")
            return minqlxtended.Return.STOP_ALL

        self._blocks.setdefault(player.steam_id, set()).add(target_sid)
        self._rebuild_active()
        player.tell("^7You have blocked ^6{}^7. You will no longer see their chat.".format(name))
        return minqlxtended.Return.STOP_ALL

    def cmd_unblock(self, player, msg, channel):
        """Reverses !block. Use the ID shown by /players, or the SteamID.

        Example: !unblock 3"""
        if len(msg) < 2:
            player.tell("^7Usage: ^6!unblock <id>^7 — see ^6!blocklist^7.")
            return minqlxtended.Return.STOP_ALL

        target_sid, name = self._resolve_target(player, msg[1])
        if target_sid is None:
            return minqlxtended.Return.STOP_ALL

        if target_sid not in self._blocks.get(player.steam_id, set()):
            player.tell("^7You have not blocked ^6{}^7.".format(name))
            return minqlxtended.Return.STOP_ALL

        try:
            self.db.srem(blocks_key(player.steam_id), target_sid)
        except _RedisError as e:
            minqlxtended.get_logger(self).warning("block: srem failed for %s: %s", player.steam_id, e)
            player.tell("^1Could not remove the block. Try again later.")
            return minqlxtended.Return.STOP_ALL

        remaining = self._blocks.get(player.steam_id)
        if remaining is not None:
            remaining.discard(target_sid)
            if not remaining:
                del self._blocks[player.steam_id]
        self._rebuild_active()
        player.tell("^7You have unblocked ^6{}^7.".format(name))
        return minqlxtended.Return.STOP_ALL

    def cmd_blocklist(self, player, msg, channel):
        """Shows who you have blocked. Only you see this."""
        blocked = self._blocks.get(player.steam_id)
        if not blocked:
            player.tell("^7You have not blocked anyone.")
            return minqlxtended.Return.STOP_ALL

        # Names are resolved only for players currently on the server; offline
        # entries show the raw SteamID rather than costing a lookup each.
        online = {}
        for p in self.players():
            online[p.steam_id] = p.name

        # Grouped a few per line rather than one tell() per entry: at the 50-entry
        # cap that is the difference between ~17 messages and 50.
        lines = []
        chunk = []
        for sid in sorted(blocked):
            name = online.get(sid)
            chunk.append("^6{}^7{}".format(sid, " ({})".format(name) if name else ""))
            if len(chunk) == 3:
                lines.append("  " + "   ".join(chunk))
                chunk = []
        if chunk:
            lines.append("  " + "   ".join(chunk))

        player.tell("^7You have blocked ^6{}^7 player(s):".format(len(blocked)))
        for line in lines:
            player.tell(line)
        player.tell("^7Use ^6!unblock <SteamID>^7 to reverse one.")
        return minqlxtended.Return.STOP_ALL

    # ====================================================================
    #                              HELPERS
    # ====================================================================

    def _resolve_target(self, player, ident_arg):
        """Resolve a command argument to (steam_id, display_name).

        Accepts either a client id from /players or a full SteamID64, matching
        the convention used by ban.py. Replies to the caller and returns
        (None, None) when the argument cannot be resolved.
        """
        try:
            ident = int(ident_arg)
        except ValueError:
            player.tell("^7Invalid ID. Use a client ID from ^6/players^7 or a SteamID64.")
            return None, None

        target_player = None
        if 0 <= ident < BOT_STEAM_ID_MAX:
            try:
                target_player = self.player(ident)
            except minqlxtended.NonexistentPlayerError:
                target_player = None
            if not target_player:
                player.tell("^7No player with client ID ^6{}^7. Check ^6/players^7.".format(ident))
                return None, None
            ident = target_player.steam_id

        return ident, target_player.name if target_player else str(ident)

    def _load_blocks(self, steam_id):
        """Load one player's block set from Redis into memory."""
        try:
            members = self.db.smembers(blocks_key(steam_id))
        except _RedisError as e:
            minqlxtended.get_logger(self).warning("block: smembers failed for %s: %s", steam_id, e)
            return

        sids = set()
        for member in members:
            if isinstance(member, bytes):
                member = member.decode("utf-8", "ignore")
            try:
                sids.add(int(member))
            except (TypeError, ValueError):
                minqlxtended.get_logger(self).warning(
                    "block: skipping malformed entry %r for %s", member, steam_id
                )

        if sids:
            self._blocks[steam_id] = sids
        else:
            self._blocks.pop(steam_id, None)

    def _rebuild_active(self):
        """Recompute the client-id lookup used by the hot path.

        Always a full rebuild from _blocks plus the live roster. Incremental
        updates are avoided on purpose: client slots get reused when players
        reconnect, and a stale partial map would let a new occupant inherit the
        previous player's block. The roster caps at 64, so this is cheap.
        """
        roster = self.players()
        sid_to_cid = {p.steam_id: p.id for p in roster}

        active = {}
        for p in roster:
            blocked_sids = self._blocks.get(p.steam_id)
            if not blocked_sids:
                continue
            cids = {sid_to_cid[sid] for sid in blocked_sids if sid in sid_to_cid}
            if cids:
                active[p.id] = cids

        self._active = active
