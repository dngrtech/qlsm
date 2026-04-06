import json
import logging
import re

import requests

from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required
from ui import limiter

logger = logging.getLogger(__name__)

server_status_bp = Blueprint('server_status', __name__)

STATUS_KEY_PATTERN = 'server:status:*'
WORKSHOP_PREVIEW_CACHE_KEY_PREFIX = 'steam:workshop:preview'
WORKSHOP_PREVIEW_CACHE_TTL = 86400  # 24 hours
WORKSHOP_PREVIEW_NEGATIVE_TTL = 1800  # 30 minutes
WORKSHOP_PREVIEW_NONE_SENTINEL = '__none__'
STEAM_PUBLISHED_FILE_DETAILS_URL = (
    'https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/'
)
WORKSHOP_PREVIEW_RATE_LIMIT = '30 per minute'


def _read_workshop_preview_cache(redis_client, cache_key):
    """Return (found, preview_url_or_none) for workshop preview cache."""
    if redis_client is None:
        return False, None

    try:
        raw = redis_client.get(cache_key)
        if raw is None:
            return False, None
        if raw == WORKSHOP_PREVIEW_NONE_SENTINEL:
            return True, None
        return True, raw
    except Exception as e:
        logger.warning(f"Error reading workshop preview cache key {cache_key}: {e}")
        return False, None


def _write_workshop_preview_cache(redis_client, cache_key, preview_url):
    """Write workshop preview cache. Caches misses with shorter TTL."""
    if redis_client is None:
        return

    try:
        if preview_url:
            redis_client.setex(cache_key, WORKSHOP_PREVIEW_CACHE_TTL, preview_url)
        else:
            redis_client.setex(
                cache_key,
                WORKSHOP_PREVIEW_NEGATIVE_TTL,
                WORKSHOP_PREVIEW_NONE_SENTINEL,
            )
    except Exception as e:
        logger.warning(f"Error writing workshop preview cache key {cache_key}: {e}")


def _fetch_preview_url_from_steam(workshop_id):
    """Fetch preview_url for a workshop item. Returns None on any failure."""
    try:
        response = requests.post(
            STEAM_PUBLISHED_FILE_DETAILS_URL,
            data={
                'itemcount': '1',
                'publishedfileids[0]': str(workshop_id),
            },
            timeout=(5, 5),
        )
        response.raise_for_status()

        payload = response.json() or {}
        details = payload.get('response', {}).get('publishedfiledetails', [])
        if not details:
            return None

        preview_url = details[0].get('preview_url')
        if not isinstance(preview_url, str):
            return None
        preview_url = preview_url.strip()
        return preview_url or None
    except Exception as e:
        logger.warning(f"Error fetching workshop preview for {workshop_id}: {e}")
        return None


@server_status_bp.route('', methods=['GET'])
@jwt_required()
def get_server_status():
    """
    Returns live status for all instances from the management Redis cache.

    Response: {"data": {"<instance_id>": <status_data_or_null>}}
    Keys are instance IDs as strings. Null means data unavailable/stale.
    """
    redis_client = current_app.extensions.get('redis')
    if redis_client is None:
        return jsonify({"data": {}})

    try:
        keys = redis_client.keys(STATUS_KEY_PATTERN)
        result = {}
        for key in keys:
            # Key format: server:status:<host_id>:<instance_id>
            instance_id = key.split(':')[-1]
            raw = redis_client.get(key)
            result[instance_id] = json.loads(raw) if raw else None
        return jsonify({"data": result})
    except Exception as e:
        logger.error(f"Error reading server status from Redis: {e}", exc_info=True)
        return jsonify({"data": {}})


@server_status_bp.route('/workshop-preview/<workshop_id>', methods=['GET'])
@limiter.limit(WORKSHOP_PREVIEW_RATE_LIMIT)
@jwt_required()
def get_workshop_preview(workshop_id):
    """Return preview URL for a workshop item with Redis-backed caching."""
    workshop_id = str(workshop_id).strip()
    if not re.fullmatch(r'\d+', workshop_id):
        return jsonify({"error": {"message": "workshop_id must be numeric"}}), 400

    redis_client = current_app.extensions.get('redis')
    cache_key = f'{WORKSHOP_PREVIEW_CACHE_KEY_PREFIX}:{workshop_id}'

    found, preview_url = _read_workshop_preview_cache(redis_client, cache_key)
    if found:
        return jsonify({
            "data": {
                "workshop_id": workshop_id,
                "preview_url": preview_url,
                "source": "cache",
            }
        })

    preview_url = _fetch_preview_url_from_steam(workshop_id)
    _write_workshop_preview_cache(redis_client, cache_key, preview_url)
    return jsonify({
        "data": {
            "workshop_id": workshop_id,
            "preview_url": preview_url,
            "source": "steam",
        }
    })
