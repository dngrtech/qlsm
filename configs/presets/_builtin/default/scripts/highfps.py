"""
highfps.py - MinQLX plugin to detect players using FPS > 360

How it works:
  Quake Live forces cl_maxpackets 125, so each client sends 125 packets/sec.
  The client packs ceil(fps/125) usercmds into each packet.  The engine's
  SV_ClientThink is called once per unique usercmd, so:

      SV_ClientThink calls/sec  ~=  client FPS

  A companion shared library (highfps_hook.so) hooks SV_ClientThink and
  maintains a per-client counter.  This plugin samples those counters
  periodically and computes estimated FPS.

Cvars:
  qlx_highfpsThreshold      - FPS at or above which action is taken (default 360)
  qlx_highfpsSampleInterval - Seconds between FPS checks (default 5)
  qlx_highfpsAction         - "warn" or "kick" (default "kick")
  qlx_highfpsWarnings       - Warnings before kick when action=kick (default 3)

Commands:
  !highfps  - Show estimated FPS for all connected players (perm 2)
"""

import minqlx
import ctypes
import os
import time


class highfps(minqlx.Plugin):
    def __init__(self):
        super().__init__()

        # ── Cvars ────────────────────────────────────────────────────
        self.set_cvar_once("qlx_highfpsThreshold", "360")
        self.set_cvar_once("qlx_highfpsSampleInterval", "5")
        self.set_cvar_once("qlx_highfpsAction", "kick")
        self.set_cvar_once("qlx_highfpsWarnings", "3")
        self.set_cvar_once("qlx_highfpsPadding", "10")

        # ── Per-player state ─────────────────────────────────────────
        self.warnings = {}      # steam_id -> warning count
        self.last_counts = {}   # client_id -> usercmd count at last sample
        self.last_sample_time = time.monotonic()
        self.frame_counter = 0

        # ── Load native hook library ─────────────────────────────────
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        lib_path = os.path.join(plugin_dir, "highfps_hook.so")

        try:
            self.lib = ctypes.CDLL(lib_path)
        except OSError as e:
            self.msg("^1[highfps]^7 Failed to load {}: {}".format(lib_path, e))
            return

        self._setup_ctypes()

        result = self.lib.init_hook()
        if result != 0:
            self.msg(
                "^1[highfps]^7 Hook installation failed (error {}).".format(result)
            )
            return

        self.msg("^2[highfps]^7 Hook installed successfully.")

        # ── Register hooks & commands ────────────────────────────────
        self.add_hook("frame", self.handle_frame)
        self.add_hook("map", self.handle_map)
        self.add_hook("player_disconnect", self.handle_disconnect)
        self.add_command("highfps", self.cmd_highfps, 2)

    # ── ctypes setup ─────────────────────────────────────────────────

    def _setup_ctypes(self):
        self.lib.init_hook.argtypes = []
        self.lib.init_hook.restype = ctypes.c_int

        self.lib.get_usercmd_count.argtypes = [ctypes.c_int]
        self.lib.get_usercmd_count.restype = ctypes.c_uint64

        self.lib.reset_usercmd_count.argtypes = [ctypes.c_int]
        self.lib.reset_usercmd_count.restype = None

        self.lib.reset_all_usercmd_counts.argtypes = []
        self.lib.reset_all_usercmd_counts.restype = None

        self.lib.is_hook_active.argtypes = []
        self.lib.is_hook_active.restype = ctypes.c_int

        self.lib.refresh_svs_clients.argtypes = []
        self.lib.refresh_svs_clients.restype = None

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_threshold(self):
        return int(self.get_cvar("qlx_highfpsThreshold") or "360")

    def _get_detection_threshold(self):
        return self._get_threshold() + int(self.get_cvar("qlx_highfpsPadding") or "10")

    def _get_action(self):
        return (self.get_cvar("qlx_highfpsAction") or "warn").lower()

    def _get_max_warnings(self):
        return int(self.get_cvar("qlx_highfpsWarnings") or "3")

    def _get_sample_interval(self):
        return int(self.get_cvar("qlx_highfpsSampleInterval") or "5")

    def _estimate_fps(self, client_id, elapsed):
        """Return estimated FPS for a client over the given elapsed time."""
        current = self.lib.get_usercmd_count(client_id)
        prev = self.last_counts.get(client_id, current)
        delta = current - prev
        self.last_counts[client_id] = current
        return delta / elapsed if elapsed > 0 else 0.0

    # ── Hook handlers ────────────────────────────────────────────────

    def handle_frame(self):
        self.frame_counter += 1

        sv_fps = int(self.get_cvar("sv_fps") or "40")
        target_frames = sv_fps * self._get_sample_interval()
        if self.frame_counter < target_frames:
            return

        self.frame_counter = 0
        now = time.monotonic()
        elapsed = now - self.last_sample_time
        self.last_sample_time = now

        if elapsed < 1.0:
            return

        threshold = self._get_threshold()
        detection = self._get_detection_threshold()
        action = self._get_action()
        max_warn = self._get_max_warnings()

        for player in self.players():
            fps = self._estimate_fps(player.id, elapsed)

            if fps < detection:
                continue

            sid = player.steam_id
            self.warnings[sid] = self.warnings.get(sid, 0) + 1
            wc = self.warnings[sid]

            player.tell(
                "^1[highfps] ^7Detected FPS: ^1~{:.0f}^7. "
                "Maximum allowed: ^3{}^7. Warning {}/{}.".format(
                    fps, threshold, wc, max_warn
                )
            )
            minqlx.console_print(
                "[highfps] {} (ID:{}) ~{:.0f} FPS "
                "(warning {}/{})\n".format(
                    player.clean_name, player.id, fps, wc, max_warn
                )
            )

            if action == "kick" and wc >= max_warn:
                name = player.clean_name
                self.msg(
                    "^1[highfps] ^7{} was kicked for using "
                    "^1~{:.0f} FPS ^7(max allowed: ^3{}^7).".format(
                        name, fps, threshold
                    )
                )
                player.kick(
                    "FPS too high (~{:.0f}). Max allowed: {}".format(
                        fps, threshold
                    )
                )
                self.warnings.pop(sid, None)

    def handle_map(self, mapname, factory):
        """Refresh svs->clients pointer and reset state on map change."""
        self.lib.refresh_svs_clients()
        self.lib.reset_all_usercmd_counts()
        self.last_counts.clear()
        self.last_sample_time = time.monotonic()
        self.frame_counter = 0

    def handle_disconnect(self, player, reason):
        """Clean up per-client state on disconnect."""
        self.lib.reset_usercmd_count(player.id)
        self.last_counts.pop(player.id, None)
        self.warnings.pop(player.steam_id, None)

    # ── Commands ─────────────────────────────────────────────────────

    def cmd_highfps(self, player, msg, channel):
        """!highfps - Show estimated FPS for all connected players."""
        if not self.lib.is_hook_active():
            channel.reply("^1[highfps]^7 Hook is not active.")
            return

        now = time.monotonic()
        elapsed = now - self.last_sample_time
        if elapsed < 1.0:
            channel.reply(
                "^3[highfps]^7 Collecting data, try again shortly."
            )
            return

        threshold = self._get_threshold()
        lines = ["^2[highfps] ^7Estimated player FPS:"]

        for p in self.players():
            current = self.lib.get_usercmd_count(p.id)
            prev = self.last_counts.get(p.id, 0)
            delta = current - prev
            fps = delta / elapsed

            color = "^1" if fps >= threshold else "^2"
            lines.append(
                "  {}: {}~{:.0f} FPS".format(p.clean_name, color, fps)
            )

        channel.reply("\n".join(lines))
