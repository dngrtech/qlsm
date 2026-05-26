"""Per-file CRUD endpoints for instance user-hooks/."""
import os
import re as _re
import secrets

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

from ui import db
from ui.models import BinaryMetadata, QLInstance
from ui.routes.instance_hooks_routes import _validate_filename, _is_elf_file
from ui.task_logic.hook_paths import user_hooks_dir, CONFIGS_BASE  # noqa: F401 (CONFIGS_BASE monkeypatched in tests)
from ui.task_lock import acquire_lock, release_lock
from ui.routes.draft_routes import MAX_BINARY_FILE_SIZE as MAX_HOOK_BYTES

_CRUD_LOCK_TTL = 30

DESCRIPTION_MAX_LEN = 1000
_DESC_RE = _re.compile(r'^[^<>{}"]*$')

instance_hooks_files_bp = Blueprint("instance_hooks_files_api", __name__)


def _hook_path(instance, filename):
    return os.path.join(user_hooks_dir(instance), filename)


def _load_instance(instance_id):
    instance = db.session.get(QLInstance, instance_id)
    if not instance or not instance.host:
        return None
    return instance


def _acquire_or_409(instance_id):
    token = secrets.token_hex(16)
    if not acquire_lock("instance", instance_id, token, ttl=_CRUD_LOCK_TTL):
        return None, (jsonify({"error": {"message": "Another operation is running"}}), 409)
    return token, None


# ── Upload ────────────────────────────────────────────────────────────────────

@instance_hooks_files_bp.route("/<int:instance_id>/hooks/files", methods=["POST"])
@jwt_required()
def upload_hook_file(instance_id):
    instance = _load_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    if "file" not in request.files:
        return jsonify({"error": {"message": "No file provided"}}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"error": {"message": "No filename"}}), 400

    filename = secure_filename(upload.filename)
    if filename != upload.filename:
        return jsonify({"error": {"message": "filename contains forbidden characters"}}), 400

    error = _validate_filename(filename)
    if error:
        return jsonify({"error": {"message": error}}), 400

    upload.seek(0, 2)
    size = upload.tell()
    upload.seek(0)
    if size == 0:
        return jsonify({"error": {"message": "Empty file"}}), 400
    if size > MAX_HOOK_BYTES:
        return jsonify({"error": {"message": f"File exceeds {MAX_HOOK_BYTES} bytes"}}), 400

    head = upload.read(4)
    upload.seek(0)
    if head != b"\x7fELF":
        return jsonify({"error": {"message": "Not a valid ELF binary"}}), 400

    token, err_response = _acquire_or_409(instance_id)
    if err_response:
        return err_response
    try:
        hooks_dir = user_hooks_dir(instance)
        os.makedirs(hooks_dir, exist_ok=True)
        target = os.path.join(hooks_dir, filename)
        if os.path.exists(target):
            return jsonify({"error": {"message": f"{filename} already exists"}}), 409
        upload.save(target)
    finally:
        release_lock("instance", instance_id, token)

    return jsonify({"data": {
        "filename": filename,
        "size": os.path.getsize(target),
        "modified": int(os.path.getmtime(target)),
        "enabled": False,
        "order": None,
        "description": "",
    }}), 201


# ── Replace ───────────────────────────────────────────────────────────────────

@instance_hooks_files_bp.route("/<int:instance_id>/hooks/files/<filename>", methods=["PUT"])
@jwt_required()
def replace_hook_file(instance_id, filename):
    instance = _load_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    error = _validate_filename(filename)
    if error:
        return jsonify({"error": {"message": error}}), 400

    target = _hook_path(instance, filename)
    if not os.path.isfile(target):
        return jsonify({"error": {"message": f"{filename} not found"}}), 404

    if "file" not in request.files:
        return jsonify({"error": {"message": "No file provided"}}), 400
    upload = request.files["file"]

    upload.seek(0, 2); size = upload.tell(); upload.seek(0)
    if size == 0:
        return jsonify({"error": {"message": "Empty file"}}), 400
    if size > MAX_HOOK_BYTES:
        return jsonify({"error": {"message": f"File exceeds {MAX_HOOK_BYTES} bytes"}}), 400
    if upload.read(4) != b"\x7fELF":
        return jsonify({"error": {"message": "Not a valid ELF binary"}}), 400
    upload.seek(0)

    token, err_response = _acquire_or_409(instance_id)
    if err_response:
        return err_response
    try:
        upload.save(target)
    finally:
        release_lock("instance", instance_id, token)

    return jsonify({"data": {
        "filename": filename,
        "size": os.path.getsize(target),
        "modified": int(os.path.getmtime(target)),
    }}), 200


# ── Download ──────────────────────────────────────────────────────────────────

