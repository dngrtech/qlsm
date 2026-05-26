"""
Draft workspace API routes for plugin file management.

Provides server-side staging for plugin files during instance/preset editing.
Drafts live in /tmp/qlds-drafts/<uuid>/scripts/ and are ephemeral.
"""

import os
import shutil
import time
import uuid
import sqlalchemy
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from ui import db
from ui.models import BinaryMetadata
from ui.preset_support import resolve_preset_subdir

draft_api_bp = Blueprint('draft_api_routes', __name__)

DRAFTS_BASE = '/tmp/qlds-drafts'
DRAFT_TTL_SECONDS = 3600  # 1 hour
CONFIGS_BASE = 'configs'
PRESETS_DIR = 'presets'
SCRIPTS_DIR = 'scripts'
USER_HOOKS_DIR = 'user-hooks'


def _get_drafts_base():
    """Return the drafts base directory, overridable via app config for testing."""
    return current_app.config.get('DRAFTS_BASE', DRAFTS_BASE)


def _get_draft_scripts_path(draft_id):
    """Return the scripts directory path for a draft."""
    return os.path.join(_get_drafts_base(), draft_id, SCRIPTS_DIR)


def _get_draft_user_hooks_path(draft_id):
    """Return the user-hooks directory path for a draft."""
    return os.path.join(_get_drafts_base(), draft_id, USER_HOOKS_DIR)


def _get_draft_base_path(draft_id):
    """Return the base directory path for a draft."""
    return os.path.join(_get_drafts_base(), draft_id)


def _validate_draft_id(draft_id):
    """Validate that a draft_id is a valid UUID4."""
    try:
        uuid.UUID(draft_id, version=4)
        return True
    except ValueError:
        return False


def _draft_exists(draft_id):
    """Check if a draft directory exists."""
    return os.path.exists(_get_draft_base_path(draft_id))


def _cleanup_stale_drafts():
    """Remove draft directories older than DRAFT_TTL_SECONDS."""
    drafts_base = _get_drafts_base()
    if not os.path.exists(drafts_base):
        return
    now = time.time()
    try:
        for entry in os.listdir(drafts_base):
            draft_path = os.path.join(drafts_base, entry)
            if not os.path.isdir(draft_path):
                continue
            try:
                mtime = os.path.getmtime(draft_path)
                if now - mtime > DRAFT_TTL_SECONDS:
                    shutil.rmtree(draft_path, ignore_errors=True)
                    current_app.logger.info(f"Cleaned up stale draft: {entry}")
            except OSError:
                continue
    except OSError:
        pass


def _seed_draft(draft_scripts_path, source_path):
    """Copy source plugin files into a draft directory.

    For non-default presets, default scripts are copied first so the full
    plugin list is always visible.  Preset-specific files overlay on top.
    This mirrors _read_preset_scripts() in preset_api_routes.py.
    """
    default_scripts = os.path.abspath(
        resolve_preset_subdir('default', SCRIPTS_DIR, CONFIGS_BASE)
    )
    presets_root = os.path.join(os.path.abspath(CONFIGS_BASE), PRESETS_DIR)
    is_non_default_preset = (
        source_path != default_scripts
        and _is_path_under(presets_root, source_path)
    )

    # Seed with default scripts first for non-default presets
    if is_non_default_preset and os.path.exists(default_scripts):
        shutil.copytree(default_scripts, draft_scripts_path, dirs_exist_ok=True)

    # Overlay source scripts (preset-specific or instance)
    if os.path.exists(source_path):
        shutil.copytree(source_path, draft_scripts_path, dirs_exist_ok=True)
    elif not os.path.exists(draft_scripts_path):
        os.makedirs(draft_scripts_path, exist_ok=True)

    # Seed user-hooks/ alongside scripts/ from the same source root
    source_root = os.path.dirname(source_path) if os.path.basename(source_path) == SCRIPTS_DIR else source_path
    source_user_hooks = os.path.join(source_root, USER_HOOKS_DIR)
    draft_user_hooks = os.path.join(os.path.dirname(draft_scripts_path), USER_HOOKS_DIR)
    if os.path.isdir(source_user_hooks):
        shutil.copytree(source_user_hooks, draft_user_hooks, dirs_exist_ok=True)
    elif not os.path.exists(draft_user_hooks):
        os.makedirs(draft_user_hooks, exist_ok=True)


