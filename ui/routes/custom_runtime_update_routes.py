"""Preview and reserve a same-provider Custom release change."""
import json
import re
import uuid

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ui import db, task_lock
from ui.custom_runtime_update import preview
from ui.models import Host, HostStatus
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.routes.host_runtime_upgrade_routes import BUSY, ENQUEUE_FAILED, LOCK_TTL, _error, _json_body
from ui.task_logic.common import append_log
from ui.task_logic.host_runtime_upgrade_recovery import start_upgrade_job

custom_runtime_update_bp = Blueprint('custom_runtime_update', __name__)
_DIGEST = re.compile(r'[a-f0-9]{64}')


@custom_runtime_update_bp.route('/<int:host_id>/custom-runtime-update', methods=['GET', 'POST'])
@jwt_required()
def custom_runtime_update(host_id):
    host = db.session.get(Host, host_id)
    if host is None:
        return _error('Host not found.', 404)
    if request.method == 'GET':
        data, _ = preview(host)
        return jsonify(data=data)
    body = _json_body()
    if (not isinstance(body, dict) or set(body) != {'action', 'fingerprint', 'target_sha256'}
            or body['action'] not in ('update', 'rollback')
            or any(not isinstance(body[key], str) or not _DIGEST.fullmatch(body[key])
                   for key in ('fingerprint', 'target_sha256'))):
        return _error('Provide an update or rollback action, fingerprint, and target_sha256.', 400)
    if host.runtime != 'custom' or not host.runtime_provider_id:
        return _error('The host must use a pinned Custom runtime.', 409)
    from ui.addons.runtime_protection import (
        RuntimeProviderConflict, ensure_runtime_provider_present, provider_lifecycle_lock,
    )

    provider = host.runtime_provider_id
    try:
        with provider_lifecycle_lock(provider):
            ensure_runtime_provider_present(provider)
            operation_id, error = _reserve(host_id, provider, body)
    except RuntimeProviderConflict as exc:
        return jsonify(error=exc.to_error()), 409
    except (OSError, RedisError):
        return _error('Could not lock the host and provider for maintenance. Try again shortly.', 409)
    except SQLAlchemyError:
        db.session.rollback()
        return _error('Could not record the Custom release operation.', 500)
    if error:
        return error
    try:
        start_upgrade_job(operation_id)
    except Exception:
        current_app.logger.error('Custom runtime operation %s could not be queued', operation_id)
        return _error(ENQUEUE_FAILED, 500)
    return jsonify(data={'operation_id': operation_id, 'status': 'configuring'}), 202


def _reserve(host_id, provider, body):
    token = uuid.uuid4().hex
    if not task_lock.acquire_lock('host', host_id, token, LOCK_TTL):
        return None, _error(BUSY, 409)
    try:
        db.session.expire_all()
        host = db.session.get(Host, host_id)
        if host is None:
            return None, _error('Host not found.', 404)
        ids = sorted(i.id for i in host.instances)
        if not task_lock.acquire_locks('instance', ids, token, LOCK_TTL):
            return None, _error(BUSY, 409)
        try:
            db.session.expire_all()
            data, inputs = preview(host)
            if not inputs:
                return None, _error(data['eligibility']['reason'], 409)
            choice = inputs['choices'][body['action']]
            if (host.runtime_provider_id != provider or sorted(i.id for i in host.instances) != ids
                    or data['fingerprint'] != body['fingerprint'] or not choice
                    or choice['sha256'] != body['target_sha256']):
                return None, _error('The release or host changed. Review the available releases again.', 409)
            op = HostRuntimeUpgradeOperation(
                host_id=host_id, state='preparing', original_runtime='custom', original_host_status='active',
                fingerprint=data['fingerprint'], inputs_json=json.dumps(inputs),
                answers_json=json.dumps({'action': body['action'], 'target_sha256': choice['sha256']}),
                original_instance_states_json=json.dumps({i.id: i.status.value for i in host.instances}))
            db.session.add(op)
            host.status = HostStatus.CONFIGURING
            append_log(host, f"Custom release {body['action']} to {choice['sha256'][:12]} queued.")
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return None, _error(BUSY, 409)
            return op.id, None
        finally:
            task_lock.release_locks('instance', ids, token)
    finally:
        task_lock.release_lock('host', host_id, token)
