"""
serverchecker — minqlx plugin for live server status.

Writes live server status to Redis every 10 seconds, surfacing real-time
player counts, map, game state, and player details. Also used by the
ql-packet-fragmentation collector for per-player UDP port mapping.

Redis key: minqlx:server_status:<port>  (e.g. minqlx:server_status:27960)
"""

import minqlx
import json
import os
import re
import time
import threading
import zipfile


UPDATE_INTERVAL = 10  # seconds
EXPIRE_INTERVAL = 15  # seconds (time until data is automatically cleaned up)
WORKSHOP_CONTENT_REL_PATH = os.path.join('steamapps', 'workshop', 'content', '282440')
WORKSHOP_ID_RE = re.compile(r'^\s*(\d+)')


def _normalize_workshop_id(raw):
    """Extract leading numeric workshop ID from input."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = WORKSHOP_ID_RE.match(text)
    return match.group(1) if match else None


def _parse_workshop_file_ids(workshop_file_path):
    """Parse workshop.txt style file and return IDs in file order."""
    ids = []
    if not workshop_file_path or not os.path.isfile(workshop_file_path):
        return ids

    try:
        with open(workshop_file_path, 'r') as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                workshop_id = _normalize_workshop_id(stripped)
                if workshop_id:
                    ids.append(workshop_id)
    except Exception:
        return ids
    return ids


def _pk3_contains_map(pk3_path, map_name):
    """Return True when a pk3 archive contains maps/<map_name>.bsp."""
    target = f"maps/{map_name}.bsp".lower()
    try:
        with zipfile.ZipFile(pk3_path) as archive:
            for item in archive.namelist():
                if item.lower() == target:
                    return True
    except Exception:
        return False
    return False


def _resolve_map_workshop_item(map_name, candidate_ids, fs_basepath):
    """Resolve map -> workshop item ID by scanning candidate workshop pk3 archives."""
    if not map_name or not candidate_ids or not fs_basepath:
        return None

    map_key = str(map_name).strip().lower()
    if not map_key:
        return None

    seen_ids = set()
    for raw_id in candidate_ids:
        item_id = _normalize_workshop_id(raw_id)
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        item_dir = os.path.join(fs_basepath, WORKSHOP_CONTENT_REL_PATH, item_id)
        if not os.path.isdir(item_dir):
            continue

        try:
            for filename in sorted(os.listdir(item_dir)):
                if not filename.lower().endswith('.pk3'):
                    continue
                pk3_path = os.path.join(item_dir, filename)
                if _pk3_contains_map(pk3_path, map_key):
                    return item_id
        except Exception:
            continue

    return None


class serverchecker(minqlx.Plugin):

    def __init__(self):
        self.add_hook("game_start",        self.on_game_start)
        self.add_hook("game_end",          self.on_game_end)
        self.add_hook("player_connect",    self.on_player_connect)
        self.add_hook("player_disconnect", self.on_player_disconnect)
        self.add_hook("map",               self.on_map)

        self._match_start_time = None
        if self.game and self.game.state == "in_progress":
            self._match_start_time = time.time()  # fallback if plugin reloaded mid-game

        self._current_workshop_item = None
        self._resolved_map = None
        self._map_workshop_cache = {}

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        self.logger.info("serverchecker: plugin loaded, update thread started.")

    # ── Hooks ──────────────────────────────────────────────────────────────

    def on_game_start(self, data):
        self._match_start_time = time.time()
        self.update_status()

    def on_game_end(self, data):
        self._match_start_time = None
        self.update_status()

    def on_player_connect(self, player):
        self.update_status()

    def on_player_disconnect(self, player, reason):
        self.update_status()

    def on_map(self, mapname, factory):
        self._match_start_time = None
        self._refresh_workshop_item_for_map(mapname)
        self.update_status()

    # ── Update loop ────────────────────────────────────────────────────────

    def _update_loop(self):
        # self.logger.info("serverchecker: _update_loop entered.")
        while not self._stop_event.is_set():
            try:
                self.update_status()
            except Exception as e:
                self.logger.error(f"serverchecker: loop error: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
            self._stop_event.wait(UPDATE_INTERVAL)
        # self.logger.info("serverchecker: _update_loop exited.")

    # ── Status builder ─────────────────────────────────────────────────────

    def _candidate_workshop_ids(self):
        """Build ordered workshop ID candidates from runtime data and workshop file."""
        ordered_ids = []
        seen = set()

        try:
            game_items = getattr(self.game, 'workshop_items', []) if self.game else []
        except Exception:
            game_items = []

        for raw in game_items or []:
            item_id = _normalize_workshop_id(raw)
            if item_id and item_id not in seen:
                seen.add(item_id)
                ordered_ids.append(item_id)

        base_path = self.get_cvar("fs_basepath") or ""
        workshop_file_name = self.get_cvar("sv_workshopfile") or "workshop.txt"
        workshop_file_path = os.path.join(base_path, 'baseq3', workshop_file_name)
        for item_id in _parse_workshop_file_ids(workshop_file_path):
            if item_id not in seen:
                seen.add(item_id)
                ordered_ids.append(item_id)

        return ordered_ids

    def _refresh_workshop_item_for_map(self, map_name=None):
        """Resolve current map to workshop item once per map and cache result."""
        current_map = (map_name or (self.game.map if self.game else "") or "").strip().lower()
        if not current_map:
            self._resolved_map = None
            self._current_workshop_item = None
            return

        if current_map == self._resolved_map:
            return

        if current_map in self._map_workshop_cache:
            self._current_workshop_item = self._map_workshop_cache[current_map]
            self._resolved_map = current_map
            return

        base_path = self.get_cvar("fs_basepath") or ""
        workshop_item_id = _resolve_map_workshop_item(
            current_map,
            self._candidate_workshop_ids(),
            base_path,
        )
        self._map_workshop_cache[current_map] = workshop_item_id
        self._current_workshop_item = workshop_item_id
        self._resolved_map = current_map

    def update_status(self):
        try:
            port = self.get_cvar("net_port")
            # self.logger.info(f"serverchecker: update_status called for port {port}")

            players = []
            for p in self.players():
                try:
                    # Player.ip strips the port; use the raw field so Redis has the
                    # actual client UDP port that the eBPF program sees.
                    raw_ip = p["ip"] if "ip" in p else ""
                    players.append({
                        "name":  p.name,
                        "steam": str(p.steam_id),
                        "score": p.score if hasattr(p, "score") else 0,
                        "ping":  p.ping  if hasattr(p, "ping")  else 0,
                        "team":  str(p.team),
                        "udp_port": int(raw_ip.split(":")[1]) if raw_ip and ":" in raw_ip else None,
                    })
                except Exception as pe:
                    self.logger.warning(f"serverchecker: player error: {pe}")
                    continue

            def _safe_score(attr):
                try:
                    return getattr(game, attr) if game else 0
                except (ValueError, TypeError):
                    return 0

            game = self.game
            self._refresh_workshop_item_for_map(game.map if game else None)
            status = {
                "port":       port,
                "hostname":   self.get_cvar("sv_hostname") or "",
                "map":        game.map        if game else "?",
                "gametype":   game.type_short if game else "?",
                "factory":    game.factory    if game else "?",
                "state":      game.state      if game else "warmup",
                "players":    players,
                "maxplayers": int(self.get_cvar("sv_maxclients") or 16),
                "red_score":  _safe_score("red_score"),
                "blue_score": _safe_score("blue_score"),
                "match_start_time": int(self._match_start_time) if self._match_start_time and (game and game.state == "in_progress") else None,
                "workshop_item_id": self._current_workshop_item,
                "updated":    int(time.time()),
            }

            key   = f"minqlx:server_status:{port}"
            value = json.dumps(status)

            # self.logger.info(f"serverchecker: writing key={key} value={value[:120]}")
            self.db.set(key, value)

            # Expire key after EXPIRE_INTERVAL seconds to automatically clean up when server crashes or turns off
            self.db.expire(key, EXPIRE_INTERVAL)

            # self.logger.info(f"serverchecker: wrote OK — {len(players)} players on {status['map']} (expires in {EXPIRE_INTERVAL}s)")

        except Exception as e:
            self.logger.error(f"serverchecker: update_status error: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
