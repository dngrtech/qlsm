# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2026 Thomas Jones <me@thomasjones.id.au>

# This file is part of minqlxtended.

# minqlxtended is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# minqlxtended is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with minqlxtended. If not, see <http://www.gnu.org/licenses/>.

"""Slipgate integration: demo upload, map-asset contribution and server-planned balance.

    qlx_slipgateApiUrl             API root. Empty disables the plugin.
                                   Default: https://slipgate.gg/api/v1
    qlx_slipgateUploadToken        This server's sgs_... token. Collected automatically;
                                   set by hand from the manage page if not.  Default: unset
    qlx_slipgateServerAddr         The registered address, when net_ip is bind-all or the
                                   server is registered under a DNS name.  Default: unset
    qlx_slipgateUploadDemos        Upload finished demo segments.            Default: 0
    qlx_slipgateRetainDemos        Keep uploaded demos in <sv_demoDir>/uploaded/. Default: 0
    qlx_slipgateRecordRated        Record everyone from the map load.        Default: 1
    qlx_slipgateContributeAssets   Offer levelshots and BSPs Slipgate lacks. Default: 0
    qlx_slipgateAutoUpdate         Install the plugin build Slipgate offers, when no human
                                   is connected. 0 logs the offer instead.  Default: 1
    qlx_slipgateAutoBalance        Balance automatically when Slipgate's master switch
                                   allows it.                               Default: 1
    qlx_slipgateAutoSwitchBelow    Fairness below which automatic balancing acts.
                                                                            Default: 0.90
    qlx_slipgatePendingMax         Demos held before the oldest is dropped.  Default: 64
    qlx_slipgateSpoolMaxBytes      Demo directory cap, oldest deleted first. 0 is no cap.
                                                                            Default: 2 GiB
    qlx_slipgateSpoolMaxAgeHours   Delete unsent demos older than this.      Default: 72

Design: docs/minqlxtended-plugin.md in the Slipgate repository.
"""

import collections
import hashlib
import hmac
import ipaddress
import json
import os
import pathlib
import random
import secrets
import threading
import time
import urllib.parse
import zipfile

import minqlxtended
import requests

PLUGIN_VERSION = "1.10.1"

UPLOAD_TIMEOUT = (5, 120)
QUICK_TIMEOUT = (5, 10)
BACKOFF = (5, 30, 120, 600, 1800)
UPLOAD_REQUESTS_PER_MIN = 30
SWEEP_INTERVAL = 300
CONTRIBUTE_INTERVAL = 900
SWEEP_DEFAULT = 1800
REENROL_INTERVAL = 3600
ASSET_ATTEMPTS_PER_PASS = 512
ASSET_THROTTLE_MAX = 3600
PACE_SLICE = 5.0
ASSET_RECHECK_DEFAULT = 21600
RELEASE_MAX_BYTES = 1024 * 1024
UPDATE_STATE_CVAR = "qlx_slipgateUpdateState"
MIN_DEMO_BYTES = 1024
DEMO_MAX_BYTES = 64 * 1024 * 1024
LEVELSHOT_MAX_BYTES = 8 * 1024 * 1024
PREVIEW_MAX_BYTES = 2 * 1024 * 1024
BSP_MAX_BYTES = 64 * 1024 * 1024
ARENA_MAX_BYTES = 16 * 1024
LEVELSHOT_EXTENSIONS = ("jpg", "jpeg", "tga", "png")

_AssetKind = collections.namedtuple("_AssetKind", ("member", "flag", "endpoint", "max_bytes"))

ASSET_KINDS = {
    "levelshot": _AssetKind("levelshots/{name}.*", "has_levelshot",
                            "/ingest/assets/levelshot", LEVELSHOT_MAX_BYTES),
    "levelshot_preview": _AssetKind("levelshots/preview/{name}.*", "has_preview",
                                    "/ingest/assets/levelshot-preview", PREVIEW_MAX_BYTES),
    "bsp": _AssetKind("maps/{name}.bsp", None, "/ingest/assets/bsp", BSP_MAX_BYTES),
    "arena": _AssetKind(None, None, "/ingest/assets/arena", ARENA_MAX_BYTES),
}

KNOWN_VERBS = frozenset({"put", "switch", "suggest"})
KNOWN_OUTCOMES = frozenset(
    {"already_fair", "no_better_split", "budget_limited", "close_enough", "propose", "apply",
     "cannot_apply"}
)
StepResult = collections.namedtuple("StepResult", ("applied", "reason", "pair"),
                                    defaults=(False, None, None))
RunReport = collections.namedtuple("RunReport", ("applied", "planned", "stranded"))
BRAND = "^6Slipgate^7"
QL_PERCENT = chr(0xFF05)
NAME_IN_LINE = 12
# Five colour roles: ^6 accent, ^1 wrong and red, ^4 blue, ^3 caveat, ^7 text.
TEAM_COLOURS = {"red": "^1", "blue": "^4", "free": "^6", "spectator": ""}
MAX_LOOKUP_PLAYERS = 200

MAX_BALANCE_PLAYERS = 64
MIN_BALANCE_PLAYERS = 3
MAX_INSTRUCTIONS = MAX_BALANCE_PLAYERS + 8
SUGGESTION_TTL = 90
AUTO_DEBOUNCE = 5
AUTO_INTERVAL = 60
OUR_MOVE_TTL = 2
VOTE_SETTLE = 3.5
BALANCE_COOLDOWN = 3

CS_SLIPGATE_STAMP = 900

GAMETYPE_CODES = {
    minqlxtended.Gametype.CA: "ca", minqlxtended.Gametype.CTF: "ctf",
    minqlxtended.Gametype.TDM: "tdm", minqlxtended.Gametype.FREEZE_TAG: "ft",
    minqlxtended.Gametype.FFA: "ffa", minqlxtended.Gametype.DUEL: "duel",
    minqlxtended.Gametype.ATTACK_AND_DEFEND: "ad", minqlxtended.Gametype.DOMINATION: "domination",
    minqlxtended.Gametype.HARVESTER: "harvester", minqlxtended.Gametype.ONE_FLAG: "1flag",
    minqlxtended.Gametype.RED_ROVER: "redrover",
}
TEAM_GAMETYPE_CODES = frozenset({"ca", "ctf", "tdm", "ft", "ad", "domination", "harvester", "1flag"})
ROUND_BASED_CODES = frozenset({"ca", "ft", "ad"})
RATED_GAMETYPES = frozenset(GAMETYPE_CODES.values())
PLACEABLE_TEAMS = frozenset({minqlxtended.Team.RED, minqlxtended.Team.BLUE})

UPLOADED_DIR = "uploaded"
REJECTED_DIR = "rejected"

_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=2, max_retries=0))
_session.mount("http://", requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=2, max_retries=0))

class _PassEnded(Exception):
    def __init__(self, outcome, throttle=None):
        super().__init__(outcome)
        self.outcome = outcome
        self.throttle = throttle


def _member_key(name):
    return name.replace("\\", "/").lower()


def _is_local_host(host):
    if not host or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def header_safe(value):
    return str(value or "").encode("latin-1", "replace").decode("latin-1")


