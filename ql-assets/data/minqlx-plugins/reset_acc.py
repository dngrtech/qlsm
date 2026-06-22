"""
reset_acc - Reset scoreboard stats mid-game (accuracy, K/D, score).

Designed for FFA warmup/practice servers where players want per-fight
stats. After a fight, type !resetstats to zero your accuracy, kills,
deaths, and score so the next Tab press shows only that engagement.

When auto-reset of full stats is enabled (!autoresetstats), the player is
privately told their overall accuracy ("^7ACC: ^2[n]%") on every kill and
death, so they see what they had right before the stats wipe.

Requires minqlx built with the reset_player_stats(), reset_player_accuracy()
and player_accuracy() C bindings.

Commands:
  !resetstats          - Reset accuracy, K/D, and score to 0
  !resetstats <name>   - Admin: reset another player's stats
  !resetacc            - Reset accuracy only (K/D unchanged)
  !resetacc <name>     - Admin: reset another player's accuracy only
  !autoresetacc [kill|death|both|off] [delay]
                       - Auto-reset accuracy after kill/death
  !autoresetstats [kill|death|both|off] [delay]
                       - Auto-reset full stats after kill/death

CVars:
  qlx_autoResetDelay   - Default delay in seconds before auto-reset fires
                         (default: 2.0, range: 0-5, decimals ok e.g. 0.5)
"""

import threading
import minqlx

ADMIN_LEVEL = 2
AUTO_RESET_DELAY_DEFAULT = 2.0
AUTO_RESET_DELAY_MAX = 5.0
VALID_MODES = ("kill", "death", "both", "off")

DB_KEY = "minqlx:players:{}:reset_acc:{}"


