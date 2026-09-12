"""Read the admin list for one instance: QLSM's stored rows plus the live
minqlx levels off the running server."""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from ui import db
from ui.models import QLInstance
from ui.task_logic.permission_read import read_live_permissions

instance_admin_api_bp = Blueprint('instance_admin_api_routes', __name__)


@instance_admin_api_bp.route('/<int:instance_id>/admins', methods=['GET'])
@jwt_required()
def get_instance_admins(instance_id):
    instance = db.session.get(QLInstance, instance_id)
    if instance is None:
        return jsonify({"error": {"message": f"Instance {instance_id} not found."}}), 404

    live, managed, live_error = read_live_permissions(instance)
    return jsonify({"data": {
        "stored": [admin.to_dict() for admin in instance.admins],
        "live": live,
        # The managed-admins set is what the tab needs to tell an in-game
        # !setperm grant apart from a level QLSM pushed and then lost the row for
        # (which the next save would reset to 0).
        "managed": managed,
        "live_error": live_error,
    }}), 200
