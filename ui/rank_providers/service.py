"""Loads a rank config, resolves the game type, caches, and calls an adapter.

Caching is per-instance, not per-viewer: several people watching the same
instance's Live Status share one entry and the fetch cost is bounded regardless
of poller count. Redis rather than an in-process cache because Gunicorn runs
multiple worker processes.
"""
import hashlib
import json
import logging

from ui import db
from ui.admin_permissions import STEAMID64_RE
from ui.models import RankProviderConfig
from ui.rank_providers.registry import build_provider

logger = logging.getLogger(__name__)

CACHE_PREFIX = 'rank:ratings'
SUCCESS_TTL = 60   # the hook polls at 30s, so poll >= TTL/2 keeps hits common
NEGATIVE_TTL = 15  # a transient outage self-heals fast without hammering
MAX_STEAM_IDS = 64

STATUS_KEY_PREFIX = 'server:status'  # ui/task_logic/server_status_poll.py:17


def validate_steam_ids(raw):
    """Applied before any cache or provider call.

    These ids end up interpolated into an outbound, credential-carrying
    provider URL (a path segment for qlstats, a query value for elo-service).

    1. split, strip
    2. drop anything that is not a steam64 — reusing the repo's existing
       STEAMID64_RE (r'^7656119\\d{10}$'). Do NOT substitute a looser
       r'^\\d{17}$'. Non-matching ids are dropped silently rather than 400'd:
       a stale roster should not fail the request.
    3. de-duplicate
    4. cap at MAX_STEAM_IDS — without it one authenticated request becomes an
       unbounded outbound fan-out at 3s per call
    """
    if isinstance(raw, str):
        parts = raw.split(',')
    else:
        parts = list(raw or [])
    seen = []
    for part in parts:
        candidate = str(part).strip()
        if not STEAMID64_RE.match(candidate):
            continue
        if candidate not in seen:
            seen.append(candidate)
        if len(seen) >= MAX_STEAM_IDS:
            break
    return seen


def _fingerprint(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]