class slipgate(minqlxtended.Plugin):
    _qlx_slipgateApiUrl = minqlxtended.setting("qlx_slipgateApiUrl", "https://slipgate.gg/api/v1")
    _qlx_slipgateUploadDemos = minqlxtended.setting("qlx_slipgateUploadDemos", False)
    _qlx_slipgateRetainDemos = minqlxtended.setting("qlx_slipgateRetainDemos", False)
    _qlx_slipgateRecordRated = minqlxtended.setting("qlx_slipgateRecordRated", True)
    _qlx_slipgateContributeAssets = minqlxtended.setting("qlx_slipgateContributeAssets", False)
    _qlx_slipgateAutoUpdate = minqlxtended.setting("qlx_slipgateAutoUpdate", True)
    _qlx_slipgateAutoBalance = minqlxtended.setting("qlx_slipgateAutoBalance", True)
    _qlx_slipgateAutoSwitchBelow = minqlxtended.setting("qlx_slipgateAutoSwitchBelow", 0.90,
                                                        minimum=0, maximum=1)
    _qlx_slipgatePendingMax = minqlxtended.setting("qlx_slipgatePendingMax", 64,
                                                   minimum=8, maximum=1024)
    _qlx_slipgateSpoolMaxBytes = minqlxtended.setting("qlx_slipgateSpoolMaxBytes", 2147483648,
                                                      minimum=0, maximum=1099511627776)
    _qlx_slipgateSpoolMaxAgeHours = minqlxtended.setting("qlx_slipgateSpoolMaxAgeHours", 72,
                                                         minimum=1, maximum=8760)

    def __init__(self):
        super().__init__()
        self.set_cvar_once("qlx_slipgateUploadToken", "")
        self.set_cvar_once("qlx_slipgateServerAddr", "")

        self._map = None
        self._pending = {}  # path -> attempts
        self._lock = threading.RLock()
        self._draining = False
        self._upload_times = collections.deque()  # the last minute's uploads, oldest first
        self._upload_lock = threading.Lock()

        self._caps = {}
        self._caps_at = None
        self._stamp_state = None
        self._refused = {}  # scope -> reason; "all" is a 401, "demo"/"asset"/"update" a 403
        self._refused_token = None
        self._reenrol_after = 0.0
        self._balance_cooldown_until = 0.0
        self._round_number = None
        self._lobby_revision = 0
        self._auto_due_at = 0.0
        self._auto_reason = ""
        self._auto_next_at = 0.0
        self._our_moves = {}  # (client_id, team) -> expiry
        self._plan_seq = 0
        self._joined = {}  # steam_id -> arrival
        self._suggestion = None
        self._held_plan = None
        self._update_failed = {}  # version -> why it was refused; never cleared, see settle_update
        self._update_offered = None
        self._update_forced = False
        self._assets_offered = set()
        self._assets_next_at = 0.0
        self._asset_state = None
        self._workshop_items = ()
        self._sweep_next_at = 0.0
        self._contributing = False
        self._sweeping = False
        self._logged = set()
        self._health = {"uploaded": 0, "duplicate": 0, "rejected": 0,
                        "last_ok_at": 0.0, "last_error": "", "last_error_at": 0.0}

        self.settle_update()

        self.repeat(1, self.tick_auto_balance)
        self.repeat(SWEEP_INTERVAL, self.refresh_capabilities)
        self.repeat(SWEEP_INTERVAL, self.enrol)
        self.repeat(SWEEP_INTERVAL, self.sweep_spool)
        self.repeat(CONTRIBUTE_INTERVAL, self.contribute_assets)
        self.run_in_thread(self.fetch_capabilities, then=self.store_and_update)
        self.enrol()
        self.warn_if_insecure_url()
        self.warn_about_balance_plugin()
        self.register_votes()


    @property
    def api_url(self):
        return (self._qlx_slipgateApiUrl or "").rstrip("/")

    @property
    def upload_token(self):
        return (self.get_cvar("qlx_slipgateUploadToken") or "").strip()

    def is_configured(self):
        return bool(self.api_url)

    def warn_if_insecure_url(self):
        url = self.api_url
        if not url:
            return
        parts = urllib.parse.urlsplit(url)
        if parts.scheme == "https" or _is_local_host(parts.hostname):
            return
        self.log_once("insecure-url", "warning",
                      "slipgate: qlx_slipgateApiUrl is %s - the upload token and match data cross "
                      "the wire in clear. Point it at an https:// Slipgate for anything public.", url)

    def _blocker(self, enabled, cvar, scope, feature_ok, feature_off):
        if not self.is_configured():
            return "qlx_slipgateApiUrl is not set"
        if not enabled:
            return f"{cvar} is 0"
        if not self.upload_token:
            return "no upload token"
        blocked = self.paused_reason(scope)
        if blocked:
            return f"credential refused ({blocked})"
        return None if feature_ok else feature_off

    def upload_blocker(self):
        return self._blocker(self._qlx_slipgateUploadDemos, "qlx_slipgateUploadDemos", "demo",
                             self.feature_allowed("demo_upload"),
                             "Slipgate has demo ingest switched off")

    def contribute_blocker(self):
        return self._blocker(self._qlx_slipgateContributeAssets, "qlx_slipgateContributeAssets",
                             "asset", any(self.feature_allowed(f"asset_{k}") for k in ASSET_KINDS),
                             "Slipgate has asset contribution switched off")

    def can_upload(self):
        return self.upload_blocker() is None

    def can_contribute(self):
        return self.contribute_blocker() is None

    def feature_allowed(self, name):
        return bool(self._caps.get("features", {}).get(name, True))

    def declared_value(self, name):
        limits = self._caps.get("limits", {})
        raw = limits.get(name)
        if isinstance(raw, float) and raw.is_integer():
            raw = int(raw)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw if raw > 0 else None
        if name in limits:
            self.log_once(f"caps-type:{name}", "warning",
                          "slipgate: ignoring a declared %s of %r; it is not a whole "
                          "number, so this build's own value stands", name, raw)
        return None

    def declared_limit(self, name, fallback):
        value = self.declared_value(name)
        return int(fallback) if value is None else min(value, int(fallback))

    def declared_pace(self, name, fallback):
        value = self.declared_value(name)
        return int(fallback) if value is None else max(value, int(fallback))

    def warn_about_balance_plugin(self):
        if self.plugin("balance") is not None:
            self.log_once("balance-plugin", "warning",
                          "slipgate: balance.py is loaded as well as this plugin, and they "
                          "share !balance, !teams, !ratings, !elo, !do, !dl, !a and !prepare. "
                          "Every one of those now runs twice, once against qlstats and once "
                          "against Slipgate. Unload balance.py.")

    def register_votes(self):
        for name, handler, usage, description in (
            ("balance", self.vote_balance, "", "Balances the teams."),
            ("do", self.vote_do, "[now/later]",
             "Forces the suggested switch now, or at the start of the next round."),
            ("go", self.vote_go, "", "Balances the teams and begins the game."),
            ("prepare", self.vote_prepare, "", "Shuffles the teams, then balances the result."),
        ):
            try:
                self.add_vote(name, handler, usage, description)
            except ValueError:
                self.log_once(f"vote-name:{name}", "warning",
                              "slipgate: the '%s' vote is already registered, so balance.py or "
                              "an old custom_votes.py is still loaded and keeps it. Unload that "
                              "plugin and reload this one.", name)

    def log_once(self, key, level, message, *args):
        if key in self._logged:
            return
        self._logged.add(key)
        getattr(self.logger, level)(message, *args)


    def enrol(self):
        if not self.is_configured():
            return
        if not (self._qlx_slipgateUploadDemos or self._qlx_slipgateContributeAssets):
            return
        refused_outright = self._refused.get("all") == "HTTP 401"
        if self.upload_token and not refused_outright:
            return
        if refused_outright:
            if time.monotonic() < self._reenrol_after:
                return
            self._reenrol_after = time.monotonic() + REENROL_INTERVAL
        self.run_in_thread(self.enrol_now, then=self.store_token)

    def enrol_now(self):
        password = (self.get_cvar("zmq_stats_password") or "").strip()
        if not password:
            self.log_once("enrol-nopassword", "warning",
                          "slipgate: zmq_stats_password is not set, so this server cannot "
                          "collect an upload token automatically; mint one on the manage page")
            return None
        address = self.public_address()
        if not address:
            self.log_once("enrol-noaddress", "warning",
                          "slipgate: cannot tell which address this server is registered under "
                          "(net_ip is unset or 0.0.0.0). Set qlx_slipgateServerAddr to the "
                          "address it is registered with, or mint a token on the manage page")
            return None
        addr = f"{address}:{self.get_cvar('net_port') or '27960'}"
        nonce = secrets.token_hex(16)
        issued_at = int(time.time())
        message = f"{addr}\n{nonce}\n{issued_at}".encode()
        signature = hmac.new(password.encode(), message, hashlib.sha256).hexdigest()
        try:
            response = self.request("POST", "/ingest/enrol", token=False, json={
                "server_addr": addr, "nonce": nonce,
                "issued_at": issued_at, "signature": signature,
            })
        except requests.RequestException as exc:
            self.log_once("enrol-unreachable", "warning", "slipgate: enrolment failed: %s", exc)
            return None
        body = self.json_body(response) or {}
        if response.status_code != 200:
            detail = body.get("detail")
            self.log_once("enrol-refused", "warning",
                          "slipgate: enrolment refused (HTTP %d%s). Check this server is "
                          "registered at %s and that its stats password matches.",
                          response.status_code, f" - {detail}" if isinstance(detail, str) else "",
                          addr)
            return None
        for key in ("enrol-unreachable", "enrol-nopassword", "enrol-noaddress", "enrol-refused"):
            self._logged.discard(key)
        return body.get("token")

    def store_token(self, token):
        if not token:
            return
        self.set_cvar("qlx_slipgateUploadToken", token)
        self.logger.info("slipgate: collected this server's upload token")

    def public_address(self):
        override = (self.get_cvar("qlx_slipgateServerAddr") or "").strip()
        if override:
            return override.rsplit(":", 1)[0] if ":" in override else override
        ip = (self.get_cvar("net_ip") or "").strip()
        return ip if ip and ip != "0.0.0.0" else ""  # noqa: S104 - rejecting bind-all, not binding

    def credential_refused(self, code, context, scope="all"):
        if code not in (401, 403):
            return False
        self._refused_token = self.upload_token
        if code == 401:
            self._refused = {"all": "HTTP 401"}
            self.logger.error(
                "slipgate: the upload token was rejected on %s (HTTP 401); uploads and asset "
                "contribution are paused. The plugin will try to enrol a replacement, which "
                "works as long as zmq_stats_password here matches the registered one. If it "
                "does not, re-mint the token on the server manage page and set "
                "qlx_slipgateUploadToken.", context)
        else:
            self._refused[scope] = "HTTP 403"
            self.logger.error(
                "slipgate: %s was refused (HTTP 403). The token itself is valid, so a new one "
                "will not help: this server is either deactivated on Slipgate or its token "
                "lacks the %s scope. Check the server manage page.", context, scope)
        return True

    def paused_reason(self, scope):
        if not self._refused:
            return None
        if self.upload_token and self.upload_token != self._refused_token:
            self._refused = {}
            self._refused_token = None
            self._logged.clear()
            return None
        return self._refused.get("all") or self._refused.get(scope)

    def is_paused(self, scope="any"):
        if scope == "any":
            return bool(self.paused_reason("demo") or self.paused_reason("asset"))
        return self.paused_reason(scope) is not None


    def headers(self, token=True):
        out = {"X-Slipgate-Plugin-Version": PLUGIN_VERSION}
        state = self.update_state
        if state:
            out["X-Slipgate-Update-State"] = header_safe(state)
        if token and self.upload_token:
            out["Authorization"] = f"Bearer {self.upload_token}"
        return out

    def request(self, method, path, json=None, params=None, token=True, timeout=None,
                headers=None):
        sent = self.headers(token)
        if headers:
            sent.update(headers)
        return _session.request(method, f"{self.api_url}{path}", json=json, params=params,
                                headers=sent, timeout=timeout or QUICK_TIMEOUT)

    @staticmethod
    def json_body(response):
        try:
            body = response.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    def fetch_capabilities(self):
        if not self.is_configured() or not self.upload_token:
            return None
        try:
            response = self.request("GET", "/ingest/capabilities")
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        return self.json_body(response)

    def store_capabilities(self, caps):
        if not caps:
            return
        for key in ("features", "limits"):
            value = caps.get(key)
            if value is not None and not isinstance(value, dict):
                self.log_once("caps-shape", "warning",
                              "slipgate: ignoring a capability response whose %r is a %s, "
                              "not an object", key, type(value).__name__)
                return
        if caps != self._caps:
            self._assets_offered.clear()
            self._assets_next_at = 0.0
        self._caps = caps
        self._caps_at = time.monotonic()
        self._logged.discard("caps-shape")

    def refresh_capabilities(self):
        if self.is_configured() and not self.is_paused("all"):
            self.run_in_thread(self.fetch_capabilities, then=self.store_and_update)

    def store_and_update(self, caps):
        """Store the policy, then consider the build it offers. A ``then=``, so: game thread.

        """
        self.store_capabilities(caps)
        self.maybe_update()


    @property
    def update_state(self):
        return (self.get_cvar(UPDATE_STATE_CVAR) or "").strip()

    def settle_update(self):
        """Say whether the previous update worked. Runs in whichever build is now live."""
        self.set_cvar_once(UPDATE_STATE_CVAR, "")
        verb, _, rest = self.update_state.partition(":")
        version, _, reason = rest.partition(":")
        if verb == "pending" and version:
            if version == PLUGIN_VERSION:
                self.set_cvar(UPDATE_STATE_CVAR, f"ok:{version}")
                self.logger.info("slipgate: updated to %s", version)
            else:
                self.refuse_version(version, "version", announce=False)
        elif verb == "rollback" and version:
            self._update_failed[version] = reason or "rollback"

    def refuse_version(self, version, reason, announce=True):
        """Mark ``version`` as one this box will not try again, and record why."""
        self._update_failed[version] = reason
        self.set_cvar(UPDATE_STATE_CVAR, f"rollback:{version}:{reason}"[:64])
        if announce:
            self.logger.error("slipgate: refused plugin release %s (%s)", version, reason)

    def offered_release(self):
        """The release Slipgate is offering this server, as a dict, or None."""
        offered = self._caps.get("plugin_release")
        if not isinstance(offered, dict):
            return None
        version, sha = offered.get("version"), offered.get("sha256")
        if not isinstance(version, str) or not isinstance(sha, str) or not version or not sha:
            return None
        return {"version": version, "sha256": sha}

    def human_players(self):
        """The roster minus bots, for the emptiness checks. Not valid in a `player_connect`
        handler: SVF_BOT is set after that event, so use its own `is_bot` argument there."""
        return [p for p in self.players() if not self.looks_like_a_bot(p)]

    def looks_like_a_bot(self, player):
        """SVF_BOT, else the steam id QL gives a bot. An unreadable client counts as human."""
        try:
            if player.is_bot:
                return True
        except Exception:
            self.logger.debug("slipgate: could not read SVF_BOT for client %s",
                              getattr(player, "id", "?"))
        try:
            return str(player.steam_id).strip() == "0"
        except Exception:
            self.logger.debug("slipgate: could not read the steam id for client %s",
                              getattr(player, "id", "?"))
        return False

    def update_blocker(self):
        """Why a self-update cannot happen right now, or None. The status line reads this."""
        if not self.is_configured() or not self.upload_token:
            return "not configured"
        if self.is_paused("update"):
            return "the token was refused"
        if not self._qlx_slipgateAutoUpdate:
            return "qlx_slipgateAutoUpdate is 0"
        return None

    def maybe_update(self, forced=False, player=None):
        """Decide whether to fetch the offered build. Game thread only - it reads the roster."""
        offered = self.offered_release()
        self._update_offered = offered["version"] if offered else None
        if offered is None or offered["version"] == PLUGIN_VERSION:
            return False
        version = offered["version"]
        if version in self._update_failed:
            return False
        blocker = self.update_blocker()
        if blocker:
            self.log_once(f"update-offer:{version}", "warning",
                          "slipgate: plugin %s is available (running %s), and this server is not "
                          "taking it: %s", version, PLUGIN_VERSION, blocker)
            return False
        if self.human_players() and not forced:
            return False
        password = (self.get_cvar("zmq_stats_password") or "").strip()
        if not password:
            self.log_once("update-nopassword", "warning",
                          "slipgate: zmq_stats_password is not set, so a plugin release cannot "
                          "be verified and will not be installed")
            return False
        self._update_forced = forced
        self.run_in_thread(self.download_release, offered, password, then=self.install_release)
        if player is not None:
            self.tell(player, f"fetching plugin {version}.")
        return True

    def download_release(self, offered, password):
        """Fetch, verify and compile the offered build. Worker thread: no engine reads here.

        """
        version, expected_sha = offered["version"], offered["sha256"]
        try:
            response = self.request("GET", "/ingest/plugin", timeout=UPLOAD_TIMEOUT)
        except requests.RequestException as exc:
            self.log_once("update-unreachable", "warning",
                          "slipgate: could not fetch plugin %s (%s)", version, type(exc).__name__)
            return None
        if self.credential_refused(
            response.status_code, f"fetching plugin {version}", scope="update"
        ):
            return None
        if response.status_code != 200:
            self.log_once(f"update-http:{version}", "warning",
                          "slipgate: fetching plugin %s answered HTTP %d",
                          version, response.status_code)
            return None
        body = response.content or b""
        if not body or len(body) > RELEASE_MAX_BYTES:
            return {"version": version, "refused": "size"}
        actual = hashlib.sha256(body).hexdigest()
        if actual != expected_sha or actual != (response.headers.get("X-Slipgate-Sha256") or ""):
            return {"version": version, "refused": "sha256"}
        if (response.headers.get("X-Slipgate-Plugin-Version") or "") != version:
            return {"version": version, "refused": "version"}
        expected_sig = hmac.new(
            password.encode(), f"{version}\n{actual}".encode(), hashlib.sha256
        ).hexdigest()
        signature = (response.headers.get("X-Slipgate-Signature") or "").lower()
        if not hmac.compare_digest(expected_sig.encode(), signature.encode()):
            return {"version": version, "refused": "signature"}
        if version != self.declared_version(body):
            return {"version": version, "refused": "declared"}
        try:
            compile(body, "slipgate.py", "exec")
        except (SyntaxError, ValueError):
            return {"version": version, "refused": "compile"}
        return {"version": version, "body": body}

    @staticmethod
    def declared_version(body):
        for line in body.splitlines():
            if line.startswith(b"PLUGIN_VERSION"):
                _, _, value = line.partition(b"=")
                return value.strip().strip(b"'\"").decode("latin-1")
        return None

    def install_release(self, release):
        forced, self._update_forced = self._update_forced, False
        if not release:
            return
        version = release["version"]
        if release.get("refused"):
            self.refuse_version(version, release["refused"])
            return
        # The download took time; the server may have filled up while it ran.
        if self.human_players() and not forced:
            return
        path = self.plugin_source_path()
        if path is None:
            self.refuse_version(version, "path")
            return
        try:
            previous = pathlib.Path(path).read_bytes()
            temporary = f"{path}.new"
            with open(temporary, "wb") as handle:
                handle.write(release["body"])
            with open(f"{path}.bak", "wb") as handle:
                handle.write(previous)
            os.replace(temporary, path)
        except OSError as exc:
            self.refuse_version(version, "write")
            self.logger.error("slipgate: could not write plugin %s: %s", version, exc)
            return
        self.logger.info("slipgate: installing plugin %s, reloading", version)
        self.set_cvar(UPDATE_STATE_CVAR, f"pending:{version}")
        self.reload_onto(version, path, previous)

    def plugin_source_path(self):
        plugins = (self.get_cvar("qlx_pluginsPath") or "").strip()
        if not plugins:
            return None
        path = os.path.join(os.path.abspath(plugins), f"{type(self).__name__}.py")
        return path if os.path.isfile(path) else None

    @minqlxtended.next_frame
    def reload_onto(self, version, path, previous):
        """Swap this plugin for the file now at ``path``, restoring ``previous`` if that fails.

        """
        name = type(self).__name__
        try:
            minqlxtended.reload_plugin(name)
        except Exception as exc:
            self.logger.error(
                "slipgate: plugin %s failed to load, restoring the previous build: %s",
                version, exc)
            try:
                with open(path, "wb") as handle:
                    handle.write(previous)
                minqlxtended.load_plugin(name)
            except Exception:
                self.logger.error(
                    "slipgate: could NOT restore the previous build at %s. The plugin is not "
                    "loaded. Put a working slipgate.py there and run !load slipgate", path)
            self.refuse_version(version, "reload")



    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot):
        if self._qlx_slipgateRecordRated and self.can_upload():
            player.record_demo()
        self.remember_joined(player)

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        self.forget_joined(player)
        if str(getattr(player, "team", "")) in ("red", "blue"):
            self.lobby_changed("somebody left")

    def lobby_changed(self, reason, arm=True):
        self._lobby_revision += 1
        self._suggestion = None
        self.drop_held_plan("lobby_changed")
        if arm:
            self.arm_auto_balance(reason)

    def remember_joined(self, player):
        try:
            self._joined.setdefault(str(player.steam_id), time.monotonic())
        except Exception:
            self.logger.debug("slipgate: could not stamp the arrival of client %s", player.id)

    def forget_joined(self, player):
        try:
            steam_id = str(player.steam_id)
        except Exception:
            return
        for member in self.players():
            if str(member.steam_id) == steam_id and member.id != player.id:
                return
        self._joined.pop(steam_id, None)

    def connected_sec(self, player):
        since = self._joined.get(str(player.steam_id))
        return None if since is None else int(time.monotonic() - since)

    def snapshot_workshop_items(self):
        try:
            self._workshop_items = tuple(self.game.workshop_items or ())
        except Exception:
            self.logger.debug("slipgate: could not read the workshop item list")

    @minqlxtended.hook("map")
    def handle_map(self, mapname, factory):
        self.snapshot_workshop_items()
        self.offer_this_map(mapname)
        self._suggestion = None
        self.drop_held_plan("map_changed")
        self._lobby_revision += 1
        self.warn_about_balance_plugin()
        self._map = mapname
        self._round_number = None
        self.reset_auto_balance()
        if self._qlx_slipgateRecordRated and self.can_upload():
            self.start_recording()

    @minqlxtended.hook("game_start")
    def handle_game_start(self):
        guid = minqlxtended.configstring(minqlxtended.CS_MATCH_GUID).strip()
        self._round_number = None
        self._lobby_revision += 1
        if guid:
            self.run_in_thread(self.fetch_stamp, guid, then=self.apply_stamp)
        self._suggestion = None
        self.drop_held_plan("match_started")

    @minqlxtended.hook("game_end")
    def handle_game_end(self, aborted):
        self._lobby_revision += 1
        self.reset_auto_balance()
        self._suggestion = None
        self.drop_held_plan("match_ended")

    def fetch_stamp(self, guid):
        if not self.is_configured() or not self.upload_token:
            return None
        try:
            response = self.request("POST", "/ingest/match-stamp", json={"match_guid": guid})
        except requests.RequestException as exc:
            self.log_once("stamp-fetch", "warning",
                          "slipgate: could not reach Slipgate for a match stamp (%s); demos "
                          "from this match will carry none", type(exc).__name__)
            return None
        if response.status_code != 200:
            self.log_once("stamp-fetch", "warning",
                          "slipgate: Slipgate refused a match stamp (HTTP %d); demos from "
                          "this match will carry none", response.status_code)
            return None
        self._logged.discard("stamp-fetch")
        body = self.json_body(response)
        return body.get("stamp") if body else None

    def apply_stamp(self, stamp):
        self._stamp_state = "not requested" if not stamp else None
        if not stamp:
            return
        try:
            minqlxtended.set_configstring(CS_SLIPGATE_STAMP, stamp)
        except (ValueError, minqlxtended.EngineStateError) as exc:
            self._stamp_state = f"refused at {CS_SLIPGATE_STAMP} ({type(exc).__name__})"
            self.log_once("stamp", "warning",
                          "slipgate: the engine refused configstring %d for the match stamp "
                          "(%s: %s). Demos from this match will carry no stamp, so nothing "
                          "binds them to this server beyond the upload token.",
                          CS_SLIPGATE_STAMP, type(exc).__name__, exc)
            return
        try:
            stored = minqlxtended.configstring(CS_SLIPGATE_STAMP, cached=False)
        except Exception:
            stored = None
        if stored == stamp:
            self._stamp_state = f"set at {CS_SLIPGATE_STAMP}"
            self._logged.discard("stamp")
        else:
            self._stamp_state = f"did not stick at {CS_SLIPGATE_STAMP}"
            self.log_once("stamp", "warning",
                          "slipgate: configstring %d accepted the match stamp but read back "
                          "%r. The index is probably outside this build's CS_MAX; demos will "
                          "carry no stamp until it is moved.", CS_SLIPGATE_STAMP, stored)

    def start_recording(self):
        for player in self.players():
            if player.team != minqlxtended.Team.SPECTATOR:
                player.record_demo()


    @minqlxtended.hook("demo_finished")
    def handle_demo_finished(self, client_id, path, size, discarded, failed):
        if discarded or not self.can_upload():
            return
        if not self.within_demo_root(path):
            self.logger.warning("slipgate: ignoring a demo outside the demo directory: %s", path)
            return
        limit = self.declared_limit("demo_max_bytes", DEMO_MAX_BYTES)
        if size and size > limit:
            self.logger.warning("slipgate: demo %s is %d bytes, over the %d cap", path, size, limit)
            return
        if size is not None and 0 <= size < MIN_DEMO_BYTES:
            self.logger.warning("slipgate: demo %s is only %d bytes; not uploading it", path, size)
            return
        self.add_pending(path)
        self.drain_soon()

    def within_demo_root(self, path):
        root = self.demo_root()
        if root is None:
            return False
        return pathlib.Path(os.path.realpath(path)).is_relative_to(os.path.realpath(root))

    def demo_root(self):
        home = self.get_cvar("fs_homepath")
        if not home:
            return None
        subdir = self.get_cvar("sv_demoDir") or "demos"
        return os.path.join(home, subdir.lstrip("/\\"))

    def add_pending(self, path, attempts=0):
        with self._lock:
            self._pending[path] = attempts
            while len(self._pending) > self._qlx_slipgatePendingMax:
                del self._pending[next(iter(self._pending))]
                self.log_once("pending", "warning",
                              "slipgate: more than %d demos are waiting; dropping the oldest",
                              self._qlx_slipgatePendingMax)

    def take_pending(self):
        with self._lock:
            for path in list(self._pending):
                return path, self._pending.pop(path)
        return None

    def put_back(self, path, attempts):
        with self._lock:
            self._pending[path] = attempts


    def drain_soon(self):
        with self._lock:
            if self._draining or not self._pending:
                return
            self._draining = True
        self.run_in_thread(self.drain, then=self.drain_finished)

    def drain(self):
        try:
            while self.is_loaded and not self.is_paused("demo"):
                item = self.take_pending()
                if item is None:
                    return None
                path, attempts = item
                wait = self.upload_pacing()
                if wait is not None:
                    self.put_back(path, attempts)
                    return wait
                try:
                    wait = self.upload(path, attempts)
                except OSError as exc:
                    self.logger.warning("slipgate: could not read %s: %s", path, exc)
                    continue
                if wait is not None:
                    return wait
            return None
        finally:
            self._draining = False

    def upload_pacing(self):
        limit = self.declared_limit("upload_requests_per_min", UPLOAD_REQUESTS_PER_MIN)
        now = time.monotonic()
        with self._upload_lock:
            window = self._upload_times
            while window and now - window[0] >= 60.0:
                window.popleft()
            if len(window) < limit:
                window.append(now)
                return None
            return max(0.5, 60.0 - (now - window[0]))

    def pace_upload(self):
        while True:
            wait = self.upload_pacing()
            if wait is None:
                return True
            time.sleep(min(wait, PACE_SLICE))
            if not self.is_loaded:
                return False

    def drain_finished(self, wait):
        self._draining = False
        if wait is not None and self.is_loaded:
            self.delay(wait, self.drain_soon)
        elif self._pending and not self.is_paused("demo"):
            self.drain_soon()

    def upload(self, path, attempts):
        """Worker. Returns seconds to back off, or None."""
        if not os.path.isfile(path):
            return None
        digest, byte_count = self.hash_file(path)
        headers = self.headers()
        headers.update({"Content-Type": "application/octet-stream",
                        "X-Slipgate-Sha256": digest,
                        "X-Slipgate-Bytes": str(byte_count)})
        try:
            with open(path, "rb") as handle:
                response = _session.post(f"{self.api_url}/ingest/demos", data=handle, headers=headers,
                                         timeout=UPLOAD_TIMEOUT)
        except requests.RequestException as exc:
            return self.defer(path, attempts, f"{type(exc).__name__}: {exc}")
        return self.handle_upload_response(path, attempts, response)

    def handle_upload_response(self, path, attempts, response):
        code = response.status_code
        if code == 200:
            body = self.json_body(response) or {}
            self.note_success(body.get("status", "stored") == "stored")
            self._logged.discard("upload")
            for warning in (body.get("warnings") or [])[:4]:
                text = str(warning)[:120]
                self.log_once(f"upload-warning:{text}", "warning",
                              "slipgate: %s accepted with a warning: %s",
                              os.path.basename(path), text)
            if body.get("accepted", True):
                self.retire(path)
            return None
        if self.credential_refused(code, "demo upload", scope="demo"):
            self.put_back(path, attempts)
            return None
        if code in (413, 415, 422):
            why = (self.json_body(response) or {}).get("detail") or f"HTTP {code}"
            self.note_error(why, rejected=True)
            self.logger.warning("slipgate: %s refused - %s; moving it aside to %s/",
                                path, why, REJECTED_DIR)
            self.retire(path, folder=REJECTED_DIR)
            return None
        if code == 429:
            retry_after = response.headers.get("Retry-After", "")
            wait = min(int(retry_after), BACKOFF[-1]) if retry_after.isdigit() else None
            return self.defer(path, attempts, "HTTP 429", wait=wait)
        return self.defer(path, attempts, f"HTTP {code}")

    def note_success(self, kept):
        self._health["uploaded" if kept else "duplicate"] += 1
        self._health["last_ok_at"] = time.time()

    def note_error(self, reason, rejected=False):
        self._health["last_error"] = str(reason)[:120]
        self._health["last_error_at"] = time.time()
        if rejected:
            self._health["rejected"] += 1

    def defer(self, path, attempts, reason, wait=None):
        self.note_error(reason)
        if attempts >= len(BACKOFF):
            self.log_once("upload", "warning",
                          "slipgate: uploads failing (%s); deferring to the sweep", reason)
            return None
        self.put_back(path, attempts + 1)
        if wait is not None:
            return wait
        return BACKOFF[attempts] * random.uniform(0.8, 1.2)  # noqa: S311 - jitter, not a secret

    @staticmethod
    def hash_file(path):
        with open(path, "rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            return digest, handle.tell()

    def retire(self, path, folder=None):
        """Delete or move aside, only ever after a response."""
        keep = folder or (UPLOADED_DIR if self._qlx_slipgateRetainDemos else None)
        try:
            if keep:
                target = os.path.join(os.path.dirname(path), keep)
                os.makedirs(target, exist_ok=True)
                os.replace(path, os.path.join(target, os.path.basename(path)))
            else:
                os.unlink(path)
        except OSError as exc:
            self.logger.warning("slipgate: could not retire %s: %s", path, exc)


    def sweep_spool(self, force=False):
        if not self._qlx_slipgateUploadDemos:
            return
        if not force and (self._sweeping or time.monotonic() < self._sweep_next_at):
            return
        self._sweep_next_at = time.monotonic() + self.declared_pace("sweep_interval_sec", SWEEP_DEFAULT)
        self._sweeping = True
        self.run_in_thread(self.sweep_now, self.open_recordings(), then=self.sweep_finished)

    def open_recordings(self):
        slots = self.get_cvar("sv_maxclients", int)
        if not isinstance(slots, int) or isinstance(slots, bool) or slots <= 0:
            self.log_once("sweep", "warning", "slipgate: sv_maxclients is not readable; "
                                              "skipping the spool sweep")
            return None
        try:
            return {os.path.realpath(status.path)
                    for status in (minqlxtended.demo_status(client_id) for client_id in range(slots))
                    if status.recording and status.path}
        except Exception:
            self.log_once("sweep", "warning", "slipgate: could not read the recording slots; "
                                              "skipping the spool sweep")
            return None

    def sweep_now(self, recording):
        try:
            return self._sweep(recording)
        finally:
            self._sweeping = False

    def _sweep(self, recording):
        if recording is None:
            return False
        root = self.demo_root()
        if not root or not os.path.isdir(root):
            return False
        found = []
        unusable = set()
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in (UPLOADED_DIR, REJECTED_DIR)]
            for name in files:
                if not name.endswith(".dm_91"):
                    continue
                path = os.path.join(base, name)
                if os.path.realpath(path) in recording:
                    continue
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                found.append((stat.st_mtime, stat.st_size, path))
                if stat.st_size < MIN_DEMO_BYTES:
                    unusable.add(path)
        if self.can_upload():
            for _mtime, _size, path in sorted(found):
                if path in unusable:
                    continue
                with self._lock:
                    if path in self._pending:
                        continue
                self.add_pending(path)
        self.enforce_spool_cap(found)
        return bool(self._pending)

    def enforce_spool_cap(self, found):
        cap = self._qlx_slipgateSpoolMaxBytes or float("inf")
        cutoff = time.time() - self._qlx_slipgateSpoolMaxAgeHours * 3600
        total = sum(size for _mtime, size, _path in found)
        removed = freed = 0
        for mtime, size, path in sorted(found):
            if total <= cap and mtime >= cutoff:
                break
            if not self.is_loaded:
                break
            try:
                os.unlink(path)
            except OSError:
                continue
            with self._lock:
                self._pending.pop(path, None)
            total -= size
            freed += size
            removed += 1
        if removed:
            self.logger.warning("slipgate: spool over cap, removed %d demos (%.1f MB)",
                                removed, freed / 1e6)
        blocker = self.upload_blocker()
        if total > cap and blocker:
            self.log_once("spool", "warning",
                          "slipgate: the demo spool is over cap and uploads are off (%s); "
                          "the disk will fill", blocker)

    def sweep_finished(self, has_work):
        self._sweeping = False
        if has_work:
            self.drain_soon()


    def offer_this_map(self, mapname):
        if mapname and self.can_contribute():
            self.run_in_thread(self.offer_map_now, str(mapname).lower())

    def offer_map_now(self, name):
        """Worker. One map, no cadence of its own."""
        try:
            info = minqlxtended.map_info(name)
            if info is None:
                info = minqlxtended.map_info(name, refresh=True)
        except Exception as exc:
            self.log_once("assets-scan", "warning",
                          "slipgate: could not look up %s: %s", name, exc)
            return
        if info is None or self.is_paused("asset"):
            return
        answer = self.ask_wanted([info.name])
        entries = [entry for entry in (answer or {}).get("maps") or []
                   if entry.get("map") == info.name]
        if not entries:
            return
        for kind in entries[0].get("wanted") or []:
            _sent, retry_after = self.offer_asset(info, kind)
            if retry_after is not None:
                break

    def contribute_assets(self, force=False, player=None):
        """Timer. True when a pass started."""
        if self._contributing or not self.can_contribute():
            return False
        if not force and time.monotonic() < self._assets_next_at:
            return False
        self._contributing = True
        self.run_in_thread(self.contribute_now, player, then=self.report_forced_pass)
        return True

    def contribute_now(self, player=None):
        try:
            summary = self._contribute()
        finally:
            self._contributing = False
        summary["player"] = player
        return summary

    def _check_pass(self):
        if self.is_paused("asset") or not self.is_loaded:
            raise _PassEnded("failed")

    def _contribute(self):
        try:
            maps = {info.name: info for info in minqlxtended.installed_maps()}
        except Exception as exc:
            self.log_once("assets-scan", "warning",
                          "slipgate: could not scan the installed maps: %s", exc)
            maps = {}
        if not maps:
            self._assets_next_at = time.monotonic() + CONTRIBUTE_INTERVAL
            return {"sent": 0, "outcome": "failed", "resume_sec": CONTRIBUTE_INTERVAL}

        sent = attempts = wanted_pairs = 0
        throttle = None
        outcome = "exhausted"
        try:
            self._check_pass()
            answer = self.ask_wanted(sorted(maps))
            if answer is None:
                raise _PassEnded("failed")
            for entry in answer.get("maps") or []:
                info = maps.get(entry.get("map"))
                if info is None:
                    continue
                if not self.is_loaded:
                    raise _PassEnded("failed")
                for kind in entry.get("wanted") or []:
                    wanted_pairs += 1
                    if not self.asset_outstanding(info.name, kind):
                        continue
                    self._check_pass()
                    if attempts >= ASSET_ATTEMPTS_PER_PASS:
                        raise _PassEnded("capped")
                    if not self.pace_upload():
                        raise _PassEnded("failed")
                    attempts += 1
                    kept, retry_after = self.offer_asset(info, kind)
                    sent += 1 if kept else 0
                    if retry_after is not None:
                        raise _PassEnded("throttled", retry_after)
        except _PassEnded as end:
            outcome, throttle = end.outcome, end.throttle

        if outcome == "exhausted":
            resume = self.declared_pace("asset_recheck_sec", ASSET_RECHECK_DEFAULT)
        else:
            resume = CONTRIBUTE_INTERVAL if throttle is None else throttle
        self._assets_next_at = time.monotonic() + resume
        self.report_pass(maps, wanted_pairs, sent, outcome)
        return {"sent": sent, "outcome": outcome, "resume_sec": resume}

    def report_pass(self, maps, wanted_pairs, sent, outcome):
        """One line whenever the snapshot changes."""
        workshop_maps = sum(
            1 for info in maps.values() if any(s.workshop_id for s in info.sources))
        pk3s = len({s.pk3_path for info in maps.values() for s in info.sources})
        snapshot = {"maps": len(maps), "workshop_maps": workshop_maps, "pk3s": pk3s,
                    "wanted": wanted_pairs, "sent": sent, "outcome": outcome,
                    "at": time.monotonic()}
        changed = self._asset_state is None or any(
            snapshot[k] != self._asset_state[k]
            for k in ("maps", "workshop_maps", "wanted", "sent", "outcome"))
        self._asset_state = snapshot
        if changed:
            self.logger.info(
                "slipgate: %d map(s) installed, %d from workshop items, %d pk3; "
                "%d asset(s) wanted, %d sent; %s",
                len(maps), workshop_maps, pk3s, wanted_pairs, sent, outcome)
        if maps and not workshop_maps and self.get_cvar("sv_workshopFile"):
            engine_items = len(self._workshop_items or ())
            self.log_once(
                "assets-workshop", "warning",
                "slipgate: this server loads workshop maps (sv_workshopFile is set%s) but the "
                "installed-map scan found none - so Slipgate is never told they exist and can "
                "never ask for their levelshots. Set qlx_workshopPath to the directory holding "
                "the numbered workshop item folders.",
                f" and the engine lists {engine_items} item(s)" if engine_items else "")

    def report_forced_pass(self, summary):
        player = summary.get("player")
        if player is None:
            return
        sent, outcome = summary["sent"], summary["outcome"]
        soon = f"resuming in {max(1, int(summary['resume_sec']) // 60)} min"
        if outcome == "exhausted":
            tail = ("Slipgate has everything this server can offer." if not sent
                    else "that is everything this server can offer.")
        elif outcome == "throttled":
            tail = f"Slipgate asked for a pause, {soon}."
        elif outcome == "capped":
            tail = f"more to do, {soon}."
        else:
            tail = f"the pass stopped early, {soon}."
        self.tell(player, f"sent {sent} asset(s); {tail}")

    def ask_wanted(self, names):
        """Worker. What Slipgate lacks of these maps, or None."""
        try:
            response = self.request(
                "POST", "/ingest/assets/wanted", json={"maps": list(names)},
                headers={"X-Slipgate-Asset-Kinds": ",".join(sorted(ASSET_KINDS))})
        except requests.RequestException as exc:
            self.log_once("assets", "warning", "slipgate: asset discovery failed: %s", exc)
            return None
        if self.credential_refused(response.status_code, "asset discovery", scope="asset"):
            return None
        if response.status_code == 503:
            self.log_once("assets", "warning",
                          "slipgate: this Slipgate has map-asset contribution switched off, so "
                          "there is nothing to send. Enable it under /admin/settings.")
            return None
        if response.status_code != 200:
            self.log_once("assets", "warning", "slipgate: asset discovery returned HTTP %d",
                          response.status_code)
            return None
        self._logged.discard("assets")
        return self.json_body(response)

    def asset_outstanding(self, name, kind):
        return (name, kind) not in self._assets_offered and self.feature_allowed(f"asset_{kind}")

    def offer_asset(self, info, kind):
        """Worker. (sent, retry_after); the pair is retired only on a final answer."""
        pair = (info.name, kind)
        if not self.asset_outstanding(info.name, kind):
            return False, None
        spec = ASSET_KINDS.get(kind)
        if spec is None:
            self._assets_offered.add(pair)
            self.log_once(f"assets-kind:{kind}", "warning",
                          "slipgate: Slipgate wants a %r asset, which this plugin version "
                          "cannot supply. Update the plugin.", kind)
            return False, None
        is_bsp = kind == "bsp"
        is_arena = kind == "arena"
        is_preview = kind == "levelshot_preview"
        limit = self.declared_limit(
            "bsp_max_bytes" if is_bsp
            else "arena_max_bytes" if is_arena
            else "levelshot_preview_max_bytes" if is_preview
            else "levelshot_max_bytes",
            spec.max_bytes)
        body = self.asset_body(info, kind, spec, limit)
        if body is None:
            self._assets_offered.add(pair)
            return False, None
        data, source, content_type = body
        headers = self.headers()
        headers.update({"Content-Type": content_type,
                        "X-Slipgate-Map": header_safe(info.name)})
        if source is not None:
            headers["X-Slipgate-Source-Pk3"] = header_safe(os.path.basename(source.pk3_path))
            if source.workshop_id:
                headers["X-Slipgate-Workshop-Id"] = str(source.workshop_id)
        try:
            response = _session.post(f"{self.api_url}{spec.endpoint}", data=data, headers=headers,
                                     timeout=UPLOAD_TIMEOUT)
        except requests.RequestException as exc:
            self.log_once("assets-post", "warning", "slipgate: asset upload failed: %s", exc)
            return False, None
        code = response.status_code
        if self.credential_refused(code, "asset upload", scope="asset"):
            return False, None
        if code == 429:
            header = response.headers.get("Retry-After", "")
            wait = min(int(header), ASSET_THROTTLE_MAX) if header.isdigit() else CONTRIBUTE_INTERVAL
            self.log_once("assets-post", "warning",
                          "slipgate: %s %s deferred; Slipgate asked for %d s",
                          info.name, kind, wait)
            return False, max(1, wait)
        if code >= 500:
            self.log_once("assets-post", "warning",
                          "slipgate: %s %s deferred (HTTP %d); the next pass tries again",
                          info.name, kind, code)
            return False, None
        self._assets_offered.add(pair)
        if code != 200:
            why = (self.json_body(response) or {}).get("detail") or f"HTTP {code}"
            self.note_error(why, rejected=True)
            self.logger.warning("slipgate: %s %s refused - %s", info.name, kind, why)
            return False, None
        self._logged.discard("assets-post")
        body = self.json_body(response) or {}
        kept = body.get("status") in ("pending", "published")
        self.note_success(kept)
        return kept, None

    @staticmethod
    def members_for(info, kind):
        """Every (source, member) that might carry this asset, best source first."""
        spec = ASSET_KINDS.get(kind)
        if spec is None or spec.member is None:
            return []
        out = []
        for source in info.sources:
            if spec.flag and getattr(source, spec.flag, True) is False:
                continue
            out.append((source, spec.member.format(name=info.name)))
        return out

    def asset_body(self, info, kind, spec, limit):
        """(bytes, source, content type), or None."""
        if kind == "arena":
            return self.arena_body(info, limit)
        for source, pattern in self.members_for(info, kind):
            data = self.read_member(source.pk3_path, pattern, limit)
            if data is not None:
                return data, source, "application/octet-stream"
        return None

    def arena_body(self, info, limit):
        arena = getattr(info, "arena", None)
        if arena is None:
            return None
        blob = json.dumps(self.arena_payload(info, arena), separators=(",", ":")).encode("utf-8")
        if len(blob) > limit:
            self.logger.warning("slipgate: the arena claim for %s is %d bytes, over the %d cap",
                                info.name, len(blob), limit)
            return None
        return blob, self.arena_source(info, arena), "application/json"

    @staticmethod
    def arena_source(info, arena):
        raw = getattr(arena, "source", None) or ""
        for source in info.sources:
            if raw.startswith(source.pk3_path):
                return source
        return None

    @staticmethod
    def arena_payload(info, arena):
        tokens = [str(t)[:32] for t in (getattr(arena, "type_tokens", None) or ())][:16]
        codes = []
        for gametype in getattr(arena, "gametypes", None) or ():
            code = GAMETYPE_CODES.get(gametype)
            if code and code not in codes:
                codes.append(code)
        payload = {
            "map": info.name,
            "longname": (getattr(arena, "longname", None) or "")[:200] or None,
            "author": (getattr(arena, "author", None) or "")[:200] or None,
            "type_tokens": tokens,
            "gametypes": codes,
        }
        for field in ("fraglimit", "timelimit"):
            value = getattr(arena, field, None)
            if isinstance(value, int) and 0 <= value <= 1_000_000:
                payload[field] = value
        extra = {}
        modelled = {"map", "longname", "author", "type", "fraglimit", "timelimit"}
        for key, value in dict(getattr(arena, "raw", None) or {}).items():
            if len(extra) >= 16:
                break
            if key not in modelled:
                extra[str(key)[:32]] = str(value)[:128]
        payload["extra"] = extra
        return payload

    def read_member(self, pk3_path, pattern, limit):
        try:
            with zipfile.ZipFile(pk3_path) as archive:
                entry = self.find_member(archive, pattern)
                if entry is None:
                    return None
                if entry.file_size > limit:
                    self.logger.warning("slipgate: %s in %s is %d bytes, over the %d cap",
                                        entry.filename, os.path.basename(pk3_path),
                                        entry.file_size, limit)
                    return None
                with archive.open(entry) as handle:
                    data = handle.read(limit + 1)
                if len(data) > limit:
                    self.logger.warning("slipgate: %s in %s decompressed past its declared size",
                                        entry.filename, os.path.basename(pk3_path))
                    return None
                return data
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            self.log_once("assets-read", "warning", "slipgate: could not read %s: %s", pk3_path, exc)
            return None

    @staticmethod
    def find_member(archive, pattern):
        if not pattern.endswith(".*"):
            wanted = pattern.lower()
            return next((c for c in archive.infolist() if _member_key(c.filename) == wanted), None)
        stem = pattern[:-2].lower()
        for candidate in archive.infolist():
            head, _, extension = _member_key(candidate.filename).rpartition(".")
            if head == stem and extension in LEVELSHOT_EXTENSIONS:
                return candidate
        return None


    @minqlxtended.command("balance", permission=1, client_cmd_perm=1)
    def cmd_balance(self, player, msg, channel):
        return self.request_plan(player, channel, force=True)

    @minqlxtended.command(("teams", "teens"))
    def cmd_teams(self, player, msg, channel):
        return self.request_plan(player, channel)

    def no_plan(self, player, reason):
        if player is not None:
            player.tell(reason)
        else:
            self.logger.debug("slipgate: no automatic balance - %s", reason)
        return None

    def game_code(self):
        game = self.game
        return GAMETYPE_CODES.get(game.type_short) if game is not None else None

    def plan_preconditions(self, player=None):
        """(code, roster), or None once the caller has been told."""
        if not self.is_configured():
            return self.no_plan(player, f"{BRAND} is not configured on this server.")
        if self.game is None:
            return None
        code = self.game_code()
        if code not in TEAM_GAMETYPE_CODES:
            return self.no_plan(player, "Balance only applies to rated team game types.")
        if time.monotonic() < self._balance_cooldown_until:
            return self.no_plan(player, "Give that a moment.")
        teams = self.teams()
        roster = [{"steam_id": str(member.steam_id), "team": side, "client_id": member.id,
                   "connected_sec": self.connected_sec(member),
                   "score": getattr(member, "score", None)}
                  for side in ("red", "blue") for member in teams[side]]
        if len(roster) < MIN_BALANCE_PLAYERS:
            return self.no_plan(player, "Not enough players to balance.")
        cap = self.declared_limit("balance_max_players", MAX_BALANCE_PLAYERS)
        if len(roster) > cap:
            return self.no_plan(player, f"Too many players to balance (max {cap}).")
        return code, roster

    def auto_switch_below(self):
        floor = round(float(self._qlx_slipgateAutoSwitchBelow) * 1000)
        return self.declared_limit("auto_switch_below_permille", floor) / 1000.0

    def request_plan(self, player=None, channel=None, force=False, trigger="command"):
        checked = self.plan_preconditions(player)
        if checked is None:
            return None
        code, roster = checked
        self._balance_cooldown_until = time.monotonic() + self.declared_pace(
            "balance_cooldown_sec", BALANCE_COOLDOWN
        )
        self._plan_seq += 1
        request_context = {
            "match_state": self.match_state() or "live",
            "round_number": self._round_number if self.has_round_boundary() else None,
            "threshold": self.auto_switch_below() if trigger == "auto" else 0.0,
            "revision": self._lobby_revision,
        }
        self.run_in_thread(self.fetch_plan, roster, code, channel, self._map, force,
                           request_context=request_context, trigger=trigger, seq=self._plan_seq,
                           then=self.apply_plan)
        return None

    def fetch_plan(self, roster, code, channel, mapname, force, request_context=None,
                   *, trigger="command", seq=0):
        context = dict(request_context or {})
        threshold = context.get("threshold", 0.0)
        stamp = {"_channel": channel, "_map": mapname, "_forced": bool(force), "_roster": roster,
                 "_seq": seq, "_threshold": threshold, "_revision": context.get("revision"),
                 "_trigger": trigger}
        payload = {"supported_verbs": sorted(KNOWN_VERBS),
                   "game_type": code,
                   "players": roster,
                   "match_state": context.get("match_state", "live"),
                   "trigger": trigger,
                   "round_number": context.get("round_number"),
                   "force": bool(force),
                   "auto_switch_below": threshold}
        try:
            response = self.request("POST", "/balance/plan", json=payload)
        except requests.RequestException as exc:
            return {"_error": type(exc).__name__, **stamp}
        if response.status_code != 200:
            return {"_error": f"HTTP {response.status_code}", **stamp}
        body = self.json_body(response)
        return {**(body if body is not None else {"_error": "unreadable response"}), **stamp}

    def stale_plan(self, plan, channel, reason):
        if plan.get("_trigger") == "auto":
            self.arm_auto_balance(reason)
        elif channel:
            channel.reply(self.branded("the teams changed while that balance was calculated."))
        self.report_outcome(plan, timing="none", dropped="lobby_changed")

    def refuse_plan(self, plan, channel, dropped):
        self.report_outcome(plan, timing="none", dropped=dropped)
        if channel:
            channel.reply(self.branded("that balance could not be run here."))

    def apply_plan(self, plan):
        if not plan:
            return
        channel = plan.get("_channel")
        if plan.get("_seq") and plan["_seq"] != self._plan_seq:
            self.logger.info("slipgate: dropping balance plan %s, %s is the current one",
                             plan.get("_seq"), self._plan_seq)
            self.report_outcome(plan, timing="none", dropped="superseded")
            return
        if plan.get("_map") != self._map:
            self.logger.info("slipgate: dropping a balance plan for %s, the map is now %s",
                             plan.get("_map"), self._map)
            self.report_outcome(plan, timing="none", dropped="map_changed")
            return
        revision = plan.get("_revision")
        if revision is not None and revision != self._lobby_revision:
            self.logger.info("slipgate: dropping balance plan for lobby revision %s, now %s",
                             revision, self._lobby_revision)
            self.stale_plan(plan, channel, "the automatic plan became stale")
            return
        if plan.get("_error"):
            if channel:
                channel.reply(self.branded(f"balance unavailable ({plan['_error']})."))
            return

        instructions = plan.get("instructions") or []
        if not isinstance(instructions, list) or len(instructions) > MAX_INSTRUCTIONS:
            self.logger.warning("slipgate: refusing a balance plan of %d instructions",
                                len(instructions) if isinstance(instructions, list) else -1)
            self.refuse_plan(plan, channel, "too_many_steps")
            return
        if self.game is None:
            return
        steps = [step for step in instructions if isinstance(step, dict)]
        if any(step.get("verb") not in KNOWN_VERBS for step in steps):
            self.logger.warning("slipgate: refusing a plan with a verb this build cannot run")
            self.refuse_plan(plan, channel, "unknown_verb")
            return

        movers = [step for step in steps if step.get("verb") in ("put", "switch")]
        if self.roster_drift(plan.get("_roster")):
            self._suggestion = None
            self.drop_held_plan("lobby_changed")
            self.stale_plan(plan, channel, "the automatic plan's roster became stale")
            return

        stripped = False
        if (movers and self.match_state() in ("countdown", None)
                and not self.preserves_head_count(movers)):
            self.logger.warning("slipgate: refusing a plan that would resize a team mid-countdown")
            movers, stripped = [], True

        forced = bool(plan.get("_forced"))
        threshold = plan.get("_threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            threshold = 0.0
        quality_before = plan.get("quality_before")
        rated = isinstance(quality_before, (int, float)) and not isinstance(quality_before, bool)
        if movers and not forced:
            if not rated:
                self.logger.warning(
                    "slipgate: refusing %d move(s) in a plan that quoted no fairness, so nothing "
                    "here can tell a proposal from an instruction; proposing instead", len(movers))
                movers, stripped = [], True
            elif quality_before >= threshold:
                self.logger.warning(
                    "slipgate: refusing %d move(s) in a plan for teams that are already "
                    "%.0f%% fair, against a threshold of %.0f%%; proposing instead",
                    len(movers), quality_before * 100, threshold * 100)
                movers, stripped = [], True

        index = self.player_index()
        pair = None
        for step in steps:
            if step.get("verb") == "suggest":
                pair = self.apply_instruction(step, index, set()).pair or pair

        self.drop_held_plan("superseded")

        timing = "none"
        report = None
        if movers:
            if forced:
                self._suggestion = None
                report = self.run_steps(movers)
                timing = "now"
            elif self.defer_moves():
                self._held_plan = {
                    "steps": movers,
                    "map": self._map,
                    "seq": plan.get("_seq"),
                    "roster": plan.get("_roster") or self.balance_roster_snapshot(),
                    "revision": (plan.get("_revision") if plan.get("_revision") is not None
                                 else self._lobby_revision),
                    "trigger": plan.get("_trigger"),
                    "plan_id": plan.get("plan_id"),
                }
                timing = "next_round"
            else:
                report = self.run_steps(movers)
                timing = "now"

        applied = report.applied if report is not None else None
        planned = report.planned if report is not None else None
        self.narrate_plan(plan, steps, stripped=stripped, rated=rated, timing=timing, pair=pair,
                          applied=applied, planned=planned,
                          reached=report is not None and not report.stranded)
        if timing != "next_round":
            self.report_outcome(
                plan, applied=applied or 0, planned=planned,
                stranded=list(report.stranded) if report is not None else [],
                timing=timing, stripped=stripped,
            )

    def report_outcome(self, plan, *, applied=0, planned=None, stranded=(), timing="now",
                       stripped=False, drifted=False, dropped=None):
        plan_id = plan.get("plan_id") if isinstance(plan, dict) else None
        if not isinstance(plan_id, int) or isinstance(plan_id, bool):
            return
        body = {
            "plan_id": plan_id,
            "applied": int(applied or 0),
            "stranded": [str(item) for item in (stranded or ())][:64],
            "timing": str(timing),
            "stripped": bool(stripped),
            "drifted": bool(drifted),
        }
        if planned is not None:
            body["planned"] = int(planned)
        if dropped:
            body["dropped"] = str(dropped)[:32]
        self.run_in_thread(self.post_outcome, body)

    def post_outcome(self, body):
        try:
            response = self.request("POST", "/balance/outcome", json=body)
        except Exception as exc:
            self.log_once("balance-outcome", "warning",
                          "slipgate: could not report a balance outcome - %s", exc)
            return
        if response.status_code != 200:
            self.log_once("balance-outcome", "warning",
                          "slipgate: a balance outcome was refused (HTTP %s)", response.status_code)
            return
        self._logged.discard("balance-outcome")

    def narrate_plan(self, plan, steps, stripped, rated, timing, pair,
                     applied=None, planned=None, reached=True):
        try:
            line = self.balance_line(
                plan.get("outcome"),
                quality_before=plan.get("quality_before"),
                quality=plan.get("quality"),
                timing=timing,
                stripped=stripped,
                rated=rated,
                pair=pair,
                quality_after=self.suggested_quality(steps),
                applied=applied,
                planned=planned,
                reached=reached,
            )
        except Exception:
            self.logger.exception("slipgate: could not compose the balance line")
            return
        if line:
            self.announce(line)
        else:
            self.logger.warning("slipgate: no line for balance outcome %r", plan.get("outcome"))

    @staticmethod
    def suggested_quality(steps):
        for step in steps:
            if step.get("verb") == "suggest":
                value = step.get("quality_after")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return value
        return None


    @minqlxtended.hook("team_switch")
    def handle_team_switch(self, player, old_team, new_team):
        if self._our_moves.pop((player.id, str(new_team)), None) is not None:
            return
        if str(old_team) in ("red", "blue") or str(new_team) in ("red", "blue"):
            self.lobby_changed("somebody changed team")

    @minqlxtended.hook("vote_ended")
    def handle_vote_ended(self, votes, vote, args, passed):
        if not passed or str(vote).lower() != "shuffle":
            return
        self.arm_auto_balance("a shuffle vote passed", delay=VOTE_SETTLE)

    @minqlxtended.hook("game_countdown")
    def handle_game_countdown(self):
        self.arm_auto_balance("the match is about to start", delay=0.0)

    def reset_auto_balance(self):
        self._auto_due_at = 0.0
        self._auto_next_at = 0.0

    def arm_auto_balance(self, reason, delay=None):
        wait = AUTO_DEBOUNCE if delay is None else delay
        self._auto_due_at = max(self._auto_due_at, time.monotonic() + wait)
        self._auto_reason = reason

    def tick_auto_balance(self):
        now = time.monotonic()
        self._our_moves = {key: expiry for key, expiry in self._our_moves.items() if expiry > now}
        if not self._auto_due_at or now < self._auto_due_at or now < self._auto_next_at:
            return
        if not self.auto_balance_allowed():
            return
        self._auto_due_at = 0.0
        self._auto_next_at = now + AUTO_INTERVAL
        self.logger.info("slipgate: balancing on its own - %s", self._auto_reason)
        self.request_plan(trigger="auto")

    def auto_balance_allowed(self):
        return bool(
            self.is_configured() and self.upload_token
            and self._qlx_slipgateAutoBalance and self.feature_allowed("balance_auto")
            and not self.paused_reason("all") and not self.is_intermission()
        )

    def has_round_boundary(self):
        return self.game_code() in ROUND_BASED_CODES

    def match_state(self):
        """intermission | countdown | warmup | live, or None when unreadable."""
        try:
            if self.is_intermission():
                return "intermission"
            state = self.game.state
        except Exception:
            return None
        if state == minqlxtended.GameState.COUNTDOWN:
            return "countdown"
        if state == minqlxtended.GameState.WARMUP:
            return "warmup"
        return "live"

    def defer_moves(self):
        return self.match_state() == "live" and self.has_round_boundary()

    def run_steps(self, steps):
        if self.game is None:
            return RunReport(0, len(self.instruction_players(steps)), [])
        index = self.player_index()
        wanted = self.planned_sides(steps, index)
        self.mark_our_moves(wanted, index)
        moved = set()
        applied_players = set()
        for step in steps:
            if self.apply_instruction(step, index, moved).applied:
                first, _ = self.resolve_player(step, index)
                if first is not None:
                    applied_players.add(self.player_key(first))
                if step.get("verb") == "switch":
                    second, _ = self.resolve_player(step, index, other=True)
                    if second is not None:
                        applied_players.add(self.player_key(second))
        stranded = self.verify_split(wanted)
        return RunReport(len(applied_players - set(stranded)),
                         len(self.instruction_players(steps)), stranded)

    @staticmethod
    def player_key(player):
        return player.id, str(player.steam_id)

    def player_index(self):
        """By slot, and by Steam ID where unique."""
        players = list(self.players())
        shared = collections.Counter(str(p.steam_id) for p in players)
        return {"slots": {p.id: p for p in players},
                "steam": {str(p.steam_id): p for p in players if shared[str(p.steam_id)] == 1}}

    @staticmethod
    def expected_player(step, other=False):
        prefix = "other_" if other else ""
        client_id = step.get(f"{prefix}client_id")
        steam_id = str(step.get(f"{prefix}steam_id") or "")
        if isinstance(client_id, bool) or not isinstance(client_id, int):
            client_id = None
        return client_id, steam_id

    def resolve_player(self, step, index, other=False):
        """(player, refusal). A slot is verified against the Steam ID expected in it."""
        client_id, steam_id = self.expected_player(step, other)
        if client_id is not None:
            player = index["slots"].get(client_id)
            if player is None:
                return None, "that client slot is no longer connected"
            if steam_id and str(player.steam_id) != steam_id:
                return None, "that client slot now belongs to somebody else"
            return player, None
        if not steam_id:
            return None, "the instruction names no player"
        player = index["steam"].get(steam_id)
        if player is None:
            return None, "they are no longer connected or that Steam ID occupies multiple slots"
        return player, None

    def resolve_pair(self, step, index):
        first, first_refusal = self.resolve_player(step, index)
        second, second_refusal = self.resolve_player(step, index, other=True)
        return first, second, first_refusal or second_refusal

    def instruction_players(self, steps):
        players = set()
        for step in steps:
            verb = step.get("verb")
            if verb in ("put", "switch"):
                players.add(self.expected_player(step))
            if verb == "switch":
                players.add(self.expected_player(step, other=True))
        players.discard((None, ""))
        return players

    @staticmethod
    def indexed(index, identity):
        client_id, steam_id = identity
        member = index["slots"].get(client_id) if client_id is not None else None
        if member is None and steam_id:
            member = index["steam"].get(steam_id)
        return member

    def mark_our_moves(self, wanted, index):
        """Our own moves echo back through team_switch; mark them before they land."""
        deadline = time.monotonic() + OUR_MOVE_TTL
        for identity, side in wanted.items():
            member = self.indexed(index, identity)
            if member is not None:
                self._our_moves[(member.id, str(side))] = deadline

    def mark_shuffled_moves(self, before):
        deadline = time.monotonic() + OUR_MOVE_TTL
        teams = self.teams()
        for side in ("red", "blue"):
            for member in teams[side]:
                if before.get(member.id) != side:
                    self._our_moves[(member.id, side)] = deadline

    def planned_sides(self, steps, index):
        wanted = {}
        for step in steps:
            verb = step.get("verb")
            if verb == "put":
                identity = self.expected_player(step)
                team = step.get("team")
                if identity != (None, "") and team in PLACEABLE_TEAMS:
                    player, _ = self.resolve_player(step, index)
                    wanted[self.player_key(player) if player is not None else identity] = str(team)
            elif verb == "switch":
                first, second, _refusal = self.resolve_pair(step, index)
                if first is not None and second is not None and first.team != second.team:
                    wanted[self.player_key(first)] = str(second.team)
                    wanted[self.player_key(second)] = str(first.team)
        return wanted

    def preserves_head_count(self, steps):
        index = self.player_index()
        net = 0
        for identity, side in self.planned_sides(steps, index).items():
            member = self.indexed(index, identity)
            if member is None or str(member.team) == side:
                continue
            net += 1 if side == "red" else -1
        return net == 0

    def verify_split(self, wanted):
        if not wanted:
            return []
        teams = self.teams()
        where = {self.player_key(member): side
                 for side in ("red", "blue") for member in teams[side]}
        stranded = sorted((identity for identity, side in wanted.items() if where.get(identity) != side),
                          key=str)
        if stranded:
            self.logger.warning(
                "slipgate: %d of %d planned movers are not where the plan put them: %s",
                len(stranded), len(wanted), ", ".join(str(identity) for identity in stranded))
        return stranded

    def roster_drift(self, planned):
        if not planned:
            return []
        teams = self.teams()
        now = {(member.id, str(member.steam_id), side)
               for side in ("red", "blue") for member in teams[side]}
        then = {(entry.get("client_id"), str(entry.get("steam_id")), entry.get("team"))
                for entry in planned if entry.get("steam_id")}
        changed = sorted(now ^ then)
        if changed:
            self.logger.warning("slipgate: the lobby changed while a plan was in flight: %s",
                                ", ".join(str(item) for item in changed))
        return changed

    def balance_roster_snapshot(self):
        teams = self.teams()
        return [{"steam_id": str(member.steam_id), "client_id": member.id, "team": side}
                for side in ("red", "blue") for member in teams[side]]

    def held_plan_refusal(self, held):
        if held is None:
            return "there is nothing waiting."
        if held.get("trigger") != "command" and not (
            self._qlx_slipgateAutoBalance and self.feature_allowed("balance_auto")
        ):
            return "automatic balancing has been turned off since."
        if held.get("map") != self._map:
            return "the map changed."
        if held.get("seq") is not None and held["seq"] != self._plan_seq:
            return "a newer balance has been decided since."
        if held.get("revision") is not None and held["revision"] != self._lobby_revision:
            return "the playing lobby changed."
        if self.roster_drift(held.get("roster")):
            return "the playing lobby changed."
        if (self.match_state() in ("countdown", None)
                and not self.preserves_head_count(held.get("steps") or [])):
            return "it would resize a team during a countdown."
        return None

    def drop_held_plan(self, reason):
        held = self._held_plan
        self._held_plan = None
        if held is not None:
            self.report_outcome(held, timing="none", dropped=reason)

    def run_held_plan(self, reason="the round is starting"):
        held = self._held_plan
        self._held_plan = None
        if held is None:
            return
        refusal = self.held_plan_refusal(held)
        if refusal is not None:
            self.logger.info("slipgate: dropping the held balance - %s", refusal)
            if held.get("trigger") == "auto":
                self.arm_auto_balance("a held automatic balance became stale")
            self.report_outcome(held, timing="none", dropped="held_stale")
            return
        report = self.run_steps(held["steps"])
        self.report_outcome(held, applied=report.applied, planned=report.planned,
                            stranded=list(report.stranded), timing="now")
        if report.stranded:
            self.logger.warning("slipgate: the held balance left %d of %d move(s) unmade (%s)",
                                len(report.stranded), report.planned, reason)

    @minqlxtended.next_frame
    def run_held_plan_next_frame(self):
        self.run_held_plan()

    def apply_instruction(self, step, index, moved):
        verb = step.get("verb")
        if verb == "put":
            steam_id = str(step.get("steam_id") or "")
            team = step.get("team")
            target, refusal = self.resolve_player(step, index)
            if target is None:
                return self.step_dropped(verb, steam_id, refusal)
            identity = self.player_key(target)
            if identity in moved:
                return self.step_dropped(verb, steam_id, "already moved by an earlier step")
            if team not in PLACEABLE_TEAMS:
                return self.step_dropped(verb, steam_id, f"{team} is not a team a plan may name")
            if target.team != team:
                if not self.put_player(target, team):
                    return self.step_dropped(verb, steam_id, "the engine refused the move")
                moved.add(identity)
            return StepResult(True)
        if verb == "suggest":
            first, second, refusal = self.resolve_pair(step, index)
            if first is None or second is None or first.team == second.team:
                return self.step_dropped(verb, step.get("steam_id"),
                                         refusal or "the pair already share a team")
            self._suggestion = {
                "pair": (str(first.steam_id), str(second.steam_id)),
                "slots": ((self.player_key(first), self.player_key(second))
                          if self.expected_player(step)[0] is not None
                          and self.expected_player(step, other=True)[0] is not None
                          else None),
                "agreed": set(),
                "at": time.monotonic(),
                "deferred": False,
            }
            return StepResult(True, None, (first.clean_name, second.clean_name))
        if verb == "switch":
            first, second, refusal = self.resolve_pair(step, index)
            if first is None or second is None:
                return self.step_dropped(verb, step.get("steam_id"), refusal)
            if first.team == second.team:
                return self.step_dropped(verb, first.steam_id, "the pair are already on one team")
            first_key = self.player_key(first)
            second_key = self.player_key(second)
            if first_key in moved or second_key in moved:
                return self.step_dropped(verb, first.steam_id,
                                         "one of the pair was moved by an earlier step")
            if not self.switch_players(first, second):
                return self.step_dropped(verb, first.steam_id, "the engine refused the swap")
            moved.update({first_key, second_key})
            return StepResult(True)
        return self.step_dropped(verb, step.get("steam_id"), "a verb this build cannot run")

    def step_dropped(self, verb, who, reason):
        self.logger.warning("slipgate: dropped a %s for %s - %s", verb, who or "?", reason)
        return StepResult(False, reason)

    def _scoreboard(self, game, players):
        """(stats, score) per player during a live match, else None."""
        try:
            if game.state != minqlxtended.GameState.IN_PROGRESS:
                return None
            return tuple((player.stats, player.score) for player in players)
        except Exception:
            return None

    def switch_players(self, first, second):
        game = self.game
        if game is None:
            return False
        before = self._scoreboard(game, (first, second))
        try:
            game.switch(first, second)
        except ValueError as exc:
            self.logger.warning("slipgate: the engine refused a switch of %s and %s - %s",
                                first.steam_id, second.steam_id, exc)
            return False
        if before is not None:
            self.delay(1, self.restore_stats, (first, second), before)
        return True

    def put_player(self, player, team):
        game = self.game
        if game is None:
            return False
        before = self._scoreboard(game, (player,))
        try:
            player.put(team)
        except ValueError as exc:
            self.logger.warning("slipgate: the engine refused a put of %s to %s - %s",
                                player.steam_id, team, exc)
            return False
        if before is not None:
            self.delay(1, self.restore_stats, (player,), before)
        return True

    def restore_stats(self, players, before):
        for player, (stats, score) in zip(players, before, strict=False):
            try:
                if stats is not None:
                    player.stats = stats
                if score is not None:
                    player.score = score
            except Exception:
                self.logger.debug("slipgate: could not restore the scoreboard for %s", player)

    @staticmethod
    def pct(value):
        try:
            return f"{float(value):.0%}".replace("%", QL_PERCENT)
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def branded(text):
        return f"{BRAND}: {text}"

    def announce(self, text):
        self.msg(self.branded(text))

    def tell(self, player, text):
        player.tell(self.branded(text))

    @classmethod
    def balance_line(cls, outcome, quality_before=None, quality=None, timing="none",
                     stripped=False, rated=True, pair=None, quality_after=None,
                     applied=None, planned=None, reached=True):
        before, after = cls.pct(quality_before), cls.pct(quality)
        if stripped:
            if not rated:
                return "not moving anyone: this plan did not say how fair the teams are."
            return f"teams are {before} fair, so nobody is being moved."
        if outcome == "already_fair":
            return f"teams are already {before} fair."
        if outcome == "no_better_split":
            return f"teams are {before} fair, and no better split exists."
        if outcome == "budget_limited":
            return f"teams are {before} fair; no worthwhile low-disruption balance is available."
        if outcome == "close_enough":
            return f"teams are close enough at {before}; a balance would only reach {after}."
        if outcome == "propose":
            if pair:
                first, second = (str(n)[:NAME_IN_LINE] for n in pair)
                return (f"{before} fair. Swap ^6{first}^7 and ^6{second}^7 "
                        f"for {cls.pct(quality_after)}: both type ^6!a^7.")
            return f"teams are {before} fair; a balance would reach {after}."
        if outcome == "apply":
            if timing == "next_round":
                return f"evening the teams at the start of the next round - {before} to {after}."
            if timing == "now":
                if applied is not None and planned:
                    if not applied:
                        return f"could not move anyone; teams are still {before} fair."
                    if applied < planned:
                        return (f"moved {applied} of {planned}, so the teams are short of "
                                f"{after}. Type ^6!teams^7 to re-check.")
                    if not reached:
                        return (f"moved everyone named, but the teams are not the {after} "
                                f"planned. Type ^6!teams^7 to re-check.")
                return f"evened the teams - {before} to {after}."
            return f"teams are already {before} fair."
        if outcome == "cannot_apply":
            return f"a balance would reach {after}, but this build cannot apply it."
        return None

    @minqlxtended.command("prepare", permission=1, client_cmd_perm=1)
    def cmd_prepare(self, player, msg, channel):
        return self.prepare_teams(player, channel)

    def prepare_teams(self, player=None, channel=None, trigger="command"):
        """Shuffle, then balance what it landed on."""
        game = self.game
        if game is None:
            return None
        if self.plan_preconditions(player) is None:
            return None
        before = {member.id: side for side in ("red", "blue") for member in self.teams()[side]}
        game.shuffle()
        self.mark_shuffled_moves(before)
        return self.request_plan(player, channel, force=True, trigger=trigger)


    @minqlxtended.command(("agree", "a"), client_cmd_perm=0)
    def cmd_agree(self, player, msg, channel):
        pending = self.live_suggestion()
        if pending is None:
            self.tell(player, "nothing to agree to right now.")
            return None
        identities = pending.get("slots")
        identity = self.player_key(player) if identities else str(player.steam_id)
        if identity not in (identities or pending["pair"]):
            self.tell(player, "that suggestion does not involve you.")
            return None
        pending["agreed"].add(identity)
        if len(pending["agreed"]) < len(identities or pending["pair"]):
            self.msg(f"^6{player.clean_name}^7 agrees. Waiting on the other player.")
            return None
        if self.defer_moves():
            pending["deferred"] = True
            self.announce("agreed: the swap happens at the start of the next round.")
            return None
        self.execute_suggestion("both players agreed")
        return None

    def force_pending(self, reason, stale):
        """Run the held plan (still revalidated) and the suggestion."""
        if self._held_plan is not None:
            refusal = self.held_plan_refusal(self._held_plan)
            if refusal is not None:
                self.drop_held_plan("held_stale")
                stale(refusal)
            else:
                self.run_held_plan(reason="forced")
        if self.live_suggestion() is not None:
            self.execute_suggestion(reason)

    @minqlxtended.command("do", permission=1)
    def cmd_do(self, player, msg, channel):
        if self.live_suggestion() is None and self._held_plan is None:
            self.tell(player, "nothing suggested right now.")
            return None
        self.force_pending(
            "forced", lambda refusal: self.tell(player, f"that balance is out of date - {refusal} Ask again."))
        return None

    @minqlxtended.command(("dl", "do_later"), permission=1, client_cmd_perm=1)
    def cmd_do_later(self, player, msg, channel):
        pending = self.live_suggestion()
        if pending is None:
            self.tell(player, "nothing suggested right now.")
            return None
        if not self.has_round_boundary():
            self.tell(player, "this game type has no rounds to wait for. "
                        "Use ^6!do^7 to switch them now.")
            return None
        pending["deferred"] = True
        self.announce("the swap will happen at the start of the next round.")
        return None

    def live_suggestion(self):
        """The pending suggestion if still good, else None. The clock stops once deferred."""
        pending = self._suggestion
        if pending is None:
            return None
        if pending.get("deferred"):
            return pending
        ttl = self.declared_limit("suggestion_ttl_sec", SUGGESTION_TTL)
        if time.monotonic() - pending["at"] > ttl:
            self._suggestion = None
            return None
        return pending

    def execute_suggestion(self, reason):
        pending = self.live_suggestion()
        self._suggestion = None
        if pending is None or self.game is None:
            return
        index = self.player_index()
        slots = pending.get("slots")
        if slots:
            first = index["slots"].get(slots[0][0])
            second = index["slots"].get(slots[1][0])
            if first is not None and self.player_key(first) != tuple(slots[0]):
                first = None
            if second is not None and self.player_key(second) != tuple(slots[1]):
                second = None
        else:
            first = index["steam"].get(pending["pair"][0])
            second = index["steam"].get(pending["pair"][1])
        if first is None or second is None:
            self.announce("too late, one of them has left.")
            return
        if first.team == second.team:
            self.announce("too late, they are on the same team now.")
            return
        if not self.switch_players(first, second):
            return
        self.announce(f"switched ^6{first.clean_name}^7 with ^6{second.clean_name}^7 ({reason}).")

    @minqlxtended.next_frame
    def execute_suggestion_next_frame(self, reason):
        self.execute_suggestion(reason)

    @minqlxtended.hook("round_countdown")
    def handle_round_countdown(self, round_number):
        if isinstance(round_number, int):
            self._round_number = round_number
        pending = self.live_suggestion()
        if pending is not None and pending.get("deferred"):
            self.execute_suggestion_next_frame("agreed earlier")
        if self._held_plan is not None:
            self.run_held_plan_next_frame()


    def vote_balance(self, caller, args):
        if self.plan_preconditions(caller) is None:
            return None
        return minqlxtended.CustomVote("balance the teams", self.execute_balance_vote)

    def execute_balance_vote(self):
        self.request_plan(channel=minqlxtended.CHAT_CHANNEL, force=True, trigger="vote")

    def vote_do(self, caller, args):
        args = (args or "").strip().lower()
        if not args:
            self.tell(caller, "use one of the following:")
            self.tell(caller, "  ^6/cv do now^7 forces the switch when the vote passes.")
            self.tell(caller, "  ^6/cv do later^7 forces the switch at the start of the next round.")
            return None
        if self.live_suggestion() is None and self._held_plan is None:
            self.tell(caller, "nothing suggested right now.")
            return None
        if args == "now":
            return minqlxtended.CustomVote("force the suggested switch now", self.execute_do_vote)
        if args == "later":
            if not self.has_round_boundary():
                self.tell(caller, "this game type has no rounds to wait for. "
                          "Vote ^6/cv do now^7 to switch them when the vote passes.")
                return None
            if self.live_suggestion() is None:
                self.tell(caller, "that balance is already waiting for the next round.")
                return None
            return minqlxtended.CustomVote("force the suggested switch at the start of the next round",
                                           self.execute_do_later_vote)
        self.tell(caller, "either ^6now^7 or ^6later^7, nothing else.")
        return None

    def execute_do_vote(self):
        self.force_pending("the vote passed",
                           lambda refusal: self.announce(f"that balance is out of date - {refusal}"))

    def execute_do_later_vote(self):
        pending = self.live_suggestion()
        if pending is None:
            self.announce("too late, that suggestion has expired.")
            return
        pending["deferred"] = True
        self.announce("the swap will happen at the start of the next round.")

    def vote_go(self, caller, args):
        if self.match_state() != "warmup":
            self.tell(caller, "voting to go is not possible during an active game.")
            return None
        return minqlxtended.CustomVote("balance the teams and begin the game", self.execute_go_vote)

    def execute_go_vote(self):
        self.execute_balance_vote()
        game = self.game
        if game is not None and self.match_state() == "warmup":
            game.allready()

    def vote_prepare(self, caller, args):
        if self.match_state() != "warmup":
            self.tell(caller, "voting to prepare is not possible during an active game.")
            return None
        if self.plan_preconditions(caller) is None:
            return None
        return minqlxtended.CustomVote("shuffle the teams, then balance them", self.execute_prepare_vote)

    def execute_prepare_vote(self):
        if self.match_state() != "warmup":
            self.announce("the game has already started, so the teams were left as they are.")
            return
        self.prepare_teams(channel=minqlxtended.CHAT_CHANNEL, trigger="vote")


    @minqlxtended.command(("rating", "elo", "getrating", "getelo"), usage="[player] [gametype]")
    def cmd_rating(self, player, msg, channel):
        if not self.is_configured():
            player.tell(f"{BRAND} is not configured on this server.")
            return None
        target = self.resolve_target(player, msg)
        if target is None:
            return minqlxtended.Return.USAGE
        if len(msg) > 2:
            code = msg[2].lower()
            if code not in RATED_GAMETYPES:
                player.tell(f"Not a rated game type. Try: {', '.join(sorted(RATED_GAMETYPES))}")
                return None
        else:
            code = self.game_code()
        if code is None:
            player.tell("This game type is not rated. Name one to look it up anyway.")
            return None
        self.run_in_thread(self.fetch_rating, *target, code, channel, then=self.reply)
        return None

    def fetch_rating(self, steam_id, name, code, channel):
        try:
            response = self.request("GET", f"/players/{steam_id}/ratings/{code}")
        except requests.RequestException as exc:
            return channel, self.branded(f"lookup failed ({type(exc).__name__}).")
        if response.status_code == 404:
            return channel, f"^7{name} has no {code} rating yet."
        body = self.json_body(response) if response.status_code == 200 else None
        if body is None:
            return channel, self.branded(f"lookup failed (HTTP {response.status_code}).")
        tier = body.get("tier_name")
        if body.get("provisional"):
            band = f" ^3({tier}, provisional)^7" if tier else " ^3(provisional)^7"
        else:
            band = f" ^6({tier})^7" if tier else ""
        return channel, (f"^7{name}: ^6{body.get('display')}^7{band} in {code.upper()} over "
                         f"{body.get('games')} games")

    @minqlxtended.command("achievements", usage="[player]")
    def cmd_achievements(self, player, msg, channel):
        if not self.is_configured():
            player.tell(f"{BRAND} is not configured on this server.")
            return None
        target = self.resolve_target(player, msg)
        if target is None:
            return minqlxtended.Return.USAGE
        self.run_in_thread(self.fetch_achievements, *target, channel, then=self.reply)
        return None

    def fetch_achievements(self, steam_id, name, channel):
        try:
            response = self.request("GET", f"/players/{steam_id}/achievements")
        except requests.RequestException as exc:
            return channel, self.branded(f"lookup failed ({type(exc).__name__}).")
        body = self.json_body(response) if response.status_code == 200 else None
        if body is None:
            return channel, self.branded(f"lookup failed (HTTP {response.status_code}).")
        earned = body.get("achievements") or []
        if not earned:
            return channel, f"^7{name} has no achievements yet."
        names = ", ".join(str(a.get("name")) for a in earned[:8])
        return channel, f"^7{name}: {len(earned)} achievements - {names}"

    @minqlxtended.command(("ratings", "elos", "selo", "egos"))
    def cmd_ratings(self, player, msg, channel):
        return self.request_roster_ratings(player, channel, "rating")

    @minqlxtended.command("tiers")
    def cmd_tiers(self, player, msg, channel):
        return self.request_roster_ratings(player, channel, "tier")

    def request_roster_ratings(self, player, channel, mode):
        if not self.is_configured():
            player.tell(f"{BRAND} is not configured on this server.")
            return None
        code = self.game_code()
        if code is None:
            player.tell("This game type is not rated.")
            return None
        roster = self.roster_snapshot()
        if not roster:
            player.tell("Nobody here to rate.")
            return None
        self.run_in_thread(self.fetch_ratings, roster, code, channel, mode, then=self.show_ratings)
        return None

    def roster_snapshot(self):
        """[(steam_id, team, clean_name)] for everyone connected. Game thread."""
        teams = self.teams()
        out = [(str(member.steam_id), side, member.clean_name)
               for side in ("free", "red", "blue", "spectator") for member in teams.get(side) or ()]
        return out[:MAX_LOOKUP_PLAYERS]

    def fetch_ratings(self, roster, code, channel, mode):
        payload = {"steam_ids": [sid for sid, _side, _name in roster], "game_type": code}
        try:
            response = self.request("POST", "/ratings/bulk", json=payload)
        except requests.RequestException as exc:
            return channel, code, roster, None, f"lookup failed ({type(exc).__name__})", mode
        if response.status_code != 200:
            return channel, code, roster, None, f"lookup failed (HTTP {response.status_code})", mode
        body = self.json_body(response)
        if body is None:
            return channel, code, roster, None, "lookup returned nothing usable", mode
        found = {str(entry["steam_id"]): entry for entry in body.get("players") or ()
                 if isinstance(entry, dict) and entry.get("steam_id")}
        return channel, code, roster, found, None, mode

    def show_ratings(self, result):
        """One line per populated team, the colour on the value."""
        if not result:
            return
        channel, code, roster, found, error, mode = result
        if channel is None:
            return
        if error:
            channel.reply(self.branded(f"{error}."))
            return
        current = {sid for sid, _side, _name in self.roster_snapshot()}
        joined = len(current - {sid for sid, _side, _name in roster})
        lines = []
        for side in ("free", "red", "blue", "spectator"):
            members = [(sid, name) for sid, member_side, name in roster
                       if member_side == side and sid in current]
            if not members:
                continue
            colour = TEAM_COLOURS.get(side, "")
            entries = sorted(
                (self.rating_entry(found.get(sid), name, colour, mode) for sid, name in members),
                key=lambda entry: (entry[0] is not None, entry[0] or 0), reverse=True,
            )
            lines.append(", ".join(text for _value, text in entries))
        if not lines:
            lines.append(self.branded(f"nobody left to rate in {code.upper()}."))
        elif joined:
            lines.append(f"^7({joined} joined while looking up - run it again for them.)")
        self.reply_lines(channel, lines)

    @staticmethod
    def rating_entry(entry, name, colour, mode):
        if not entry or not entry.get("found"):
            return None, f"{name}: ^3unrated^7"
        display = entry.get("display")
        value = entry.get("tier_name") if mode == "tier" else display
        if value is None:
            return None, f"{name}: ^3unrated^7"
        suffix = " ^3(prov)^7" if entry.get("provisional") else ""
        rendered = f"{colour}{value}^7" if colour else f"{value}"
        return display, f"{name}: {rendered}{suffix}"

    def resolve_target(self, player, msg):
        """(steam_id, name) of who a command is about, resolved on the game thread, or None."""
        if len(msg) < 2:
            return str(player.steam_id), player.clean_name
        argument = str(msg[1]).strip()
        if argument.isdigit():
            identifier = self.resolve_identifier(argument, target=player)
            if identifier is None:
                return None
            if identifier.player is not None:
                return str(identifier.player.steam_id), identifier.player.clean_name
            return str(identifier.steam_id), str(identifier.name or identifier.steam_id)
        found = self.find_player(argument)
        if not found:
            player.tell(f"No player matching ^6{argument}^7.")
            return None
        return str(found[0].steam_id), found[0].clean_name

    def reply(self, result):
        if not result:
            return
        channel, text = result
        if channel and text:
            channel.reply(text)


    @minqlxtended.command("slipgate", permission=1, usage="status|ping|refresh|upload|assets|update")
    def cmd_slipgate(self, player, msg, channel):
        action = msg[1].lower() if len(msg) > 1 else "status"
        if action == "status":
            self.tell_status(player)
        elif action == "upload":
            blocker = self.upload_blocker()
            if blocker:
                self.tell(player, f"demo upload is off - {blocker}.")
                return None
            self.sweep_spool(force=True)
            self.tell(player, "sweeping the demo spool.")
        elif action == "assets":
            blocker = self.contribute_blocker()
            if blocker:
                self.tell(player, f"asset contribution is off - {blocker}.")
                return None
            if self.contribute_assets(force=True, player=player):
                self.tell(player, "checking which map assets are wanted.")
            else:
                self.tell(player, "a contribution pass is already running.")
        elif action == "refresh":
            self.refresh_capabilities()
            self.tell(player, "re-reading the server's policy.")
        elif action == "update":
            if self.human_players():
                self.tell(player, "^3reloading with players connected - nobody will be recorded "
                                  "until the next map.^7")
            if not self.maybe_update(forced=True, player=player):
                offered = self._update_offered
                if offered and offered in self._update_failed:
                    self.tell(player, f"plugin {offered} was refused "
                                      f"({self._update_failed[offered]}).")
                elif offered and offered != PLUGIN_VERSION:
                    self.tell(player, f"cannot update - {self.update_blocker()}.")
                else:
                    self.tell(player, f"already on the offered build ({PLUGIN_VERSION}).")
        elif action == "ping":
            self.run_in_thread(self.ping, channel, then=self.reply)
        else:
            return minqlxtended.Return.USAGE
        return None

    def maps_line(self):
        state = self._asset_state
        if not state:
            return "^3not scanned yet^7 - try ^6!slipgate assets^7"
        engine = len(self._workshop_items or ())
        if state["maps"] and not state["workshop_maps"]:
            trailer = "^1none from workshop items^7"
            if engine:
                trailer += f" (the engine lists {engine})"
        else:
            trailer = f"{state['workshop_maps']} from workshop items"
        return (f"{state['maps']} installed, {trailer}, {state['pk3s']} pk3"
                f"{self.at_clock_monotonic(state['at'])}")

    def update_line(self):
        offered = self._update_offered
        if offered and offered in self._update_failed:
            return f"^1refused {offered}^7 ({self._update_failed[offered]}) - running {PLUGIN_VERSION}"
        blocker = self.update_blocker()
        if offered and offered != PLUGIN_VERSION:
            trailer = f"^3{blocker}^7" if blocker else "installing when the server empties"
            return f"^6{offered}^7 offered, running {PLUGIN_VERSION} - {trailer}"
        if blocker:
            return f"off - {blocker}"
        return f"on - {PLUGIN_VERSION} is current"

    def at_clock_monotonic(self, when):
        if not when:
            return ""
        minutes = int((time.monotonic() - when) // 60)
        return f" - {minutes} min ago" if minutes else " - just now"

    def tell_status(self, player):
        health = self._health
        upload_blocker = self.upload_blocker()
        asset_blocker = self.contribute_blocker()
        self.reply_lines(player, [
            f"{BRAND} plugin {PLUGIN_VERSION}",
            f"  endpoint     {self.api_url or '^1unset^7'}",
            f"  upload token {'set' if self.upload_token else '^1unset^7'}",
            f"  uploads      {'on' if not upload_blocker else f'off ^1({upload_blocker})^7'}",
            f"  pending      {len(self._pending)} demo(s)",
            f"  match stamp  {self._stamp_state or 'no match started yet'}",
            f"  assets       {'on' if not asset_blocker else f'off ^1({asset_blocker})^7'} - "
            f"{len(self._assets_offered)} settled this session",
            f"  maps         {self.maps_line()}",
            f"  update       {self.update_line()}",
            f"  totals       {health['uploaded']} uploaded, {health['duplicate']} duplicate, "
            f"{health['rejected']} rejected"
            f"{self.at_clock(health['last_ok_at'], ', last ok ')}",
            *self.policy_lines(),
        ])
        if health["last_error"]:
            player.tell(f"  last error   {health['last_error']}"
                        f"{self.at_clock(health['last_error_at'], ' at ')}")

    @staticmethod
    def at_clock(stamp, prefix):
        if not stamp:
            return ""
        return prefix + time.strftime("%H:%M", time.localtime(stamp))

    def policy_lines(self):
        if self._caps_at is None:
            return ["  policy       ^3not fetched yet^7 - try ^6!slipgate refresh^7"]
        age = int(time.monotonic() - self._caps_at)
        out = [f"  policy       read {self.describe_age(age)}"]
        for label, name, fallback, accessor in (
            ("sweep", "sweep_interval_sec", SWEEP_DEFAULT, self.declared_pace),
            ("balance cooldown", "balance_cooldown_sec", BALANCE_COOLDOWN, self.declared_pace),
            ("suggestion", "suggestion_ttl_sec", SUGGESTION_TTL, self.declared_limit),
            ("demo cap", "demo_max_bytes", DEMO_MAX_BYTES, self.declared_limit),
        ):
            effective = accessor(name, fallback)
            declared = self._caps.get("limits", {}).get(name)
            clamped = " ^3(clamped)^7" if isinstance(declared, int) and declared != effective else ""
            shown = f"{effective // 1048576} MB" if name.endswith("_bytes") else f"{effective}s"
            out.append(f"               {label} {shown}{clamped}")
        return out

    @staticmethod
    def describe_age(seconds):
        if seconds < 90:
            return "just now"
        if seconds < 5400:
            return f"{seconds // 60} min ago"
        return f"{seconds // 3600} h ago"

    def ping(self, channel):
        started = time.monotonic()
        caps = self.fetch_capabilities()
        elapsed = (time.monotonic() - started) * 1000
        if caps is None:
            return channel, self.branded("no answer.")
        self.store_capabilities(caps)
        features = ", ".join(name for name, on in (caps.get("features") or {}).items() if on)
        return channel, self.branded(f"{elapsed:.0f} ms - {features or 'no features'}")
