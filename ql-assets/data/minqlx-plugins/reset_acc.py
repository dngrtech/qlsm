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
"""

import minqlx

ADMIN_LEVEL = 2


class reset_acc(minqlx.Plugin):
    def __init__(self):
        self.add_command("resetstats", self.cmd_resetstats, 0)
        self.add_command("resetacc", self.cmd_resetacc, 0)

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

    def _reset_all(self, requester, target):
        if not hasattr(minqlx, "reset_player_stats"):
            requester.tell("^1reset_player_stats not available — minqlx patch required.")
            return

        result = minqlx.reset_player_stats(target.id)

        if not result:
            requester.tell("^1Could not reset stats (player not fully connected?).")
            return

        minqlx.set_score(target.id, 0)

        if requester.id == target.id:
            requester.tell("^2Stats reset. ^7Accuracy, K/D, and score are now 0.")
        else:
            requester.tell(f"^2Reset stats for ^7{target.clean_name}^2.")
            target.tell(f"^2Your stats were reset by ^7{requester.clean_name}^2.")

    def _reset_accuracy(self, requester, target):
        if not hasattr(minqlx, "reset_player_accuracy"):
            requester.tell("^1reset_player_accuracy not available — minqlx patch required.")
            return

        result = minqlx.reset_player_accuracy(target.id)

        if not result:
            requester.tell("^1Could not reset accuracy (player not fully connected?).")
            return

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
