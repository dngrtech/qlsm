"""Binary metadata API routes for .so plugin file descriptions."""

import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ui import db
from ui.models import BinaryMetadata
from ui.routes.draft_routes import _draft_exists, _validate_draft_id

binary_meta_bp = Blueprint('binary_meta', __name__)

DESCRIPTION_MAX_LEN = 100
_DESCRIPTION_RE = re.compile(r'^[^<>{}"]*$')
_VALID_CONTEXT_TYPES = frozenset({'preset', 'instance'})


def _safe_context_key(key):
    """Return True if key contains no path separators or parent-dir refs."""
    return bool(key) and '/' not in key and '\\' not in key and '..' not in key


@binary_meta_bp.route('/<draft_id>/binary-meta', methods=['GET'])
@jwt_required()
def get_binary_meta(draft_id):
    """Fetch a description for a .so file in a preset or instance context."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    path = (request.args.get('path') or '').strip()
    context_type = (request.args.get('context_type') or '').strip()
    context_key = (request.args.get('context_key') or '').strip()

    if not path or not context_type or not context_key:
        return jsonify({
            "error": {
                "message": "path, context_type, and context_key are required",
            },
        }), 400
    if not path.lower().endswith('.so'):
        return jsonify({
            "error": {"message": "Only .so files support descriptions"},
        }), 400
    if context_type not in _VALID_CONTEXT_TYPES:
        return jsonify({
            "error": {"message": "context_type must be 'preset' or 'instance'"},
        }), 400
    if not _safe_context_key(context_key):
        return jsonify({"error": {"message": "Invalid context_key"}}), 400

    row = BinaryMetadata.query.filter_by(
        context_type=context_type,
        context_key=context_key,
        file_path=path,
    ).first()

    return jsonify({"data": {"description": row.description if row else ""}}), 200


@binary_meta_bp.route('/<draft_id>/binary-meta', methods=['PATCH'])
@jwt_required()
def save_binary_meta(draft_id):
    """Create or update a description for a .so file."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body required"}}), 400

    path = data.get('path')
    description = data.get('description')
    context_type = data.get('context_type')
    context_key = data.get('context_key')

    if not all(isinstance(v, str) for v in (
        path, description, context_type, context_key,
    )):
        return jsonify({
            "error": {
                "message": (
                    "path, description, context_type, and context_key "
                    "must be strings"
                ),
            },
        }), 400

    path = path.strip()
    description = description.strip()
    context_type = context_type.strip()
    context_key = context_key.strip()

    if not path:
        return jsonify({"error": {"message": "path is required"}}), 400
    if not context_type:
        return jsonify({"error": {"message": "context_type is required"}}), 400
    if not context_key:
        return jsonify({"error": {"message": "context_key is required"}}), 400
    if len(description) > DESCRIPTION_MAX_LEN:
        return jsonify({
            "error": {
                "message": (
                    f"Description must be {DESCRIPTION_MAX_LEN} "
                    "characters or fewer"
                ),
            },
        }), 400
    if not _DESCRIPTION_RE.match(description):
        return jsonify({
            "error": {
                "message": 'Description contains invalid characters (<, >, {, }, ")',
            },
        }), 400
    if context_type not in _VALID_CONTEXT_TYPES:
        return jsonify({
            "error": {"message": "context_type must be 'preset' or 'instance'"},
        }), 400
    if not _safe_context_key(context_key):
        return jsonify({"error": {"message": "Invalid context_key"}}), 400
    if not path.lower().endswith('.so'):
        return jsonify({
            "error": {"message": "Only .so files support descriptions"},
        }), 400

    row = BinaryMetadata.query.filter_by(
        context_type=context_type,
        context_key=context_key,
        file_path=path,
    ).first()

    if row:
        row.description = description
    else:
        row = BinaryMetadata(
            context_type=context_type,
            context_key=context_key,
            file_path=path,
            description=description,
        )
        db.session.add(row)

    db.session.commit()
    return jsonify({"data": {"description": description}}), 200