def _is_path_under(allowed_root, resolved_path):
    """Validate that resolved_path is strictly under allowed_root.

    Appends os.sep to avoid the startswith('configs') vs 'configs-evil'
    prefix-escape bug.
    """
    norm_root = os.path.normpath(allowed_root)
    norm_path = os.path.normpath(resolved_path)
    return norm_path.startswith(norm_root + os.sep)


def _is_safe_name(value):
    """Reject values that contain path separators or parent-directory refs.

    Host names, instance IDs, and preset names are simple identifiers —
    they must never contain '/', '\\', or '..' components.
    """
    if not value:
        return False
    return '/' not in value and '\\' not in value and '..' not in value


ALLOWED_EXTENSIONS = {'.py', '.txt', '.so'}
FILE_TYPE_MAP = {'.py': 'python', '.txt': 'text', '.so': 'binary'}
VALID_BINARY_CONTEXT_TYPES = frozenset({'preset', 'instance'})


def _get_file_type(filename):
    """Return the file type category for a given filename."""
    ext = os.path.splitext(filename)[1].lower()
    return FILE_TYPE_MAP.get(ext)


def _build_draft_tree(path, base_path=None):
    """
    Recursively build a file tree with type metadata.

    Returns list of:
    - Files: { name, type: 'file', path, file_type, size, last_modified }
    - Folders: { name, type: 'folder', path, children }
    """
    if base_path is None:
        base_path = path

    if not os.path.exists(path):
        return []

    items = []
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return []

    for entry in entries:
        full_path = os.path.join(path, entry)
        relative_path = os.path.relpath(full_path, base_path)

        if entry.startswith('.') or entry == '__pycache__':
            continue

        if os.path.isdir(full_path):
            children = _build_draft_tree(full_path, base_path)
            items.append({
                'name': entry,
                'type': 'folder',
                'path': relative_path,
                'children': children
            })
        elif os.path.isfile(full_path):
            ext = os.path.splitext(entry)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                stat = os.stat(full_path)
                items.append({
                    'name': entry,
                    'type': 'file',
                    'path': relative_path,
                    'file_type': FILE_TYPE_MAP.get(ext, 'unknown'),
                    'size': stat.st_size,
                    'last_modified': stat.st_mtime
                })

    return items


TEXT_EXTENSIONS = {'.py', '.txt'}
MAX_TEXT_FILE_SIZE = 256 * 1024      # 256KB for .py, .txt
MAX_BINARY_FILE_SIZE = 10 * 1024 * 1024  # 10MB for .so
ELF_MAGIC = b'\x7fELF'


def _is_safe_draft_path(draft_scripts_path, relative_path):
    """Validate that a relative path doesn't escape the draft directory."""
    full_path = os.path.normpath(os.path.join(draft_scripts_path, relative_path))
    safe_prefix = os.path.normpath(draft_scripts_path) + os.sep
    return full_path.startswith(safe_prefix) or full_path == os.path.normpath(draft_scripts_path)


def _normalize_draft_file_path(relative_path):
    """Return a canonical slash-separated draft path, or None if unsafe/ambiguous."""
    if not isinstance(relative_path, str):
        return None
    stripped = relative_path.strip().replace('\\', '/')
    if not stripped or os.path.isabs(stripped):
        return None
    parts = stripped.split('/')
    if any(part in ('', '.', '..') for part in parts):
        return None
    return '/'.join(parts)


