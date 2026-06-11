# Created by rage, (C)2026

# You can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.

# You should have received a copy of the GNU General Public License
# along with minqlx. If not, see <http://www.gnu.org/licenses/>.

# Prevents queue-skipping via rapid spectator-team cycling.
#
# Players who voluntarily leave an active team (red/blue/free) and enter
# spectator must wait MIN_SPEC_WAIT seconds before they can rejoin a team.
# This closes the exploit where pressing "team spectator; team 1" in a single
# bind lets a player skip the entire spec queue — commonly used to dodge an
# elo loss or reset scoreboard stats mid-game.
#
# The fix works at PRI_HIGHEST so it fires before specqueue.py processes the
# attempt, blocking the exploit regardless of game state or queue depth.
#
# COMMANDS (requires permission level 3):
#   !qguard          — show current status and wait time
#   !qguard on       — enable protection
#   !qguard off      — disable protection

import minqlx
import time

MIN_SPEC_WAIT = 15  # seconds a player must remain in spec after leaving an active team


class spec_switch_guard(minqlx.Plugin):
    def __init__(self):
        self.add_hook("team_switch", self.handle_team_switch, priority=minqlx.PRI_HIGH)
        self.add_hook("team_switch_attempt", self.handle_team_switch_attempt, priority=minqlx.PRI_HIGHEST)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.add_command("qguard", self.cmd_qguard, 3, usage="[on|off]")

        self._enabled = True
        self._spec_since = {}  # steam_id -> float: wall-clock time player entered spec from an active team

    def handle_team_switch(self, player, old_team, new_team):
        # Record only. Do NOT pop the entry here on spec->active: an in-frame
        # free->spec->free cycle (the queue-skip exploit) fires two
        # team_switch events back-to-back, and the second would wipe the
        # timer before team_switch_attempt can block the rejoiner. Entries
        # decay naturally on the next free->spec (overwrite) and are
        # cleaned on player_disconnect.
        if new_team == "spectator" and old_team in ("red", "blue", "free"):
            self._spec_since[player.steam_id] = time.time()

    def handle_team_switch_attempt(self, player, old_team, new_team):
        if not self._enabled:
            return
        if old_team != "spectator" or new_team == "spectator":
            return

        since = self._spec_since.get(player.steam_id)
        if since is None:
            return

        elapsed = time.time() - since
        if elapsed < MIN_SPEC_WAIT:
            wait = int(MIN_SPEC_WAIT - elapsed) + 1
            player.tell("^3You must wait ^1{}s^3 in spectator before rejoining.".format(wait))
            return minqlx.RET_STOP_ALL

    def handle_player_disconnect(self, player, reason):
        self._spec_since.pop(player.steam_id, None)

    def cmd_qguard(self, player, msg, channel):
        if len(msg) < 2:
            state = "^2ON" if self._enabled else "^1OFF"
            channel.reply("^3Queue skip guard is {}^3. Wait time: ^1{}s^3.".format(state, MIN_SPEC_WAIT))
            return

        arg = msg[1].lower()
        if arg == "on":
            self._enabled = True
            channel.reply("^3Queue skip guard ^2enabled^3.")
        elif arg == "off":
            self._enabled = False
            channel.reply("^3Queue skip guard ^1disabled^3.")
        else:
            return minqlx.RET_USAGE
