import os
import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ui import db
from ui.models import BinaryMetadata, QLInstance
from ui.task_logic.ansible_instance_mgmt import RESERVED_HOOK_FILENAMES, _SYSTEM_HOOKS
from ui.task_logic.ansible_instance_hooks import _system_hook_source_path
from ui.task_logic.hook_paths import user_hooks_dir as _user_hooks_dir, draft_user_hooks_dir as _draft_user_hooks_dir


ELF_MAGIC = b"\x7fELF"
_DRAFT_ID_RE = re.compile(r'^[0-9a-f-]{36}$')

instance_hooks_bp = Blueprint("instance_hooks_api", __name__)


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


@instance_hooks_bp.route("/<int:instance_id>/hooks", methods=["GET"])
@jwt_required()
def get_instance_hooks(instance_id):
    instance = db.session.get(QLInstance, instance_id)
    if not instance:
        return jsonify({"error": {"message": "Instance not found"}}), 404

    draft_id = request.args.get('draft_id', '').strip()
    if draft_id and _DRAFT_ID_RE.match(draft_id):
        hooks_dir = _draft_user_hooks_dir(draft_id)
    else:
        hooks_dir = _user_hooks_dir(instance)

    on_disk = _list_so_files(hooks_dir)
    on_disk_names = {item["filename"] for item in on_disk}
    all_enabled = _enabled_list(instance)
    enabled = [name for name in all_enabled if name in on_disk_names]
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
            "missing": False,
        })

    # Include hooks registered in DB but absent from disk so the UI can surface
    # and remove them — without this they are invisible and unremovable.
    for name in all_enabled:
        if name not in on_disk_names:
            available.append({
                "filename": name,
                "size": 0,
                "modified": 0,
                "enabled": True,
                "order": None,
                "description": descriptions.get(name, ""),
                "missing": True,
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
