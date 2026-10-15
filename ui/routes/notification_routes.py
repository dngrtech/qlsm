import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from ui import db
from ui.models import Notification

notification_api_bp = Blueprint('notification_api_routes', __name__)

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _unread_query():
    return Notification.query.filter(Notification.read_at.is_(None))


@notification_api_bp.route('', methods=['GET'])
@jwt_required()
def list_notifications():
    """Newest first. ?unread=1 limits the list to unread rows; unread_count is
    always the total, so the bell can poll with limit=1."""
    try:
        limit = int(request.args.get('limit', DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    query = _unread_query() if request.args.get('unread') in ('1', 'true') else Notification.query
    rows = (query.order_by(Notification.updated_at.desc(), Notification.id.desc())
            .limit(limit).all())
    return jsonify({'data': {
        'notifications': [row.to_dict() for row in rows],
        'unread_count': _unread_query().count(),
    }}), 200


@notification_api_bp.route('/<int:notification_id>/read', methods=['POST'])
@jwt_required()
def mark_read(notification_id):
    row = db.session.get(Notification, notification_id)
    if row is None:
        return jsonify({'error': {'message': 'Notification not found.'}}), 404
    if row.read_at is None:
        row.read_at = datetime.datetime.utcnow()
        db.session.commit()
    return jsonify({'data': row.to_dict()}), 200


@notification_api_bp.route('/read-all', methods=['POST'])
@jwt_required()
def mark_all_read():
    updated = _unread_query().update(
        {'read_at': datetime.datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    return jsonify({'data': {'updated': updated}}), 200