def _get_source_path(data):
    """Determine the source scripts path from request data. Returns None if invalid."""
    base = os.path.abspath(CONFIGS_BASE)
    source = data.get('source')

    if source == 'preset':
        preset = data.get('preset', 'default')
        if not _is_safe_name(preset):
            return None
        allowed_root = os.path.join(base, PRESETS_DIR)
        path = os.path.abspath(resolve_preset_subdir(preset, SCRIPTS_DIR, CONFIGS_BASE))
    elif source == 'instance':
        host = data.get('host')
        instance_id = data.get('instance_id')
        if not host or not instance_id:
            return None
        if not _is_safe_name(host) or not _is_safe_name(str(instance_id)):
            return None
        if host == PRESETS_DIR:
            return None
        allowed_root = os.path.join(base, host)
        path = os.path.join(base, host, str(instance_id), SCRIPTS_DIR)
    else:
        return None

    if not _is_path_under(allowed_root, path):
        return None
    return path


@draft_api_bp.route('/', methods=['POST'])
@jwt_required()
def create_draft():
    """Create a new draft workspace seeded from a preset or instance."""
    data = request.get_json()
    if not data or 'source' not in data:
        return jsonify({"error": {"message": "source is required (preset or instance)"}}), 400

    source_path = _get_source_path(data)
    if source_path is None:
        return jsonify({"error": {"message": "Invalid source. Provide preset name or host + instance_id."}}), 400

    _cleanup_stale_drafts()

    draft_id = str(uuid.uuid4())
    draft_scripts_path = _get_draft_scripts_path(draft_id)

    try:
        os.makedirs(os.path.dirname(draft_scripts_path), exist_ok=True)
        _seed_draft(draft_scripts_path, source_path)
    except OSError as e:
        current_app.logger.error(f"Failed to create draft {draft_id}: {e}")
        return jsonify({"error": {"message": "Failed to create draft workspace"}}), 500

    current_app.logger.info(f"Created draft {draft_id} from {source_path}")
    return jsonify({"data": {"draft_id": draft_id}}), 201


