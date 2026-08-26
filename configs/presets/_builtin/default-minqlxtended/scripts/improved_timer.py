"""
improved_timer.py - Replace Sys_Milliseconds with a CLOCK_MONOTONIC source

How it works:
  The Q3 engine measures frame intervals with Sys_Milliseconds(), which
  internally calls gettimeofday() (wall clock).  Wall clock time can jump
  backwards or stall when the OS applies NTP corrections, producing
  irregular frame deltas that affect:
    - Physics and movement simulation (uses msec as the time step)
    - Lag-compensation rewind accuracy
    - Per-frame timing precision for statistical cheat detection

  improved_timer_hook.so patches Sys_Milliseconds in the running qzeroded
  process to use clock_gettime(CLOCK_MONOTONIC) instead.  The interface is
  identical (int milliseconds since first call), but the source is now a
  strictly monotonic, drift-free clock.

  The hook is loaded via ctypes at plugin load time — no LD_PRELOAD needed.

Commands:
  !timer  - Show whether the timing hook is active (perm 2)
"""

import minqlxtended
import ctypes
import os
import time


class improved_timer(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        lib_path = os.path.join(plugin_dir, "improved_timer_hook.so")

        try:
            self.lib = ctypes.CDLL(lib_path)
        except OSError as e:
            self.msg("^1[timer]^7 Failed to load {}: {}".format(lib_path, e))
            self.lib = None
            return

        self._setup_ctypes()
        self._rate_sample = None

        result = self.lib.init_hook()
        if result != 0:
            self.msg("^1[timer]^7 Hook installation failed (error {}).".format(result))
            return

        self.msg("^2[timer]^7 Sys_Milliseconds replaced with CLOCK_MONOTONIC.")
        self.add_command("timer", self.cmd_timer, 2)

    def _setup_ctypes(self):
        self.lib.init_hook.argtypes = []
        self.lib.init_hook.restype = ctypes.c_int

        self.lib.is_hook_active.argtypes = []
        self.lib.is_hook_active.restype = ctypes.c_int

        self.lib.get_call_count.argtypes = []
        self.lib.get_call_count.restype = ctypes.c_uint64

        self.lib.get_current_milliseconds.argtypes = []
        self.lib.get_current_milliseconds.restype = ctypes.c_int

        self.lib.get_last_milliseconds.argtypes = []
        self.lib.get_last_milliseconds.restype = ctypes.c_int

    def cmd_timer(self, player, msg, channel):
        if self.lib is None:
            channel.reply("^1[timer]^7 Library not loaded.")
            return
        if not self.lib.is_hook_active():
            channel.reply("^1[timer]^7 Hook is ^1not active^7.")
            return

        calls = self.lib.get_call_count()
        current_ms = self.lib.get_current_milliseconds()
        last_ms = self.lib.get_last_milliseconds()
        now = time.monotonic()

        rate_label = "avg"
        elapsed = current_ms / 1000.0 if current_ms > 0 else 0.0
        rate = calls / elapsed if elapsed > 0 else 0.0

        if self._rate_sample is not None:
            last_time, last_calls = self._rate_sample
            sample_elapsed = now - last_time
            if sample_elapsed > 0:
                rate_label = "recent"
                rate = (calls - last_calls) / sample_elapsed

        self._rate_sample = (now, calls)

        channel.reply(
            "^2[timer]^7 active | calls: ^5{}^7 | {}: ^5{:.1f}/s^7 | ms: ^5{}^7 | last: ^5{}^7".format(
                calls, rate_label, rate, current_ms, last_ms
            )
        )
