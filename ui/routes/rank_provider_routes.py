"""Per-instance rank provider configuration, and the read-only ratings feed.

A separate blueprint rather than an addition to instance_routes.py (1418 lines,
over the 500-line hard limit), following instance_admin_routes.py.
"""
import json

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from ui import db
from ui.models import QLInstance, RankProviderConfig
from ui.rank_providers.registry import PROVIDER_TYPES
from ui.rank_providers.service import RankService

rank_provider_api_bp = Blueprint('rank_provider_api_routes', __name__)

MAX_LENGTHS = {'base_url': 255, 'api_key': 255, 'game_type': 16, 'provider_type': 32}

# `extra` lands in an unbounded Text column, so bound the SERIALIZED blob.
MAX_EXTRA_SERIALIZED = 2048

# qlstats interpolates extra['rating_system'] straight into a request path.
# The UI only ever offers these two.
QLSTATS_RATING_SYSTEMS = {'elo', 'elo_b'}


def _error(message, status=400):
    return jsonify({"error": {"message": message}}), status


def _service():
    return RankService(current_app.extensions.get('redis'))


def _require_instance(instance_id):
    return db.session.get(QLInstance, instance_id)


def _validate(payload):
    """Repo validation order: type -> normalize -> empty -> length -> pattern.

    Returns (cleaned, error_message).
    """
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."

    # 1. Type check
    for field in ('provider_type', 'base_url', 'api_key', 'game_type'):
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            return None, f"'{field}' must be a string."
    if 'enabled' in payload and not isinstance(payload['enabled'], bool):
        return None, "'enabled' must be a boolean."
    extra = payload.get('extra', {})
    if extra is None:
        extra = {}
    if not isinstance(extra, dict):
        return None, "'extra' must be an object."
    # Every value a string. Without this, json.dumps writes arbitrary nested
    # data into an unbounded Text column, and a non-string rating_system
    # reaches an outbound URL path segment as whatever repr it happens to have.
    for key, value in extra.items():
        if not isinstance(value, str):
            return None, f"'extra.{key}' must be a string."

    # 2. Normalize
    cleaned = {
        'provider_type': (payload.get('provider_type') or '').strip(),
        # Trailing slashes off: adapters concatenate paths onto this, so a
        # trailing slash yields a double slash and a 404 with no useful error.
        'base_url': (payload.get('base_url') or '').strip().rstrip('/'),
        'api_key': (payload.get('api_key') or '').strip() or None,
        'game_type': (payload.get('game_type') or '').strip() or None,
        'extra': extra,
        'enabled': payload.get('enabled', True),
    }

    # 3. Empty check — game_type is deliberately optional: blank means
    #    "derive it from the live gametype", the normal case. elo-service is
    #    the exception: its pools map to no gametype, so blank never rates.
    if not cleaned['provider_type']:
        return None, "'provider_type' is required."
    if not cleaned['base_url']:
        return None, "'base_url' is required."
    if cleaned['provider_type'] == 'elo_service' and not cleaned['game_type']:
        return None, "'game_type' is required for elo-service (e.g. 'ffa_auto')."

    # 4. Length check
    for field, limit in MAX_LENGTHS.items():
        value = cleaned.get(field)
        if value and len(value) > limit:
            return None, f"'{field}' must be {limit} characters or fewer."
    # extra is bounded by its serialized length — the column is Text, and
    # nothing else stops an operator posting arbitrary data into it.
    if len(json.dumps(cleaned['extra'])) > MAX_EXTRA_SERIALIZED:
        return None, (f"'extra' must serialize to {MAX_EXTRA_SERIALIZED} "
                      "characters or fewer.")

    # 5. Pattern check
    if cleaned['provider_type'] not in PROVIDER_TYPES:
        return None, (f"Unknown provider type '{cleaned['provider_type']}'. "
                      f"Expected one of: {', '.join(sorted(PROVIDER_TYPES))}.")
    if not cleaned['base_url'].startswith(('http://', 'https://')):
        return None, "'base_url' must start with http:// or https://."
    # The one operator-controlled value that reaches an outbound URL path
    # segment. Scoped to qlstats on purpose: this is three rules, not a
    # per-provider schema framework for a column with one key in it.
    if cleaned['provider_type'] == 'qlstats':
        system = cleaned['extra'].get('rating_system')
        if system is not None and system not in QLSTATS_RATING_SYSTEMS:
            return None, ("'extra.rating_system' must be one of: "
                          f"{', '.join(sorted(QLSTATS_RATING_SYSTEMS))}.")

    # 6. Uniqueness — none needed, instance_id is unique.
    return cleaned, None


