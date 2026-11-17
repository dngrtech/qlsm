"""One-click minqlx -> minqlxtended host upgrade: the compatibility dry-run the
dialog shows, and the confirmation that reserves the host and queues the job.

The confirmation runs its checks, the capture and the reservation insert under
the host and instance Redis locks, then releases them BEFORE enqueueing: the
worker takes them again under its own fencing token, and the committed
reservation row keeps every other mutation (and a backup restore) out in
between. The capture holds ZMQ passwords and is never returned or logged.
"""
import json
import uuid

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from ui import db
from ui.models import Host, HostStatus
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.runtime_upgrade import (
    capture_upgrade_inputs,
    classification_fingerprint,
    upgrade_dry_run,
    upgrade_eligibility,
)
from ui.plugin_upload_validation import MAX_TOTAL_BYTES, UploadRejected, validate_plugin_upload
from ui.runtime_upgrade_conversion import AnswersInvalid, parse_answers, parse_uploads
from ui.runtime_upgrade_guard import active_runtime_upgrade, blocked_message, upgrade_block_response
from ui.task_lock import MAINTENANCE_LOCK_KEY, acquire_lock, acquire_locks, release_lock, release_locks
from ui.task_logic.common import append_log
from ui.task_logic.host_runtime_upgrade_recovery import start_upgrade_job
from ui.tasks import RUNTIME_UPGRADE_TIMEOUT

host_runtime_upgrade_bp = Blueprint('host_runtime_upgrade_routes', __name__)

LOCK_TTL = RUNTIME_UPGRADE_TIMEOUT + 300

NOT_ELIGIBLE = 'This host cannot be upgraded to minqlxtended.'
STALE = ('The host or its instances changed since the compatibility check was shown; '
         'review the upgrade again.')
INSTANCES_CHANGED = 'The host\'s instances changed while the upgrade was starting; review it again.'
BUSY = ('The host or one of its instances is busy with another operation; '
        'try again when it finishes.')
BACKUP_RUNNING = 'Cannot start the upgrade while a backup export or import is running. Try again shortly.'
ENQUEUE_FAILED = ('The runtime upgrade could not be queued. If it did not start, it is cancelled '
                  'automatically within a few minutes and the host returns to ACTIVE.')


def _error(message, status):
    return jsonify({'error': {'message': message}}), status


def _json_body():
    """The parsed JSON body, or None when it is absent, malformed or too deeply
    nested to parse."""
    try:
        return request.get_json(silent=True)
    except RecursionError:
        return None


def _encodable(value):
    """True for a str that survives UTF-8 (no lone surrogates)."""
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


