"""
reset_acc - Reset scoreboard stats mid-game (accuracy, K/D, score).

Designed for FFA warmup/practice servers where players want per-fight
stats. After a fight, type !resetstats to zero your accuracy, kills,
deaths, and score so the next Tab press shows only that engagement.

Requires minqlx built with the reset_player_stats() and
reset_player_accuracy() C bindings.

Commands:
  !resetstats          - Reset accuracy, K/D, and score to 0
  !resetstats <name>   - Admin: reset another player's stats
  !resetacc            - Reset accuracy only (K/D unchanged)
  !resetacc <name>     - Admin: reset another player's accuracy only
  !autoresetacc        - Toggle accuracy reset after kills/deaths (2s)
  !autoresetstats      - Toggle full stats reset after kills/deaths (2s)
"""

import threading
import minqlx

ADMIN_LEVEL = 2
AUTO_RESET_DELAY = 2.0

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

        # {steam_id: {"mode": "both", "delay": 2.0}}
        self._auto_acc = {}
        self._auto_stats = {}
        # {steam_id: threading.Timer}
        self._pending_timers = {}

    # -------------------------------------------------------------------------
    # Redis persistence
    # -------------------------------------------------------------------------

    def _db_load(self, player, store, key):
        sid = player.steam_id
        mode = self.db.get(DB_KEY.format(sid, f"{key}:mode"))
        if mode not in ("kill", "death", "both"):
            return False
        pref = {"mode": "both", "delay": AUTO_RESET_DELAY}
        store[sid] = pref
        self._db_save(player, key, pref)
        return True

    def _db_save(self, player, key, pref):
        sid = player.steam_id
        if pref is None:
            self.db.delete(DB_KEY.format(sid, f"{key}:mode"))
            self.db.delete(DB_KEY.format(sid, f"{key}:delay"))
        else:
            self.db[DB_KEY.format(sid, f"{key}:mode")] = pref["mode"]
            self.db[DB_KEY.format(sid, f"{key}:delay")] = str(pref["delay"])

    def handle_loaded(self, player):
        sid = player.steam_id
        self._auto_acc.pop(sid, None)
        self._auto_stats.pop(sid, None)

        if self._db_load(player, self._auto_stats, "stats"):
            self._db_save(player, "acc", None)
        elif self._db_load(player, self._auto_acc, "acc"):
            self._db_save(player, "stats", None)
        else:
            self._db_save(player, "stats", None)
            self._db_save(player, "acc", None)

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
        self._handle_auto_toggle(
            player, msg, self._auto_acc, self._auto_stats,
            "accuracy", "autoresetacc", "acc", "stats"
        )
        return minqlx.RET_STOP_ALL

    def cmd_autoresetstats(self, player, msg, channel):
        self._handle_auto_toggle(
            player, msg, self._auto_stats, self._auto_acc,
            "stats", "autoresetstats", "stats", "acc"
        )
        return minqlx.RET_STOP_ALL

    def _handle_auto_toggle(self, player, msg, store, other_store, label,
                            cmd, db_key, other_db_key):
        if len(msg) != 1:
            player.tell(f"^7Usage: ^3!{cmd} ^7(toggle on/off)")
            return

        sid = player.steam_id
        self._cancel_pending(sid)

        if sid in store:
            store.pop(sid, None)
            self._db_save(player, db_key, None)
            player.tell(f"^7Auto-reset {label}: ^1disabled^7.")
            return

        other_store.pop(sid, None)
        self._db_save(player, other_db_key, None)
        pref = {"mode": "both", "delay": AUTO_RESET_DELAY}
        store[sid] = pref
        self._db_save(player, db_key, pref)
        player.tell(
            f"^7Auto-reset {label}: ^2enabled^7 after kills/deaths "
            f"(^2{AUTO_RESET_DELAY}s^7)."
        )

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
        client_id = player.id

        # Determine which reset applies (stats takes priority over acc)
        stats_pref = self._auto_stats.get(sid)
        acc_pref = self._auto_acc.get(sid)

        reset_fn = None
        delay = AUTO_RESET_DELAY

        if stats_pref and stats_pref["mode"] in (trigger, "both"):
            reset_fn = self._reset_all
        elif acc_pref and acc_pref["mode"] in (trigger, "both"):
            reset_fn = self._reset_accuracy

        if reset_fn is None:
            return

        if self._pending_timers.get(sid):
            return

        def _fire(fn=reset_fn, player_sid=sid, player_id=client_id):
            @minqlx.next_frame
            def _execute():
                if self._pending_timers.get(player_sid) is not timer:
                    return
                self._pending_timers.pop(player_sid, None)
                try:
                    current_player = self.player(player_id)
                except minqlx.NonexistentPlayerError:
                    return
                if not current_player or current_player.steam_id != player_sid:
                    return
                fn(current_player, current_player, silent=True)
            _execute()

        timer = threading.Timer(delay, _fire)
        timer.daemon = True
        self._pending_timers[sid] = timer
        try:
            timer.start()
        except Exception:
            if self._pending_timers.get(sid) is timer:
                self._pending_timers.pop(sid, None)
            raise

    # -------------------------------------------------------------------------
    # Disconnect cleanup
    # -------------------------------------------------------------------------

    def _cancel_pending(self, sid):
        timer = self._pending_timers.pop(sid, None)
        if timer is not None:
            timer.cancel()

    def handle_disconnect(self, player, reason):
        sid = player.steam_id
        self._cancel_pending(sid)
        self._auto_acc.pop(sid, None)
        self._auto_stats.pop(sid, None)

    # -------------------------------------------------------------------------
    # Reset helpers
    # -------------------------------------------------------------------------

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