@draft_api_bp.route('/<draft_id>', methods=['DELETE'])
@jwt_required()
def discard_draft(draft_id):
    """Discard a draft workspace and delete all its files."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400

    draft_path = _get_draft_base_path(draft_id)
    if not os.path.exists(draft_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    shutil.rmtree(draft_path, ignore_errors=True)
    current_app.logger.info(f"Discarded draft {draft_id}")
    return jsonify({"data": {"message": "Draft discarded"}}), 200


@draft_api_bp.route('/<draft_id>/touch', methods=['POST'])
@jwt_required()
def touch_draft(draft_id):
    """Update draft mtime to prevent cleanup during long editing sessions."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400

    draft_path = _get_draft_base_path(draft_id)
    if not os.path.exists(draft_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    os.utime(draft_path, None)  # Sets mtime to current time
    return jsonify({"data": {"message": "Draft touched"}}), 200


@draft_api_bp.route('/<draft_id>/tree', methods=['GET'])
@jwt_required()
def get_draft_tree(draft_id):
    """Return the file tree for a draft workspace with type metadata."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400

    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    scripts_path = _get_draft_scripts_path(draft_id)
    tree = _build_draft_tree(scripts_path)
    return jsonify({"data": tree}), 200


@draft_api_bp.route('/<draft_id>/content', methods=['GET'])
@jwt_required()
def get_draft_content(draft_id):
    """Read text content of a .py or .txt file from the draft."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    path = request.args.get('path')
    if not path:
        return jsonify({"error": {"message": "path parameter is required"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not _is_safe_draft_path(scripts_path, path):
        return jsonify({"error": {"message": "Invalid file path"}}), 400

    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTENSIONS:
        return jsonify({"error": {"message": f"Cannot read {ext} files as text. Only .py and .txt are readable."}}), 400

    full_path = os.path.join(scripts_path, path)
    if not os.path.exists(full_path):
        return jsonify({"error": {"message": "File not found"}}), 404

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return jsonify({"error": {"message": "File is not valid UTF-8 text"}}), 400

    return jsonify({"data": {"path": path, "content": content}}), 200


@draft_api_bp.route('/<draft_id>/content', methods=['PUT'])
@jwt_required()
def save_draft_content(draft_id):
    """Write text content of a .py or .txt file to the draft."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    path = data.get('path')
    content = data.get('content')
    if not path or content is None:
        return jsonify({"error": {"message": "path and content are required"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not _is_safe_draft_path(scripts_path, path):
        return jsonify({"error": {"message": "Invalid file path"}}), 400

    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTENSIONS:
        return jsonify({"error": {"message": f"Cannot write {ext} files as text. Only .py and .txt are writable."}}), 400

    if len(content.encode('utf-8')) > MAX_TEXT_FILE_SIZE:
        return jsonify({"error": {"message": f"Content exceeds maximum size of {MAX_TEXT_FILE_SIZE // 1024}KB"}}), 400

    full_path = os.path.join(scripts_path, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # Touch the draft directory to keep it alive
    os.utime(_get_draft_base_path(draft_id), None)

    return jsonify({"data": {"path": path, "message": "Content saved"}}), 200


def _get_max_size(ext):
    """Return the max file size for a given extension."""
    if ext == '.so':
        return MAX_BINARY_FILE_SIZE
    return MAX_TEXT_FILE_SIZE


@draft_api_bp.route('/<draft_id>/upload', methods=['POST'])
@jwt_required()
def upload_to_draft(draft_id):
    """Upload a file to the draft workspace. Supports .py, .txt, .so."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    if 'file' not in request.files:
        return jsonify({"error": {"message": "No file provided"}}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": {"message": "No filename"}}), 400

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": {"message": f"Unsupported extension {ext}. Allowed: .py, .txt, .so"}}), 400

    content = file.read()
    max_size = _get_max_size(ext)
    if len(content) > max_size:
        size_label = f"{max_size // (1024*1024)}MB" if max_size >= 1024*1024 else f"{max_size // 1024}KB"
        return jsonify({"error": {"message": f"File exceeds {size_label} size limit"}}), 400

    if ext == '.so':
        if len(content) < 4 or content[:4] != ELF_MAGIC:
            return jsonify({"error": {"message": "Invalid .so file: missing ELF header. Expected a compiled shared library."}}), 400

    target_path = request.form.get('target_path', '')
    scripts_path = _get_draft_scripts_path(draft_id)

    if target_path:
        dest_dir = os.path.join(scripts_path, target_path)
        if not _is_safe_draft_path(scripts_path, target_path):
            return jsonify({"error": {"message": "Invalid target path"}}), 400
    else:
        dest_dir = scripts_path

    os.makedirs(dest_dir, exist_ok=True)
    dest_file = os.path.join(dest_dir, filename)

    with open(dest_file, 'wb') as f:
        f.write(content)

    relative = os.path.relpath(dest_file, scripts_path)
    os.utime(_get_draft_base_path(draft_id), None)

    return jsonify({"data": {"path": relative, "message": f"Uploaded {filename}"}}), 200


@draft_api_bp.route('/<draft_id>/file', methods=['DELETE'])
@jwt_required()
def delete_draft_file(draft_id):
    """Delete a file from the draft workspace."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    path = request.args.get('path')
    if not path:
        return jsonify({"error": {"message": "path parameter is required"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not _is_safe_draft_path(scripts_path, path):
        return jsonify({"error": {"message": "Invalid file path"}}), 400

    full_path = os.path.join(scripts_path, path)
    if not os.path.exists(full_path):
        return jsonify({"error": {"message": "File not found"}}), 404

    os.remove(full_path)
    os.utime(_get_draft_base_path(draft_id), None)

    return jsonify({"data": {"message": f"Deleted {path}"}}), 200


@draft_api_bp.route('/<draft_id>/rename', methods=['PATCH'])
@jwt_required()
def rename_draft_file(draft_id):
    """Rename a file within the draft workspace."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    old_path = _normalize_draft_file_path(data.get('old_path'))
    new_path = _normalize_draft_file_path(data.get('new_path'))
    if old_path is None or new_path is None:
        return jsonify({"error": {"message": "old_path and new_path must be strings"}}), 400

    scripts_path = _get_draft_scripts_path(draft_id)
    if not (
        _is_safe_draft_path(scripts_path, old_path)
        and _is_safe_draft_path(scripts_path, new_path)
    ):
        return jsonify({"error": {"message": "Invalid file path"}}), 400

    root_path = os.path.normpath(scripts_path)
    old_full = os.path.normpath(os.path.join(scripts_path, old_path))
    new_full = os.path.normpath(os.path.join(scripts_path, new_path))
    if old_full == root_path or new_full == root_path:
        return jsonify({"error": {"message": "Path must reference a file"}}), 400
    if not os.path.isfile(old_full):
        return jsonify({"error": {"message": "old_path must reference an existing file"}}), 400

    old_ext = os.path.splitext(old_path)[1].lower()
    new_ext = os.path.splitext(new_path)[1].lower()
    if old_ext not in ALLOWED_EXTENSIONS or new_ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": {"message": "Unsupported file extension"}}), 400
    if old_ext != new_ext:
        return jsonify({"error": {"message": "Rename cannot change file extension"}}), 400
    if os.path.exists(new_full):
        return jsonify({"error": {"message": "File already exists at new_path"}}), 409
    new_parent = os.path.dirname(new_full)
    if not os.path.isdir(new_parent):
        return jsonify({"error": {"message": "new_path parent directory does not exist"}}), 400

    is_binary = old_ext == '.so'
    if is_binary:
        context_type = data.get('context_type')
        context_key = data.get('context_key')
        if not isinstance(context_type, str) or not isinstance(context_key, str):
            return jsonify({"error": {"message": "context_type and context_key must be strings"}}), 400
        context_type = context_type.strip()
        context_key = context_key.strip()
        error = _validate_binary_rename_context(context_type, context_key)
        if error:
            return jsonify({"error": {"message": error}}), 400
        if _binary_metadata_exists(context_type, context_key, new_path):
            return jsonify({"error": {"message": "Binary metadata already exists for new_path"}}), 409

    try:
        if is_binary:
            row = _get_binary_metadata(context_type, context_key, old_path)
            if row:
                row.file_path = new_path
                db.session.flush()
        os.rename(old_full, new_full)
        if is_binary:
            try:
                db.session.commit()
            except sqlalchemy.exc.SQLAlchemyError as e:
                db.session.rollback()
                try:
                    if os.path.exists(new_full) and not os.path.exists(old_full):
                        os.rename(new_full, old_full)
                except OSError as reverse_err:
                    current_app.logger.error(
                        f"Failed to reverse rename {new_path} to {old_path}: {reverse_err}"
                    )
                current_app.logger.error(f"Failed to commit binary metadata rename: {e}")
                return jsonify({"error": {"message": "Rename failed"}}), 500
    except (OSError, sqlalchemy.exc.SQLAlchemyError) as e:
        if is_binary:
            db.session.rollback()
        current_app.logger.error(f"Failed to rename {old_path} to {new_path}: {e}")
        return jsonify({"error": {"message": "Rename failed"}}), 500

    os.utime(_get_draft_base_path(draft_id), None)
    return jsonify({"data": {"old_path": old_path, "new_path": new_path}}), 200


def _validate_binary_rename_context(context_type, context_key):
    if not context_type or not context_key:
        return "context_type and context_key are required for .so rename"
    if context_type not in VALID_BINARY_CONTEXT_TYPES:
        return "context_type must be 'preset' or 'instance'"
    if '/' in context_key or '\\' in context_key or '..' in context_key:
        return "Invalid context_key"
    return None


def _get_binary_metadata(context_type, context_key, file_path):
    return BinaryMetadata.query.filter_by(
        context_type=context_type,
        context_key=context_key,
        file_path=file_path,
    ).first()


def _binary_metadata_exists(context_type, context_key, file_path):
    return _get_binary_metadata(context_type, context_key, file_path) is not None


def _get_commit_target_path(data):
    """Determine the target scripts directory for a commit. Returns None if invalid."""
    base = os.path.abspath(CONFIGS_BASE)
    target = data.get('target')

    if target == 'instance':
        host = data.get('host')
        instance_id = data.get('instance_id')
        if not host or not instance_id:
            return None
        if not _is_safe_name(host) or not _is_safe_name(str(instance_id)):
            return None
        if not str(instance_id).isdigit():
            return None
        if host == PRESETS_DIR:
            return None
        allowed_root = os.path.join(base, host)
        path = os.path.join(base, host, str(instance_id), SCRIPTS_DIR)
    elif target == 'preset':
        preset = data.get('preset')
        if not preset:
            return None
        if not _is_safe_name(preset):
            return None
        allowed_root = os.path.join(base, PRESETS_DIR)
        path = os.path.abspath(resolve_preset_subdir(preset, SCRIPTS_DIR, CONFIGS_BASE))
    else:
        return None

    if not _is_path_under(allowed_root, path):
        return None
    return path


@draft_api_bp.route('/<draft_id>/commit', methods=['POST'])
@jwt_required()
def commit_draft(draft_id):
    """Commit draft contents to an instance or preset directory, then delete the draft."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft ID"}}), 400
    if not _draft_exists(draft_id):
        return jsonify({"error": {"message": "Draft not found"}}), 404

    data = request.get_json()
    if not data or 'target' not in data:
        return jsonify({"error": {"message": "target is required (instance or preset)"}}), 400

    target_path = _get_commit_target_path(data)
    if target_path is None:
        return jsonify({"error": {"message": "Invalid target. Provide host + instance_id or preset name."}}), 400

    draft_scripts_path = _get_draft_scripts_path(draft_id)

    if data.get("target") == "instance" and os.path.isdir(draft_scripts_path):
        from ui.task_logic.ansible_instance_mgmt import RESERVED_HOOK_FILENAMES
        for name in os.listdir(draft_scripts_path):
            if name in RESERVED_HOOK_FILENAMES:
                return jsonify({
                    "error": {
                        "message": f"Filename '{name}' is reserved for a system hook",
                    },
                }), 400

    try:
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        shutil.copytree(draft_scripts_path, target_path)
    except OSError as e:
        current_app.logger.error(f"Failed to commit draft {draft_id}: {e}")
        return jsonify({"error": {"message": "Failed to commit draft"}}), 500

    if data.get("target") == "instance":
        from ui.models import QLInstance
        from ui.task_logic.common import append_log

        instance = db.session.get(QLInstance, int(data["instance_id"]))
        if instance and instance.ld_preload_hooks:
            on_disk = (
                {name for name in os.listdir(target_path) if name.endswith(".so")}
                if os.path.isdir(target_path)
                else set()
            )
            current_hooks = [
                item.strip()
                for item in instance.ld_preload_hooks.split(",")
                if item.strip()
            ]
            kept_hooks = [name for name in current_hooks if name in on_disk]
            if kept_hooks != current_hooks:
                removed = sorted(set(current_hooks) - set(kept_hooks))
                instance.ld_preload_hooks = ",".join(kept_hooks) if kept_hooks else None
                append_log(instance, f"Removed deleted hooks from LD_PRELOAD: {removed}")
                db.session.commit()

    shutil.rmtree(_get_draft_base_path(draft_id), ignore_errors=True)
    current_app.logger.info(f"Committed draft {draft_id} to {target_path}")

    return jsonify({"data": {"message": "Draft committed"}}), 200


# --- Draft folder endpoints ---

import re as _re

_DRAFT_FOLDER_SEGMENT_RE = _re.compile(r'^[A-Za-z0-9._-]+$')


def _normalize_draft_folder_path(rel_path):
    """Validate and normalize a draft folder path.

    Returns the normalized relative path (forward-slash separated) or None if invalid.
    Rules: non-empty, no leading/trailing slash, each segment matches [A-Za-z0-9._-]+
    and is ≤64 chars, reject '.' and '..' segments, reject segments starting with '.'.
    """
    if not isinstance(rel_path, str):
        return None
    rel_path = rel_path.strip()
    if not rel_path or rel_path.startswith('/') or rel_path.endswith('/'):
        return None
    segments = rel_path.split('/')
    for seg in segments:
        if not seg or seg in ('.', '..') or seg.startswith('.'):
            return None
        if len(seg) > 64 or not _DRAFT_FOLDER_SEGMENT_RE.match(seg):
            return None
    return '/'.join(segments)


@draft_api_bp.route('/<draft_id>/folders', methods=['POST'])
@jwt_required()
def create_draft_folder(draft_id):
    """Create a new folder inside the draft scripts directory."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft_id"}}), 400
    scripts_path = _get_draft_scripts_path(draft_id)
    if not os.path.isdir(scripts_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404
    data = request.get_json() or {}
    rel_path = _normalize_draft_folder_path(data.get('path'))
    if rel_path is None:
        return jsonify({"error": {"message": "Invalid path"}}), 400
    if not _is_safe_draft_path(scripts_path, rel_path):
        return jsonify({"error": {"message": "Invalid path"}}), 400
    target = os.path.join(scripts_path, rel_path)
    if os.path.exists(target):
        return jsonify({"error": {"message": "Folder already exists"}}), 409
    os.makedirs(target, exist_ok=False)
    return jsonify({"data": {"path": rel_path}}), 201


@draft_api_bp.route('/<draft_id>/folders', methods=['DELETE'])
@jwt_required()
def delete_draft_folder(draft_id):
    """Delete a folder (recursive) inside the draft scripts directory."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft_id"}}), 400
    scripts_path = _get_draft_scripts_path(draft_id)
    if not os.path.isdir(scripts_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404
    rel_path = _normalize_draft_folder_path(request.args.get('path'))
    if rel_path is None:
        return jsonify({"error": {"message": "Invalid path"}}), 400
    if not _is_safe_draft_path(scripts_path, rel_path):
        return jsonify({"error": {"message": "Invalid path"}}), 400
    target = os.path.join(scripts_path, rel_path)
    if not os.path.isdir(target):
        return jsonify({"error": {"message": "Folder not found"}}), 404
    shutil.rmtree(target)
    return jsonify({"data": {"path": rel_path}}), 200


@draft_api_bp.route('/<draft_id>/folders', methods=['PATCH'])
@jwt_required()
def rename_draft_folder(draft_id):
    """Rename a folder inside the draft scripts directory."""
    if not _validate_draft_id(draft_id):
        return jsonify({"error": {"message": "Invalid draft_id"}}), 400
    scripts_path = _get_draft_scripts_path(draft_id)
    if not os.path.isdir(scripts_path):
        return jsonify({"error": {"message": "Draft not found"}}), 404
    data = request.get_json() or {}
    old_path = _normalize_draft_folder_path(data.get('old_path'))
    new_path = _normalize_draft_folder_path(data.get('new_path'))
    if old_path is None or new_path is None:
        return jsonify({"error": {"message": "Invalid path"}}), 400
    if not (_is_safe_draft_path(scripts_path, old_path) and _is_safe_draft_path(scripts_path, new_path)):
        return jsonify({"error": {"message": "Invalid path"}}), 400
    src = os.path.join(scripts_path, old_path)
    dst = os.path.join(scripts_path, new_path)
    if not os.path.isdir(src):
        return jsonify({"error": {"message": "Source folder not found"}}), 404
    if os.path.exists(dst):
        return jsonify({"error": {"message": "Target already exists"}}), 409
    os.rename(src, dst)
    return jsonify({"data": {"old_path": old_path, "new_path": new_path}}), 200