class RankService:
    def __init__(self, redis_client):
        # May be None: ui/__init__.py:113-119 creates the shared client inside a
        # try/except that only logs a warning.
        self.redis = redis_client

    # -- config ------------------------------------------------------------

    def _load_config(self, instance_id):
        return RankProviderConfig.query.filter_by(instance_id=instance_id).first()

    @staticmethod
    def _is_usable(config):
        """A row that predates a validation change, or arrived via a restore,
        is treated as 'no provider' rather than trusted."""
        return bool(
            config
            and config.enabled
            and config.provider_type
            and config.base_url
        )

    # -- game type ---------------------------------------------------------

    def _live_gametype(self, instance):
        """The gametype from the same Redis blob live status reads.

        Server-side on purpose: it feeds the cache fingerprint and must not be
        client-controlled. Missing blob -> None -> no lookup, empty column. That
        case is moot in practice: the blob is how Live Status gets its players
        at all, so if it is gone there is nobody to rank.

        WIRE FORMAT — verified, do not re-derive. The value is a bare lowercase
        short code such as 'ca' under BOTH runtimes. Live blobs read off this
        machine's Redis:

            server:status:8:20   gametype='ca'  map='campgrounds'
            server:status:13:28  gametype='ca'  map='almostlost'

        The two serverchecker copies write it differently — minqlx writes
        `game.type_short` directly (serverchecker.py:253) and minqlxtended
        wraps it in `str()` (serverchecker.py:311) — but they agree on the
        result, because minqlxtended.Gametype is declared
        `class Gametype(enum.StrEnum)` (minqlxtended/_enums.py:344), and
        StrEnum.__str__ is str.__str__. `str(Gametype.CA)` is 'ca', never
        'Gametype.CA'. So NO normalization step is needed here, and none should
        be added: a branch that strips a 'Gametype.' prefix would be dead code
        and a fixture built on 'Gametype.CA' would assert a value the system
        never produces. The .strip().lower() below is ordinary hygiene, not
        enum handling.
        """
        if self.redis is None or instance is None:
            return None
        try:
            raw = self.redis.get(f'{STATUS_KEY_PREFIX}:{instance.host_id}:{instance.id}')
        except Exception:
            return None
        if not raw:
            return None
        try:
            status = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(status, dict):
            return None
        gametype = status.get('gametype')
        return str(gametype).strip().lower() if gametype else None

    def _resolve_game_type(self, config, provider, instance):
        """1. an explicit override wins, verbatim
        2. otherwise the adapter maps the live gametype
        3. None from either means no request at all
        """
        if config.game_type and config.game_type.strip():
            return config.game_type.strip()
        live = self._live_gametype(instance)
        if not live:
            return None
        return provider.map_game_type(live)

    # -- cache -------------------------------------------------------------

    def _cache_key(self, instance_id, config, game_type, steam_ids):
        """rank:ratings:{instance_id}:{config_fp}:{roster_fp}

        api_key is deliberately NOT hashed in — no credential material in the
        Redis keyspace. Key rotation is covered by write invalidation.
        """
        config_fp = _fingerprint(
            f'{config.provider_type}|{config.base_url}|{game_type}|'
            f'{json.dumps(config.extra_dict(), sort_keys=True)}|{config.enabled}'
        )
        roster_fp = _fingerprint(','.join(sorted(steam_ids)))
        return f'{CACHE_PREFIX}:{instance_id}:{config_fp}:{roster_fp}'

    def _read_cache(self, key):
        if self.redis is None:
            return None
        try:
            raw = self.redis.get(key)
        except Exception:
            return None
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _write_cache(self, key, data):
        if self.redis is None:
            return
        ttl = SUCCESS_TTL if data else NEGATIVE_TTL
        try:
            self.redis.setex(key, ttl, json.dumps(data))
        except Exception:
            logger.warning('rank cache write failed for %s', key)

    def invalidate(self, instance_id):
        """Called by PUT and DELETE before returning. Without it, disabling a
        provider visibly does nothing for a full TTL."""
        if self.redis is None:
            return
        try:
            for key in self.redis.scan_iter(match=f'{CACHE_PREFIX}:{instance_id}:*'):
                self.redis.delete(key)
        except Exception:
            logger.warning('rank cache invalidation failed for instance %s', instance_id)

    # -- fetch -------------------------------------------------------------

    def _fetch_from_provider(self, provider, steam_ids, game_type, instance_id):
        return provider.fetch_ratings(steam_ids, game_type, instance_id=instance_id)

    def get_ratings(self, instance_id, raw_steam_ids):
        """Returns (data, configured).

        Never raises. Any failure is an empty data dict — errors do not reach
        the Live Status UI as a failure state, they just mean no rank that cycle.
        """
        from ui.models import QLInstance

        config = self._load_config(instance_id)
        if not self._is_usable(config):
            return {}, False

        steam_ids = validate_steam_ids(raw_steam_ids)
        if not steam_ids:
            return {}, True

        provider = build_provider(
            config.provider_type, config.base_url, config.api_key, config.extra_dict(),
        )
        if provider is None:
            return {}, False

        instance = db.session.get(QLInstance, instance_id)
        game_type = self._resolve_game_type(config, provider, instance)
        if not game_type:
            # The mode genuinely has no ratings here. Not an error.
            return {}, True

        key = self._cache_key(instance_id, config, game_type, steam_ids)
        cached = self._read_cache(key)
        if cached is not None:
            return cached, True

        try:
            data = self._fetch_from_provider(provider, steam_ids, game_type, instance_id)
        except Exception:
            # Adapters catch their own errors; this is the last line of defence.
            logger.warning('rank fetch failed for instance %s', instance_id)
            data = {}

        self._write_cache(key, data)
        return data, True