class reset_acc(minqlx.Plugin):
    def __init__(self):
        self.add_command("resetstats", self.cmd_resetstats, 0)
        self.add_command("resetacc", self.cmd_resetacc, 0)
        self.add_command("autoresetacc", self.cmd_autoresetacc, 0)
        self.add_command("autoresetstats", self.cmd_autoresetstats, 0)

        self.add_hook("kill", self.handle_kill)
        self.add_hook("player_loaded", self.handle_loaded)
        self.add_hook("player_disconnect", self.handle_disconnect)

        # {steam_id: {"mode": "kill"|"death"|"both", "delay": float}}
        self._auto_acc = {}
        self._auto_stats = {}
        # {steam_id: [threading.Timer, ...]}
        self._pending_timers = {}

        self.set_cvar_once("qlx_autoResetDelay", str(AUTO_RESET_DELAY_DEFAULT))

    # -------------------------------------------------------------------------
    # Redis persistence
    # -------------------------------------------------------------------------

    def _db_load(self, player, store, key):
        sid = player.steam_id
        mode = self.db.get(DB_KEY.format(sid, f"{key}:mode"))
        if mode not in ("kill", "death", "both"):
            return
        try:
            delay = float(self.db.get(DB_KEY.format(sid, f"{key}:delay")) or AUTO_RESET_DELAY_DEFAULT)
        except (TypeError, ValueError):
            delay = AUTO_RESET_DELAY_DEFAULT
        delay = max(0.0, min(AUTO_RESET_DELAY_MAX, delay))
        store[sid] = {"mode": mode, "delay": delay}

    def _db_save(self, player, key, pref):
        sid = player.steam_id
        if pref is None:
            self.db.delete(DB_KEY.format(sid, f"{key}:mode"))
            self.db.delete(DB_KEY.format(sid, f"{key}:delay"))
        else:
            self.db[DB_KEY.format(sid, f"{key}:mode")] = pref["mode"]
            self.db[DB_KEY.format(sid, f"{key}:delay")] = str(pref["delay"])

    def handle_loaded(self, player):
        self._db_load(player, self._auto_acc, "acc")
        self._db_load(player, self._auto_stats, "stats")

    # -------------------------------------------------------------------------
    # Manual reset commands
    # -------------------------------------------------------------------------

    def cmd_resetstats(self, player, msg, channel):
        if len(msg) == 1:
            self._reset_all(player, player)
            return minqlx.RET_STOP_ALL

        if player.privileges is None or player.privileges not in ("admin", "mod"):
            player.tell("^1Only admins can reset another player's stats.")
            return minqlx.RET_STOP_ALL

        target = self._find_player(" ".join(msg[1:]).lower())
        if target is None:
            player.tell(f"^1No player found matching ^7{' '.join(msg[1:])}^1.")
            return minqlx.RET_STOP_ALL

        self._reset_all(player, target)
        return minqlx.RET_STOP_ALL

    def cmd_resetacc(self, player, msg, channel):
        if len(msg) == 1:
            self._reset_accuracy(player, player)
            return minqlx.RET_STOP_ALL

        if player.privileges is None or player.privileges not in ("admin", "mod"):
            player.tell("^1Only admins can reset another player's accuracy.")
            return minqlx.RET_STOP_ALL

        target = self._find_player(" ".join(msg[1:]).lower())
        if target is None:
            player.tell(f"^1No player found matching ^7{' '.join(msg[1:])}^1.")
            return minqlx.RET_STOP_ALL

        self._reset_accuracy(player, target)
        return minqlx.RET_STOP_ALL

    # -------------------------------------------------------------------------
    # Auto-reset toggle commands
    # -------------------------------------------------------------------------

    def cmd_autoresetacc(self, player, msg, channel):
        self._handle_auto_cmd(player, msg, self._auto_acc, "accuracy", "autoresetacc", "acc")
        return minqlx.RET_STOP_ALL

    def cmd_autoresetstats(self, player, msg, channel):
        self._handle_auto_cmd(player, msg, self._auto_stats, "stats", "autoresetstats", "stats")
        return minqlx.RET_STOP_ALL

    def _handle_auto_cmd(self, player, msg, store, label, cmd, db_key):
        sid = player.steam_id

        if len(msg) == 1:
            pref = store.get(sid)
            if pref is None:
                player.tell(f"^7Auto-reset {label}: ^1off^7. Usage: ^3!{cmd} [kill|death|both|off] [0-5, decimals ok]")
            else:
                player.tell(f"^7Auto-reset {label}: ^2{pref['mode']}^7, delay ^2{pref['delay']}s^7.")
            return

        mode = msg[1].lower()
        if mode not in VALID_MODES:
            player.tell("^1Invalid mode. Use: kill | death | both | off")
            return

        if mode == "off":
            store.pop(sid, None)
            self._db_save(player, db_key, None)
            player.tell(f"^7Auto-reset {label}: ^1disabled^7.")
            return

        delay = self._parse_delay(player, msg[2] if len(msg) > 2 else None)
        if delay is None:
            return

        pref = {"mode": mode, "delay": delay}
        store[sid] = pref
        self._db_save(player, db_key, pref)
        player.tell(f"^7Auto-reset {label}: ^2{mode}^7, delay ^2{delay}s^7.")

    def _parse_delay(self, player, raw):
        if raw is None:
            return self._server_delay()

        try:
            val = float(raw)
        except ValueError:
            player.tell(f"^1Delay must be a number between 0 and {AUTO_RESET_DELAY_MAX}.")
            return None

        if val > AUTO_RESET_DELAY_MAX:
            player.tell(f"^1Max delay is {AUTO_RESET_DELAY_MAX}s.")
            return None

        return max(0.0, val)

    def _server_delay(self):
        raw = self.get_cvar("qlx_autoResetDelay", float)
        if raw is None:
            return AUTO_RESET_DELAY_DEFAULT
        return max(0.0, min(AUTO_RESET_DELAY_MAX, raw))

    # -------------------------------------------------------------------------
    # Kill hook
    # -------------------------------------------------------------------------

    def handle_kill(self, victim, killer, data):
        self_kill = killer.steam_id == victim.steam_id
        is_teamkill = bool(data.get("TEAMKILL"))

        if not self_kill and not is_teamkill:
            self._schedule_auto_reset(killer, "kill")
        self._schedule_auto_reset(victim, "death")

    def _schedule_auto_reset(self, player, trigger):
        sid = player.steam_id

        # Determine which reset applies (stats takes priority over acc)
        stats_pref = self._auto_stats.get(sid)
        acc_pref = self._auto_acc.get(sid)

        reset_fn = None
        delay = self._server_delay()

        stats_applies = bool(stats_pref and stats_pref["mode"] in (trigger, "both"))
        acc_applies = bool(acc_pref and acc_pref["mode"] in (trigger, "both"))

        if stats_applies:
            reset_fn = self._reset_all
            delay = stats_pref["delay"]
        elif acc_applies:
            reset_fn = self._reset_accuracy
            delay = acc_pref["delay"]

        if reset_fn is None:
            return

        # Tell the player their accuracy before a full-stats auto-reset wipes
        # it. Fires on every kill/death, even when a reset timer is pending.
        if stats_applies:
            self._tell_accuracy(player)

        if self._pending_timers.get(sid):
            return

        def _fire(p=player, fn=reset_fn):
            self._pending_timers.pop(p.steam_id, None)

            @minqlx.next_frame
            def _execute():
                fn(p, p, silent=True)
            _execute()

        t = threading.Timer(delay, _fire)
        t.daemon = True
        t.start()
        self._pending_timers[sid] = [t]

    # -------------------------------------------------------------------------
    # Disconnect cleanup
    # -------------------------------------------------------------------------

    def handle_disconnect(self, player, reason):
        sid = player.steam_id
        for t in self._pending_timers.pop(sid, []):
            t.cancel()
        self._auto_acc.pop(sid, None)
        self._auto_stats.pop(sid, None)

    # -------------------------------------------------------------------------
    # Reset helpers
    # -------------------------------------------------------------------------

    def _tell_accuracy(self, player):
        if not hasattr(minqlx, "player_accuracy"):
            return
        try:
            acc = minqlx.player_accuracy(player.id)
        except ValueError:
            return
        if not acc:
            return
        hits, shots = acc
        pct = round(100 * hits / shots) if shots > 0 else 0
        player.tell(f"^7ACC: ^2{pct}%")

    def _reset_all(self, requester, target, silent=False):
        if not hasattr(minqlx, "reset_player_stats"):
            requester.tell("^1reset_player_stats not available — minqlx patch required.")
            return

        result = minqlx.reset_player_stats(target.id)

        if not result:
            requester.tell("^1Could not reset stats (player not fully connected?).")
            return

        minqlx.set_score(target.id, 0)

        if not silent:
            if requester.id == target.id:
                requester.tell("^2Stats reset. ^7Accuracy, K/D, and score are now 0.")
            else:
                requester.tell(f"^2Reset stats for ^7{target.clean_name}^2.")
                target.tell(f"^2Your stats were reset by ^7{requester.clean_name}^2.")

    def _reset_accuracy(self, requester, target, silent=False):
        if not hasattr(minqlx, "reset_player_accuracy"):
            requester.tell("^1reset_player_accuracy not available — minqlx patch required.")
            return

        result = minqlx.reset_player_accuracy(target.id)

        if not result:
            requester.tell("^1Could not reset accuracy (player not fully connected?).")
            return

        if not silent:
            if requester.id == target.id:
                requester.tell("^2Accuracy reset. ^7WEAP and +acc are now 0.")
            else:
                requester.tell(f"^2Reset accuracy for ^7{target.clean_name}^2.")
                target.tell(f"^2Your accuracy was reset by ^7{requester.clean_name}^2.")

    def _find_player(self, name_fragment):
        for p in self.players():
            if name_fragment in p.clean_name.lower():
                return p
        return None
