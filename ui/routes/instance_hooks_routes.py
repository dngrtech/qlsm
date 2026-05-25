import os
import re
import shutil
import tempfile
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ui import db
from ui.models import BinaryMetadata, InstanceStatus, QLInstance
from ui.task_lock import acquire_lock, release_lock
from ui.task_logic.ansible_instance_mgmt import RESERVED_HOOK_FILENAMES, _SYSTEM_HOOKS
from ui.task_logic.ansible_instance_hooks import _system_hook_source_path


CONFIGS_BASE = "configs"
ELF_MAGIC = b"\x7fELF"
_DRAFT_ID_RE = re.compile(r'^[0-9a-f-]{36}$')

instance_hooks_bp = Blueprint("instance_hooks_api", __name__)


def _scripts_dir(instance):
    return os.path.join(CONFIGS_BASE, instance.host.name, str(instance.id), "scripts")


def _draft_scripts_dir(draft_id):
    base = os.environ.get('QLDS_DRAFTS_DIR') or os.path.join(tempfile.gettempdir(), 'qlds-drafts')
    return os.path.join(base, draft_id, 'scripts')


def _enabled_list(instance):
    if not instance.ld_preload_hooks:
        return []
    return [h.strip() for h in instance.ld_preload_hooks.split(",") if h.strip()]


def _list_so_files(scripts_dir):
    files = []
    if not os.path.isdir(scripts_dir):
        return files
    for name in sorted(os.listdir(scripts_dir)):
        if not name.endswith(".so"):
            continue
        full_path = os.path.join(scripts_dir, name)
        try:
            stat = os.stat(full_path)
        except OSError:
            continue
        files.append({
            "filename": name,
            "size": stat.st_size,
            "modified": int(stat.st_mtime),
        })
    return files


def _description_map(instance):
    rows = BinaryMetadata.query.filter_by(
        context_type="instance",
        context_key=str(instance.id),
    ).all()
    return {row.file_path: row.description or "" for row in rows}


def _validate_filename(name):
    if not isinstance(name, str) or not name.strip():
        return "empty filename"
    if name != name.strip():
        return "filename must not contain leading or trailing whitespace"
    if not name.endswith(".so"):
        return "filename must end in .so"
    if "/" in name or "\\" in name or ".." in name:
        return "filename contains forbidden characters"
    if any(c in name for c in ('\n', '\r', '\x00')):
        return "filename contains forbidden control characters"
    if name in RESERVED_HOOK_FILENAMES:
        return "filename is reserved for a system hook"
    return None


def _is_elf_file(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == ELF_MAGIC
    except OSError:
        return False


def enqueue_apply_hooks(instance_id, *, restart_service, lock_token):
    from ui.task_logic.job_failure_handlers import instance_job_failure_handler
    from ui.tasks import apply_instance_hooks, enqueue_task

    return enqueue_task(
        apply_instance_hooks,
        instance_id,
        restart_service=restart_service,
        lock_token=lock_token,
        on_failure=instance_job_failure_handler,
    )


@instance_hooks_bp.route("/<int:instance_id>/hooks", methods=["GET"])
@jwt_required()
def get_instance_hooks(instance_id):
    instance = db.session.get(QLInstance, instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    draft_id = request.args.get('draft_id', '').strip()
    if draft_id and _DRAFT_ID_RE.match(draft_id):
        scripts_dir = _draft_scripts_dir(draft_id)
    else:
        scripts_dir = _scripts_dir(instance)

    on_disk = _list_so_files(scripts_dir)
    on_disk_names = {item["filename"] for item in on_disk}
    enabled = [name for name in _enabled_list(instance) if name in on_disk_names]
    order_map = {name: idx + 1 for idx, name in enumerate(enabled)}
    descriptions = _description_map(instance)

    available = []
    for item in on_disk:
        filename = item["filename"]
        is_enabled = filename in order_map
        available.append({
            **item,
            "enabled": is_enabled,
            "order": order_map[filename] if is_enabled else None,
            "description": descriptions.get(filename, ""),
        })

    system_hooks_active = []
    for filename, predicate, _subdir in _SYSTEM_HOOKS:
        if predicate(instance):
            src = _system_hook_source_path(filename)
            size = os.path.getsize(src) if os.path.isfile(src) else 0
            system_hooks_active.append({"filename": filename, "size": size})

    return jsonify({
        "data": {
            "available": available,
            "system_hooks_active": system_hooks_active,
        },
    }), 200


@instance_hooks_bp.route("/<int:instance_id>/hooks", methods=["PUT"])
@jwt_required()
def put_instance_hooks(instance_id):
    instance = db.session.get(QLInstance, instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "enabled" not in payload:
        return jsonify({"error": {"message": 'Body must be JSON {"enabled": [...]}'}}), 400

    enabled = payload["enabled"]
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        return jsonify({"error": {"message": "enabled must be a list of strings"}}), 400
    if len(enabled) != len(set(enabled)):
        return jsonify({"error": {"message": "duplicate filenames in enabled list"}}), 400

    for name in enabled:
        error = _validate_filename(name)
        if error:
            return jsonify({"error": {"message": f"{name}: {error}"}}), 400

    scripts_dir = _scripts_dir(instance)
    draft_id = payload.get('draft_id', '') or ''
    use_draft = bool(draft_id and _DRAFT_ID_RE.match(draft_id))
    draft_dir = _draft_scripts_dir(draft_id) if use_draft else None

    for name in enabled:
        full_path = os.path.join(scripts_dir, name)
        if not os.path.isfile(full_path):
            if draft_dir:
                draft_path = os.path.join(draft_dir, name)
                if os.path.isfile(draft_path):
                    os.makedirs(scripts_dir, exist_ok=True)
                    shutil.copy2(draft_path, full_path)
                else:
                    return jsonify({"error": {"message": f"{name}: file not found in scripts/"}}), 400
            else:
                return jsonify({"error": {"message": f"{name}: file not found in scripts/"}}), 400
        if not _is_elf_file(full_path):
            return jsonify({"error": {"message": f"{name}: not a valid ELF binary"}}), 400

    lock_token = str(uuid.uuid4())
    if not acquire_lock("instance", instance.id, lock_token, ttl=360):
        msg = f'Another operation is running on instance "{instance.name}". Please wait for it to complete.'
        return jsonify({"error": {"message": msg}}), 409

    original_hooks = instance.ld_preload_hooks
    restart_service = instance.status != InstanceStatus.STOPPED
    lock_transferred = False
    instance.ld_preload_hooks = ",".join(enabled) if enabled else None
    instance.status = InstanceStatus.CONFIGURING
    db.session.commit()

    try:
        job = enqueue_apply_hooks(
            instance.id,
            restart_service=restart_service,
            lock_token=lock_token,
        )
        if job:
            lock_transferred = True
            return jsonify({"data": {"task_id": job.id}}), 202

        instance.ld_preload_hooks = original_hooks
        instance.status = InstanceStatus.ERROR
        db.session.commit()
        return jsonify({"error": {"message": "Error queuing hook apply task."}}), 500
    except Exception:
        db.session.rollback()
        current = db.session.get(QLInstance, instance_id)
        if current:
            current.ld_preload_hooks = original_hooks
            current.status = InstanceStatus.ERROR
            db.session.commit()
        return jsonify({"error": {"message": "Error queuing hook apply task."}}), 500
    finally:
        if not lock_transferred:
            release_lock("instance", instance_id, lock_token)
