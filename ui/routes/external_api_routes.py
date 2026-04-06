from flask import Blueprint, jsonify
from ui import limiter
from ui.database import get_instances
from ui.routes.settings_routes import require_api_key

external_api_bp = Blueprint('external_api', __name__)

_EXCLUDED_FIELDS = {'zmq_rcon_port', 'zmq_rcon_password', 'zmq_stats_port', 'zmq_stats_password', 'logs', 'config'}


@external_api_bp.route('/instances', methods=['GET'])
@limiter.limit("200 per minute")
def external_list_instances():
    """List all QLDS instances for external services.

    Secured via Bearer token (API key), not JWT cookies.
    Excludes ZMQ RCON fields for security.
    """
    ok, err_response = require_api_key()
    if not ok:
        return err_response
    instances = get_instances()
    data = []
    for inst in instances:
        d = inst.to_dict()
        for field in _EXCLUDED_FIELDS:
            d.pop(field, None)
        data.append(d)
    return jsonify({'data': data})
