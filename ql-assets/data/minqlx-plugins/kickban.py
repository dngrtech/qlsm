"""
kickban.py — auto-ban players kicked too many times in a sliding window.

CVARs:
  qlx_kickbanThreshold    - kicks within window before ban (default: 3)
  qlx_kickbanWindow       - window duration in minutes (default: 15)
  qlx_kickbanDuration     - ban length in minutes (default: 60)
  qlx_kickbanImmunityLevel - permission level immune from auto-ban (default: 2)

Commands:
  !kickhistory <id>  - show kick count + timestamps within window (perm 2)
  !kickclear <id>    - clear a player's kick history (perm 2)
"""

import datetime
import time
import uuid

import minqlx
from redis.exceptions import RedisError as _RedisError

PLAYER_KEY = "minqlx:players:{}"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def zadd_compat(db, key, member, score):
    """Support both redis-py 2.x (raises RedisError) and 3.x+ (dict mapping) zadd signatures."""
    try:
        return db.zadd(key, {member: score})
    except (TypeError, _RedisError):
        return db.zadd(key, score, member)


class kickban(minqlx.Plugin):
    def __init__(self):
        super().__init__()

        self.set_cvar_once("qlx_kickbanThreshold", "3")
        self.set_cvar_once("qlx_kickbanWindow", "15")
        self.set_cvar_once("qlx_kickbanDuration", "60")
        self.set_cvar_once("qlx_kickbanImmunityLevel", "2")

        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.add_hook("player_loaded", self.handle_player_loaded)

        self.add_command("kickhistory", self.cmd_kickhistory, 2, usage="<id>")
        self.add_command("kickclear", self.cmd_kickclear, 2, usage="<id>")

    # ── Key helpers ──────────────────────────────────────────────────────

    def _kicks_key(self, steam_id):
        return PLAYER_KEY.format(steam_id) + ":kicks"

    def _bans_key(self, steam_id):
        return PLAYER_KEY.format(steam_id) + ":bans"

    # ── Cvar helpers ─────────────────────────────────────────────────────

    def _threshold(self):
        # Clamp to minimum 2: a threshold of 0 or 1 bans on first kick, which is a foot-gun.
        return max(2, self.get_cvar("qlx_kickbanThreshold", int))

    def _window(self):
        return self.get_cvar("qlx_kickbanWindow", int)

    def _duration(self):
        return self.get_cvar("qlx_kickbanDuration", int)

    def _immunity(self):
        return self.get_cvar("qlx_kickbanImmunityLevel", int)

    # ── Redis helpers ────────────────────────────────────────────────────

    def _prune_and_count(self, steam_id):
        """Remove kicks outside the window and return the current count."""
        cutoff = time.time() - (self._window() * 60)
        key = self._kicks_key(steam_id)
        self.db.zremrangebyscore(key, 0, cutoff)
        return self.db.zcard(key)

    def _resolve_player(self, ident_str, channel):
        """Return (steam_id, display_name) or (None, None) on error."""
        try:
            ident = int(ident_str)
            if 0 <= ident < 64:
                target = self.player(ident)
                return target.steam_id, target.clean_name
            return ident, str(ident)
        except ValueError:
            channel.reply("Invalid ID. Use a client ID (0-63) or a SteamID64.")
            return None, None
        except minqlx.NonexistentPlayerError:
            channel.reply("No player found at that client slot.")
            return None, None

    # ── Hooks ────────────────────────────────────────────────────────────

    def handle_player_disconnect(self, player, reason):
        if not reason or "kicked" not in reason.lower():
            return

        # Guard: player attributes may be unavailable on a partially torn-down
        # player object during disconnect teardown.
        try:
            steam_id = player.steam_id
            name = player.clean_name
        except minqlx.NonexistentPlayerError:
            return

        if self.db.get_permission(steam_id) >= self._immunity():
            return

        count = self._prune_and_count(steam_id)
        ts = time.time()
        # Use a UUID as the member so two kicks within the same float-timestamp
        # resolution are stored as distinct sorted set entries.
        zadd_compat(self.db, self._kicks_key(steam_id), str(uuid.uuid4()), ts)
        count += 1

        if count >= self._threshold():
            self._issue_ban(steam_id, name, count)

    @minqlx.delay(5)
    def handle_player_loaded(self, player):
        try:
            player.update()
        except minqlx.NonexistentPlayerError:
            return

        steam_id = player.steam_id
        count = self._prune_and_count(steam_id)

        if count == 0:
            return

        threshold = self._threshold()
        window = self._window()
        duration = self._duration()
        remaining = max(0, threshold - count)

        if remaining == 0:
            return

        self.msg(
            "^3{}^7 has been kicked ^1{}^7 time(s) in the last ^3{}^7 min — "
            "^1{}^7 more kick(s) will result in a ^1{}^7-minute ban.".format(
                player.clean_name, count, window, remaining, duration
            )
        )

    # ── Ban issuance ─────────────────────────────────────────────────────

    def _issue_ban(self, steam_id, name, count):
        """Write a ban to ban.py's Redis format and broadcast to server."""
        duration = self._duration()
        window = self._window()
        # datetime.now() returns local time — this matches ban.py's convention.
        # ban.py's is_banned() also uses datetime.now() for comparison, so this
        # is internally consistent even though time.time() (the sorted set score)
        # is a Unix epoch value.
        now = datetime.datetime.now()
        expires = now + datetime.timedelta(minutes=duration)
        now_str = now.strftime(TIME_FORMAT)
        expires_str = expires.strftime(TIME_FORMAT)

        base_key = self._bans_key(steam_id)
        # ban_id is derived from zcard — known limitation shared with ban.py:
        # if old bans have been removed (expired or !unban), zcard may return an
        # ID that was used before, overwriting the old hash. This matches ban.py's
        # own ID generation and is acceptable given the low frequency of re-banning
        # the same player. A future improvement could use an INCR-based counter.
        ban_id = self.db.zcard(base_key)

        pipe = self.db.pipeline()
        zadd_compat(pipe, base_key, ban_id, time.time() + duration * 60)
        pipe.hset(
            base_key + ":{}".format(ban_id),
            mapping={
                "expires": expires_str,
                "reason": "Auto-banned: kicked {} times within {} minutes".format(count, window),
                "issued": now_str,
                "issued_by": "0",
            },
        )
        pipe.execute()

        self.db.delete(self._kicks_key(steam_id))
        self.msg(
            "^3{}^7 has been auto-banned for ^1{}^7 minutes.".format(name, duration)
        )

    # ── Commands ─────────────────────────────────────────────────────────

    def cmd_kickhistory(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE

        steam_id, name = self._resolve_player(msg[1], channel)
        if steam_id is None:
            return

        count = self._prune_and_count(steam_id)
        window = self._window()
        threshold = self._threshold()

        if count == 0:
            channel.reply("^6{}^7 has no kicks in the last ^3{}^7 minutes.".format(name, window))
            return

        cutoff = time.time() - window * 60
        kicks = self.db.zrangebyscore(self._kicks_key(steam_id), cutoff, "+inf", withscores=True)
        timestamps = [
            datetime.datetime.fromtimestamp(float(score)).strftime(TIME_FORMAT)
            for _, score in kicks
        ]
        channel.reply(
            "^6{}^7: ^1{}/{}^7 kicks in last ^3{}^7 min: {}".format(
                name, count, threshold, window, ", ".join(timestamps)
            )
        )

    def cmd_kickclear(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE

        steam_id, name = self._resolve_player(msg[1], channel)
        if steam_id is None:
            return

        self.db.delete(self._kicks_key(steam_id))
        self.msg("^6{}^7 cleared kick history for ^6{}^7.".format(player.clean_name, name))
        channel.reply("^6{}^7's kick history cleared.".format(name))