@rank_provider_api_bp.route('/<int:instance_id>/rank-provider', methods=['GET'])
@jwt_required()
def get_rank_provider(instance_id):
    if _require_instance(instance_id) is None:
        return _error(f"Instance {instance_id} not found.", 404)
    config = RankProviderConfig.query.filter_by(instance_id=instance_id).first()
    # api_key is returned in clear text, not masked. This repo masks no secrets
    # anywhere (QLInstance.to_dict() returns both ZMQ passwords in the clear),
    # and a masked GET feeding the whole-object PUT below would overwrite the
    # real token the first time the operator toggles `enabled`.
    return jsonify({"data": config.to_dict() if config else None}), 200


@rank_provider_api_bp.route('/<int:instance_id>/rank-provider', methods=['PUT'])
@jwt_required()
def put_rank_provider(instance_id):
    if _require_instance(instance_id) is None:
        return _error(f"Instance {instance_id} not found.", 404)

    cleaned, error = _validate(request.get_json(silent=True))
    if error:
        return _error(error)

    config = RankProviderConfig.query.filter_by(instance_id=instance_id).first()
    if config is None:
        config = RankProviderConfig(instance_id=instance_id)
        db.session.add(config)

    config.provider_type = cleaned['provider_type']
    config.base_url = cleaned['base_url']
    config.api_key = cleaned['api_key']
    config.game_type = cleaned['game_type']
    config.extra = json.dumps(cleaned['extra'])
    config.enabled = cleaned['enabled']
    db.session.commit()

    # Before returning: without this, disabling a provider visibly does
    # nothing for a full TTL.
    _service().invalidate(instance_id)
    return jsonify({"data": config.to_dict(), "message": "Rank provider saved."}), 200


@rank_provider_api_bp.route('/<int:instance_id>/rank-provider', methods=['DELETE'])
@jwt_required()
def delete_rank_provider(instance_id):
    if _require_instance(instance_id) is None:
        return _error(f"Instance {instance_id} not found.", 404)
    RankProviderConfig.query.filter_by(instance_id=instance_id).delete()
    db.session.commit()
    _service().invalidate(instance_id)
    return jsonify({"data": None, "message": "Rank provider removed."}), 200


@rank_provider_api_bp.route('/<int:instance_id>/ranks', methods=['GET'])
@jwt_required()
def get_ranks(instance_id):
    """Always 200 ONCE THE INSTANCE EXISTS. Errors never propagate to Live
    Status as a failure state — they just mean no rank shown that cycle.

    An unknown instance is a 404, like the three sibling routes above. It is a
    different kind of answer from "no ratings this cycle", and making /ranks
    the one route in this blueprint that invents a 200 for a missing row would
    be the larger inconsistency. The client side of that contract is pinned
    too: useRankData treats a 404 as configured:false and stops polling, so an
    instance deleted while its drawer is open does not keep firing a request
    every 30s.
    """
    if _require_instance(instance_id) is None:
        return _error(f"Instance {instance_id} not found.", 404)
    data, configured = _service().get_ratings(
        instance_id, request.args.get('steam_ids', ''))
    return jsonify({"data": data, "configured": configured}), 200