@instance_hooks_files_bp.route("/<int:instance_id>/hooks/files/<filename>", methods=["GET"])
@jwt_required()
def download_hook_file(instance_id, filename):
    instance = _load_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    error = _validate_filename(filename)
    if error:
        return jsonify({"error": {"message": error}}), 400

    target = _hook_path(instance, filename)
    if not os.path.isfile(target):
        return jsonify({"error": {"message": f"{filename} not found"}}), 404

    return send_file(
        os.path.abspath(target),
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream",
    )


# ── Rename ────────────────────────────────────────────────────────────────────

@instance_hooks_files_bp.route("/<int:instance_id>/hooks/files/<filename>", methods=["PATCH"])
@jwt_required()
def rename_hook_file(instance_id, filename):
    instance = _load_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    error = _validate_filename(filename)
    if error:
        return jsonify({"error": {"message": error}}), 400

    payload = request.get_json(silent=True) or {}
    new_name = payload.get("new_name", "")
    if not isinstance(new_name, str):
        return jsonify({"error": {"message": "new_name must be a string"}}), 400
    new_name = new_name.strip()
    error = _validate_filename(new_name)
    if error:
        return jsonify({"error": {"message": error}}), 400

    if new_name == filename:
        return jsonify({"data": {"filename": filename}}), 200

    src = _hook_path(instance, filename)
    if not os.path.isfile(src):
        return jsonify({"error": {"message": f"{filename} not found"}}), 404
    dst = _hook_path(instance, new_name)
    if os.path.exists(dst):
        return jsonify({"error": {"message": f"{new_name} already exists"}}), 409

    token, err_response = _acquire_or_409(instance_id)
    if err_response:
        return err_response
    try:
        os.rename(src, dst)
        db.session.refresh(instance)
        if instance.ld_preload_hooks:
            hooks = [h.strip() for h in instance.ld_preload_hooks.split(",") if h.strip()]
            if filename in hooks:
                hooks = [new_name if h == filename else h for h in hooks]
                instance.ld_preload_hooks = ",".join(hooks)

        row = BinaryMetadata.query.filter_by(
            context_type="instance", context_key=str(instance.id), file_path=filename,
        ).first()
        if row:
            row.file_path = new_name

        db.session.commit()
    finally:
        release_lock("instance", instance_id, token)

    return jsonify({"data": {"filename": new_name}}), 200


# ── Delete ────────────────────────────────────────────────────────────────────

@instance_hooks_files_bp.route("/<int:instance_id>/hooks/files/<filename>", methods=["DELETE"])
@jwt_required()
def delete_hook_file(instance_id, filename):
    instance = _load_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    error = _validate_filename(filename)
    if error:
        return jsonify({"error": {"message": error}}), 400

    target = _hook_path(instance, filename)
    if not os.path.isfile(target):
        return jsonify({"error": {"message": f"{filename} not found"}}), 404

    token, err_response = _acquire_or_409(instance_id)
    if err_response:
        return err_response
    try:
        os.remove(target)
        db.session.refresh(instance)
        if instance.ld_preload_hooks:
            hooks = [h.strip() for h in instance.ld_preload_hooks.split(",") if h.strip()]
            if filename in hooks:
                hooks = [h for h in hooks if h != filename]
                instance.ld_preload_hooks = ",".join(hooks) if hooks else None

        row = BinaryMetadata.query.filter_by(
            context_type="instance", context_key=str(instance.id), file_path=filename,
        ).first()
        if row:
            db.session.delete(row)

        db.session.commit()
    finally:
        release_lock("instance", instance_id, token)

    return ("", 204)


# ── Description ───────────────────────────────────────────────────────────────

@instance_hooks_files_bp.route(
    "/<int:instance_id>/hooks/files/<filename>/description", methods=["PATCH"]
)
@jwt_required()
def set_hook_description(instance_id, filename):
    instance = _load_instance(instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    error = _validate_filename(filename)
    if error:
        return jsonify({"error": {"message": error}}), 400

    if not os.path.isfile(_hook_path(instance, filename)):
        return jsonify({"error": {"message": f"{filename} not found"}}), 404

    payload = request.get_json(silent=True) or {}
    description = payload.get("description")
    if not isinstance(description, str):
        return jsonify({"error": {"message": "description must be a string"}}), 400
    description = description.strip()
    if len(description) > DESCRIPTION_MAX_LEN:
        return jsonify({"error": {"message": f"max {DESCRIPTION_MAX_LEN} chars"}}), 400
    if not _DESC_RE.match(description):
        return jsonify({"error": {"message": 'invalid characters (<, >, {, }, ")'}}), 400

    row = BinaryMetadata.query.filter_by(
        context_type="instance", context_key=str(instance.id), file_path=filename,
    ).first()
    if row:
        row.description = description
    else:
        db.session.add(BinaryMetadata(
            context_type="instance", context_key=str(instance.id),
            file_path=filename, description=description,
        ))
    db.session.commit()
    return jsonify({"data": {"description": description}}), 200