class _Rejected(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.response = _error(message, status)


def _ineligible_response(eligibility):
    if eligibility['enabled']:
        return None
    return _error(eligibility['reason'] or NOT_ELIGIBLE, 409)


def _backup_maintenance_active():
    try:
        return bool(current_app.extensions['redis'].exists(MAINTENANCE_LOCK_KEY))
    except Exception:
        return False


def _instance_key(key, field):
    if not isinstance(key, str) or not (key.isdigit() and key.isascii()):
        raise _Rejected(f'{field} has an invalid instance id {key!r}.', 400)
    return int(key)


def _parse_uploads_body(body):
    """{instance_id: {path: text}} from uploaded_files + uploaded_file_ids.
    Shape, sizes and file-id wiring only; the text and the paths are validated
    against the capture under the locks."""
    files = body.get('uploaded_files', {})
    assignments = body.get('uploaded_file_ids', {})
    if not isinstance(files, dict):
        raise _Rejected('uploaded_files must be an object keyed by file id.', 400)
    if not isinstance(assignments, dict):
        raise _Rejected('uploaded_file_ids must be an object keyed by instance id.', 400)
    total = 0
    for file_id, entry in files.items():
        if (not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
                or not isinstance(entry.get('text'), str)):
            raise _Rejected('Each uploaded file must be an object with a path and a text.', 400)
        if not _encodable(file_id) or not _encodable(entry['path']) or not _encodable(entry['text']):
            raise _Rejected('Uploaded files must be valid UTF-8 text.', 400)
        total += len(entry['text'].encode('utf-8'))
    if total > MAX_TOTAL_BYTES:
        raise _Rejected(f'Uploaded files are larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MiB in total.', 400)
    uploads = {}
    for key, by_path in assignments.items():
        instance_id = _instance_key(key, 'uploaded_file_ids')
        if instance_id in uploads:
            raise _Rejected(f'uploaded_file_ids names instance {instance_id} twice.', 400)
        if not isinstance(by_path, dict):
            raise _Rejected(f'uploaded_file_ids for instance {instance_id} must be an object of paths.', 400)
        uploads[instance_id] = {}
        for path, file_id in by_path.items():
            if not isinstance(file_id, str) or file_id not in files:
                raise _Rejected(f'uploaded_file_ids for instance {instance_id} refers to an unknown file.', 400)
            if not _encodable(path):
                raise _Rejected('Uploaded file paths must be valid UTF-8 text.', 400)
            if files[file_id]['path'] != path:
                raise _Rejected(f'Uploaded file for {path} was assigned under a different path.', 400)
            uploads[instance_id][path] = files[file_id]['text']
    return uploads


def _parse_body(body):
    """(fingerprint, {instance_id: [paths]}, {instance_id: {path: text}}) or
    raise _Rejected(400). Type and shape only; membership and offers are
    checked against the capture."""
    if not isinstance(body, dict):
        raise _Rejected('Request body must be a JSON object.', 400)
    fingerprint = body.get('fingerprint')
    if not isinstance(fingerprint, str) or not fingerprint or not _encodable(fingerprint):
        raise _Rejected('fingerprint must be a non-empty string.', 400)
    raw = body.get('accepted_replacements', {})
    if not isinstance(raw, dict):
        raise _Rejected('accepted_replacements must be an object keyed by instance id.', 400)
    answers = {}
    for key, paths in raw.items():
        instance_id = _instance_key(key, 'accepted_replacements')
        if instance_id in answers:
            raise _Rejected(f'accepted_replacements names instance {instance_id} twice.', 400)
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            raise _Rejected(f'accepted_replacements for instance {instance_id} must be a list of paths.', 400)
        if not all(_encodable(path) for path in paths):
            raise _Rejected('accepted_replacements paths must be valid UTF-8 text.', 400)
        if len(set(paths)) != len(paths):
            raise _Rejected(f'accepted_replacements for instance {instance_id} lists a path twice.', 400)
        answers[instance_id] = paths
    return fingerprint, answers, _parse_uploads_body(body)


@host_runtime_upgrade_bp.route('/<int:host_id>/runtime-upgrade/validate-plugin', methods=['POST'])
@jwt_required()
def validate_plugin(host_id):
    """Check one file the operator picked for the dialog. Writes nothing."""
    host = db.session.get(Host, host_id)
    if host is None:
        return _error('Host not found.', 404)
    body = _json_body()
    if not isinstance(body, dict):
        return _error('Request body must be a JSON object.', 400)
    path, text = body.get('path'), body.get('text')
    if not isinstance(path, str) or not isinstance(text, str):
        return _error('path and text must be strings.', 400)
    try:
        validate_plugin_upload(path, text)
    except UploadRejected as exc:
        return jsonify({'error': {'message': exc.message, 'reasons': exc.reasons}}), 400
    return jsonify({'data': {'path': path, 'verdict': 'unknown'}})


@host_runtime_upgrade_bp.route('/<int:host_id>/runtime-upgrade', methods=['GET'])
@jwt_required()
def runtime_upgrade_dry_run(host_id):
    """The compatibility dialog: eligibility, per-instance verdicts and the
    fingerprint the client echoes back on confirm."""
    host = db.session.get(Host, host_id)
    if host is None:
        return _error('Host not found.', 404)
    blocked = upgrade_block_response(host.id, host.name)
    if blocked:
        return blocked
    eligibility = upgrade_eligibility(host)
    ineligible = _ineligible_response(eligibility)
    if ineligible:
        return ineligible
    rows, inputs = upgrade_dry_run(host)
    return jsonify({'data': {
        'eligibility': eligibility,
        'instances': rows,
        'fingerprint': classification_fingerprint(inputs),
    }})


def _reserve(host_id, fingerprint, answers, uploads, instance_ids):
    """The critical section, run under the locks: re-check, capture, validate,
    and commit the reservation with the host in CONFIGURING. Returns the
    operation id or raises _Rejected."""
    db.session.expire_all()  # everything read before the locks may be stale
    host = db.session.get(Host, host_id)
    if host is None:
        raise _Rejected('Host not found.', 404)
    if active_runtime_upgrade(host.id) is not None:
        raise _Rejected(blocked_message(host.name), 409)
    eligibility = upgrade_eligibility(host)
    if not eligibility['enabled']:
        raise _Rejected(eligibility['reason'] or NOT_ELIGIBLE, 409)
    if sorted(inst.id for inst in host.instances) != instance_ids:
        raise _Rejected(INSTANCES_CHANGED, 409)

    inputs = capture_upgrade_inputs(host)
    if classification_fingerprint(inputs) != fingerprint:
        raise _Rejected(STALE, 409)
    raw_answers = {str(instance_id): paths for instance_id, paths in answers.items()}
    try:
        ticked = parse_answers(inputs, json.dumps(raw_answers))
    except AnswersInvalid as exc:
        raise _Rejected(str(exc), 400) from None
    raw_uploads = {str(instance_id): files for instance_id, files in uploads.items()}
    try:
        cleaned_uploads = parse_uploads(inputs, json.dumps(raw_uploads))
    except AnswersInvalid as exc:
        raise _Rejected(str(exc), 400) from None

    op = HostRuntimeUpgradeOperation(
        host_id=host.id,
        state='preparing',
        inputs_json=json.dumps(inputs),
        fingerprint=fingerprint,
        answers_json=json.dumps({str(instance_id): paths for instance_id, paths in ticked.items()}),
        uploads_json=json.dumps({str(instance_id): files for instance_id, files in cleaned_uploads.items()}),
        original_runtime=host.runtime,
        original_host_status=HostStatus.ACTIVE.value,
    )
    db.session.add(op)
    host.status = HostStatus.CONFIGURING
    append_log(host, 'Upgrade to minqlxtended queued.')
    try:
        db.session.commit()
    except IntegrityError:
        # Another request inserted this host's nonterminal operation first.
        db.session.rollback()
        raise _Rejected(f'Host {host.name} is already being upgraded to minqlxtended.', 409) from None
    return op.id


@host_runtime_upgrade_bp.route('/<int:host_id>/runtime-upgrade', methods=['POST'])
@jwt_required()
def start_runtime_upgrade(host_id):
    """Confirm the dialog: reserve the host and queue upgrade_host_runtime."""
    host = db.session.get(Host, host_id)
    if host is None:
        return _error('Host not found.', 404)
    try:
        fingerprint, answers, uploads = _parse_body(_json_body())
    except _Rejected as rejected:
        return rejected.response
    blocked = upgrade_block_response(host.id, host.name)
    if blocked:
        return blocked

    instance_ids = sorted(inst.id for inst in host.instances)
    # Reject fake instance ids before any lock or per-instance work: each id
    # would otherwise multiply the uploaded text under the locks.
    if set(uploads) - set(instance_ids):
        return _error('uploaded_file_ids names an instance that is not on this host.', 400)
    token = str(uuid.uuid4())
    host_locked = False
    instances_locked = False
    try:
        host_locked = acquire_lock('host', host.id, token, LOCK_TTL)
        if host_locked:
            instances_locked = acquire_locks('instance', instance_ids, token, LOCK_TTL)
        if not instances_locked:
            return _error(BACKUP_RUNNING if _backup_maintenance_active() else BUSY, 409)
        operation_id = _reserve(host.id, fingerprint, answers, uploads, instance_ids)
    except _Rejected as rejected:
        db.session.rollback()
        return rejected.response
    finally:
        if instances_locked:
            release_locks('instance', instance_ids, token)
        if host_locked:
            release_lock('host', host.id, token)

    try:
        start_upgrade_job(operation_id)
    except Exception:
        # start_upgrade_job records the job id before it pushes, so whether the
        # push landed is unknown here. Reverting from the route could race a
        # worker that did start; the reconciler owns this row instead and ends
        # it failed_preparation (host ACTIVE) if no job is alive.
        current_app.logger.exception('Runtime upgrade %s for host %s could not be queued',
                                     operation_id, host_id)
        return _error(ENQUEUE_FAILED, 500)

    return jsonify({'data': {'status': 'configuring'}, 'message': 'Runtime upgrade queued.'}), 202
