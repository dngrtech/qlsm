"""
footsteps.py - MinQLX plugin to restore audible footsteps at high client FPS

How it works:
  PM_Footsteps advances an 8-bit walk cycle by bobmove * msec and emits
  EV_FOOTSTEP when bit 7 of (cycle + 64) flips.  bobmove is 0.4 running and
  msec is an integer, so at 500 FPS every command contributes (int)(0.4 * 2)
  == 0, the cycle stops, and other players never hear the mover walk.

  footsteps_hook.so replaces one 26-byte site in qagamex64.so with a jump to a
  trampoline that keeps the fraction the cast throws away.  Cadence then
  matches the true 3.125 steps/s at every framerate.

  The game module is dlclose/dlopen'd whenever the level is reloaded, which
  discards the patch, so the plugin re-applies it on the new_game event,
  deferred one frame.  new_game and not map: a map_restart reloads the module
  exactly like a map change does, but minqlx suppresses the map event for it
  (`if not is_restart` in _handlers.handle_new_game) and dispatches only
  new_game.  Warmup ending is a map_restart — CheckTournament sends
  `map_restart 0` when the countdown expires, on every gametype — so hooking
  map alone loses the patch at the exact moment the match begins and never
  gets it back until the next map.  new_game fires on both paths.  Patching
  runs only on the game thread — never from a background thread, which would
  mean rewriting instructions another thread might be executing.

Cvars:
  qlx_footstepsSo - absolute path to footsteps_hook.so (default: next to this file)

Commands:
  !footsteps  - Report whether the patch is installed (perm 1)
"""

import minqlx
import ctypes
import os


# Mirrors the FS_* constants in footsteps_hook.c.
STATUS_TEXT = {
    1: "^2patched and active^7",
    0: "^3not patched^7 - qagamex64.so is not mapped yet",
    -1: "^1refused^7 - arithmetic selftest failed",
    -2: "^1not patched^7 - byte pattern not found in this qagame build",
    -3: "^1refused^7 - byte pattern matched more than once",
    -4: "^1not patched^7 - could not make the code page writable",
}


class footsteps(minqlx.Plugin):
    def __init__(self):
        super().__init__()

        self.set_cvar_once("qlx_footstepsSo", "")
        self.lib = None

        lib_path = (self.get_cvar("qlx_footstepsSo") or "").strip()
        if not lib_path:
            lib_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "footsteps_hook.so")
        self.lib_path = lib_path

        # Registered before the load attempt, deliberately. If the .so is
        # missing or refuses to load, !footsteps has to still answer and say so:
        # it is the operator's only in-game signal, and a status command that
        # disappears exactly when there is something to report is worse than
        # none. Registering after the try/except would also make the
        # `if self.lib is None` guards below unreachable dead code.
        self.add_hook("new_game", self.handle_new_game)
        self.add_command("footsteps", self.cmd_footsteps, 1)

        try:
            self.lib = ctypes.CDLL(lib_path)
        except OSError as e:
            self.msg("^1[footsteps]^7 Failed to load {}: {}".format(lib_path, e))
            return

        self._setup_ctypes()

        status = self.lib.footsteps_patch()
        if status == 1:
            self.msg("^2[footsteps]^7 Remainder hook installed.")
        elif status == 0:
            # Expected when the plugin loads before the first map is up. The
            # new_game hook installs it as soon as qagame is there.
            minqlx.console_print(
                "[footsteps] qagame not mapped yet; will patch on level load\n")
        else:
            self.msg("^1[footsteps]^7 Hook not installed ({}).".format(
                self._status_text(status)))

    def _setup_ctypes(self):
        self.lib.footsteps_patch.argtypes = []
        self.lib.footsteps_patch.restype = ctypes.c_int

        self.lib.footsteps_status.argtypes = []
        self.lib.footsteps_status.restype = ctypes.c_int

        self.lib.footsteps_hits.argtypes = []
        self.lib.footsteps_hits.restype = ctypes.c_uint64

        self.lib.footsteps_edges.argtypes = []
        self.lib.footsteps_edges.restype = ctypes.c_uint64

    def _status_text(self, status):
        return STATUS_TEXT.get(status, "^1unknown status {}^7".format(status))

    def handle_new_game(self):
        """Re-apply the patch: the game module is reloaded on every level load."""
        if self.lib is None:
            return
        self._repatch()

    @minqlx.next_frame
    def _repatch(self):
        """Deferred a frame to keep the rewrite off the dispatch stack.

        Not race protection: new_game is always dispatched *after* the module is
        back in memory, on both paths.  A map_restart runs VM_Restart (dlopen)
        and then G_InitGame, which dispatches; a map change dispatches only once
        SV_SpawnServer has returned.  So the scan cannot run against an unmapped
        qagame.  The deferral buys distance instead — footsteps_patch() rewrites
        live instruction bytes, and doing that from inside the event dispatch,
        with the engine's init frame still on the stack below, is a needless
        thing to have to reason about when one frame costs nothing.  No extra
        retry hook is needed: new_game fires on every level load and
        footsteps_patch() short-circuits when the patch is already live.
        """
        status = self.lib.footsteps_patch()
        if status != 1:
            minqlx.console_print(
                "[footsteps] patch not installed after level load: {}\n".format(
                    self._status_text(status)))

    def cmd_footsteps(self, player, msg, channel):
        if self.lib is None:
            player.tell("^1[footsteps]^7 Native hook is not loaded.")
            return minqlx.RET_STOP_ALL

        status = self.lib.footsteps_status()
        player.tell("^7[footsteps] {}".format(self._status_text(status)))
        player.tell("^7[footsteps] {} bob updates, {} step edges - {}".format(
            self.lib.footsteps_hits(), self.lib.footsteps_edges(), self.lib_path))
        return minqlx.RET_STOP_ALL
