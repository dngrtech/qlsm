import base64
import fnmatch
import io
import json
import os
import re
import shutil
import zipfile
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required
from ui import db
from ui.database import get_presets, create_preset, get_preset, update_preset, delete_preset
from ui.models import BinaryMetadata
from ui.preset_support import (
    PRESETS_DIR,
    is_internal_preset_name,
    resolve_preset_subdir,
    validate_user_preset_name,
)
from ui.routes.draft_routes import ELF_MAGIC, MAX_BINARY_FILE_SIZE

preset_api_bp = Blueprint('preset_api_routes', __name__)  # url_prefix will be /presets

# Config file mapping for API response keys
CONFIG_FILE_MAP = {
    'server.cfg': 'server_cfg',
    'mappool.txt': 'mappool_txt',
    'access.txt': 'access_txt',
    'workshop.txt': 'workshop_txt'
}

# Reverse mapping for writing files from API request
API_TO_FILE_MAP = {v: k for k, v in CONFIG_FILE_MAP.items()}
ALLOWED_PRESET_CONFIG_EXTENSIONS = {'.cfg', '.txt', '.ent'}
ALLOWED_PRESET_FACTORY_EXTENSIONS = {'.factories'}
PROTECTED_CONFIG_FILES = set(CONFIG_FILE_MAP.keys())
RESERVED_CONFIG_FOLDER_NAMES = {'scripts', 'factories', 'user-hooks'}
MAX_CONFIG_PATH_DEPTH = 2
EXPORT_FORMAT_VERSION = 1
EXPORT_EXCLUDED_DIRS = {'__pycache__'}
EXPORT_EXCLUDED_FILES = {'.DS_Store', '.gitkeep'}
EXPORT_EXCLUDED_PATTERNS = ('*.pyc', '*.pyo', '*.swp', '*.tmp', '*~')


def _safe_export_filename(name):
    """Return a filesystem/browser-safe base filename for preset exports."""
    safe = re.sub(r'\s+', '-', name or '')
    safe = re.sub(r'[^A-Za-z0-9._-]+', '-', safe)
    safe = re.sub(r'-+', '-', safe).strip('.-')
    return safe or 'preset'


def _should_skip_export_path(relative_path, is_dir=False):
    """Return True for generated/editor junk that should not enter exports."""
    parts = relative_path.replace(os.sep, '/').split('/')
    if any(part in EXPORT_EXCLUDED_DIRS for part in parts):
        return True
    name = parts[-1]
    if is_dir:
        return name in EXPORT_EXCLUDED_DIRS
    if name in EXPORT_EXCLUDED_FILES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXPORT_EXCLUDED_PATTERNS)


def _ignore_generated_script_cruft(directory, names):
    """Return generated/editor junk to skip when saving draft scripts."""
    ignored = []
    for name in names:
        path = os.path.join(directory, name)
        if _should_skip_export_path(name, is_dir=os.path.isdir(path)):
            ignored.append(name)
    return ignored


def _resolve_export_root(preset_path):
    """Resolve and validate that an export root stays under PRESETS_DIR."""
    root = os.path.realpath(preset_path)
    presets_root = os.path.realpath(PRESETS_DIR)
    try:
        if os.path.commonpath([presets_root, root]) != presets_root:
            raise ValueError("Preset path is outside presets directory")
    except ValueError as exc:
        raise ValueError("Preset path is outside presets directory") from exc
    return root


def _preset_export_manifest(preset, binary_metadata_count):
    return {
        'type': 'qlsm-preset-export',
        'format_version': EXPORT_FORMAT_VERSION,
        'preset': {
            'id': preset.id,
            'name': preset.name,
            'description': preset.description,
            'is_builtin': bool(preset.is_builtin),
            'created_at': preset.created_at.isoformat() if preset.created_at else None,
            'last_updated': preset.last_updated.isoformat() if preset.last_updated else None,
        },
        'includes': {
            'preset_directory': True,
            'configs': True,
            'factories': True,
            'scripts': True,
            'user_hooks': True,
            'checked_plugins': True,
            'checked_factories': True,
            'enabled_hooks': True,
            'binary_metadata': True,
        },
        'counts': {
            'binary_metadata': binary_metadata_count,
        },
    }


def _preset_binary_metadata_export(preset_name):
    rows = BinaryMetadata.query.filter_by(
        context_type='preset',
        context_key=preset_name,
    ).order_by(BinaryMetadata.file_path.asc()).all()
    return {
        'format_version': EXPORT_FORMAT_VERSION,
        'metadata': [
            {
                'file_path': row.file_path,
                'description': row.description or '',
            }
            for row in rows
        ],
    }


def _build_preset_export_zip(preset, root):
    """Build an in-memory ZIP containing preset.path plus export metadata."""
    binary_metadata = _preset_binary_metadata_export(preset.name)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            'manifest.json',
            json.dumps(
                _preset_export_manifest(preset, len(binary_metadata['metadata'])),
                indent=2,
                sort_keys=True,
            ) + '\n',
        )
        archive.writestr(
            'binary_metadata.json',
            json.dumps(binary_metadata, indent=2, sort_keys=True) + '\n',
        )

        for current_root, dirs, files in os.walk(root):
            dirs[:] = [
                dirname for dirname in dirs
                if not os.path.islink(os.path.join(current_root, dirname))
                and not _should_skip_export_path(
                    os.path.relpath(os.path.join(current_root, dirname), root),
                    is_dir=True,
                )
            ]
            for filename in sorted(files):
                full_path = os.path.join(current_root, filename)
                if os.path.islink(full_path):
                    current_app.logger.debug(
                        'Skipping preset export symlink: %s', full_path
                    )
                    continue
                full_real = os.path.realpath(full_path)
                try:
                    inside_root = os.path.commonpath([root, full_real]) == root
                except ValueError:
                    inside_root = False
                if not inside_root:
                    current_app.logger.warning(
                        'Skipping preset export path outside root: %s', full_real
                    )
                    continue
                rel_path = os.path.relpath(full_real, root).replace(os.sep, '/')
                if _should_skip_export_path(rel_path):
                    continue
                if rel_path in {'manifest.json', 'binary_metadata.json'}:
                    continue
                try:
                    archive.write(full_real, rel_path)
                except FileNotFoundError:
                    current_app.logger.warning(
                        'Skipping disappeared preset export path: %s', full_path
                    )

    buffer.seek(0)
    return buffer


def _validate_flat_filename(filename, allowed_extensions, label):
    if not isinstance(filename, str) or not filename:
        raise ValueError(f"Invalid {label} filename: {filename}")
    if (
        os.path.isabs(filename) or '/' in filename or '\\' in filename or
        '..' in filename or filename.startswith('.')
    ):
        raise ValueError(f"Invalid {label} filename: {filename}")
    if os.path.splitext(filename)[1].lower() not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions))
        raise ValueError(f"Invalid {label} extension for {filename}. Allowed: {allowed}")


def _validate_path_segment(name, allowed_extensions=None, label='config'):
    if not isinstance(name, str) or not name:
        raise ValueError(f"Invalid {label} filename: {name}")
    if '/' in name or '\\' in name or '..' in name or name.startswith('.'):
        raise ValueError(f"Invalid {label} filename: {name}")
    if not all(char.isalnum() or char in '._-' for char in name):
        raise ValueError(f"Invalid {label} filename: {name}")
    if len(name) > 64:
        raise ValueError(f"Invalid {label} filename: {name}")
    if allowed_extensions is not None and os.path.splitext(name)[1].lower() not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions))
        raise ValueError(f"Invalid {label} extension for {name}. Allowed: {allowed}")


def _validate_relative_config_path(path):
    if not isinstance(path, str) or not path or path.startswith('/') or path.endswith('/'):
        raise ValueError(f"Invalid config filename: {path}")
    segments = path.split('/')
    if len(segments) > MAX_CONFIG_PATH_DEPTH:
        raise ValueError(f"Invalid config filename: {path}")
    for i, segment in enumerate(segments):
        is_file = i == len(segments) - 1
        _validate_path_segment(
            segment,
            ALLOWED_PRESET_CONFIG_EXTENSIONS if is_file else None,
            'config',
        )
    if len(segments) > 1 and segments[0].lower() in RESERVED_CONFIG_FOLDER_NAMES:
        raise ValueError(f"Reserved folder name: {segments[0]}")


def _normalize_config_folders(folders):
    if folders is None:
        return []
    if not isinstance(folders, list):
        raise ValueError("config_folders must be a list")
    normalized = []
    for name in folders:
        _validate_path_segment(name, None, 'config')
        if name.lower() in RESERVED_CONFIG_FOLDER_NAMES:
            raise ValueError(f"Reserved folder name: {name}")
        normalized.append(name)
    return normalized


def _normalize_text_content(content, label, filename):
    if content is None:
        return ''
    if not isinstance(content, str):
        raise ValueError(f"{label} content for {filename} must be a string")
    return content


def _normalize_preset_config_files(config_data):
    has_generic = 'configs' in config_data
    generic = config_data.get('configs')
    if has_generic:
        if not isinstance(generic, dict):
            raise ValueError("'configs' must be a dict")

        config_files = {}
        for filename, content in generic.items():
            _validate_relative_config_path(filename)
            config_files[filename] = _normalize_text_content(
                content, 'Config', filename
            )

        missing = PROTECTED_CONFIG_FILES - set(config_files.keys())
        if missing:
            files = ', '.join(sorted(missing))
            raise ValueError(f"Built-in files cannot be removed: {files}")
        return config_files, True

    config_files = {}
    for api_key, filename in API_TO_FILE_MAP.items():
        content = config_data.get(api_key)
        if content is not None:
            config_files[filename] = _normalize_text_content(
                content, 'Config', filename
            )
    return config_files, False


def _normalize_preset_factory_files(factories_data):
    if not isinstance(factories_data, dict):
        raise ValueError("'factories' must be a dict")

    factories = {}
    for filename, content in factories_data.items():
        _validate_flat_filename(
            filename, ALLOWED_PRESET_FACTORY_EXTENSIONS, 'factory'
        )
        factories[filename] = _normalize_text_content(
            content, 'Factory', filename
        )
    return factories


def _validate_preset_write_payload(data, has_config_updates=True):
    if has_config_updates:
        _normalize_preset_config_files(data)
    if 'config_folders' in data:
        _normalize_config_folders(data['config_folders'])
    if 'factories' in data:
        _normalize_preset_factory_files(data['factories'])


def _validate_checked_plugins_payload(data):
    if 'checked_plugins' not in data:
        return None
    checked_plugins = data['checked_plugins']
    if (
        not isinstance(checked_plugins, list) or
        not all(isinstance(plugin, str) for plugin in checked_plugins)
    ):
        return "checked_plugins must be a list of strings"
    return None


def _validate_checked_factories_payload(data):
    if 'checked_factories' not in data:
        return None
    checked_factories = data['checked_factories']
    if (
        not isinstance(checked_factories, list) or
        not all(isinstance(f, str) and f.lower().endswith('.factories') for f in checked_factories)
    ):
        return "checked_factories must be a list of .factories filenames"
    return None


def _validate_enabled_hooks_payload(data):
    if 'enabled_hooks' not in data:
        return None
    enabled_hooks = data['enabled_hooks']
    if (
        not isinstance(enabled_hooks, list) or
        not all(isinstance(h, str) and h.lower().endswith('.so') for h in enabled_hooks)
    ):
        return "enabled_hooks must be a list of .so filenames"
    return None


def _validation_error_response(error):
    return jsonify({"error": {"message": str(error)}}), 400


def _read_preset_configs(preset_path):
    """Read all managed config files from a preset folder."""
    configs_map = {}
    legacy = {}

    if os.path.isdir(preset_path):
        for rel_path in _list_preset_config_files(preset_path):
            filepath = os.path.join(preset_path, rel_path)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                configs_map[rel_path] = content
                if rel_path in CONFIG_FILE_MAP:
                    legacy[CONFIG_FILE_MAP[rel_path]] = content
            except Exception as e:
                current_app.logger.error(f"Error reading preset config file {filepath}: {e}")

    for filename, api_key in CONFIG_FILE_MAP.items():
        legacy.setdefault(api_key, '')
        configs_map.setdefault(filename, legacy[api_key])

    return {
        **legacy,
        'configs': configs_map,
        'config_folders': _list_preset_config_folders(preset_path),
    }


SCRIPT_READ_EXTENSIONS = ('.py', '.txt', '.so')


def _read_script_file(filepath):
    """Read a plugin script for API responses.

    .so files are binary and JSON responses must stay JSON-safe, so they are
    base64-encoded here. _write_preset_scripts decodes them back on save.
    """
    if filepath.lower().endswith('.so'):
        with open(filepath, 'rb') as f:
            return base64.b64encode(f.read()).decode('ascii')
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def _read_preset_scripts(preset_path):
    """Read all plugin scripts from a preset's scripts/ folder.

    For non-default presets that have their own scripts folder, the default
    preset's scripts are merged in first so they are not lost. Preset-specific
    files take priority over defaults with the same relative path.
    """
    scripts = {}
    scripts_dir = os.path.join(preset_path, 'scripts')
    if not os.path.exists(scripts_dir):
        return scripts

    # For non-default presets, merge default scripts first so the preset
    # only needs to store its customisations (new or overridden files).
    # Use the basename of preset_path (the preset name) rather than a
    # CWD-dependent os.path.abspath comparison for robustness.
    default_scripts_dir = resolve_preset_subdir('default', 'scripts')
    if os.path.basename(preset_path) != 'default' and os.path.exists(default_scripts_dir):
        for root, _, files in os.walk(default_scripts_dir):
            for filename in files:
                if filename.lower().endswith(SCRIPT_READ_EXTENSIONS):
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, default_scripts_dir)
                    try:
                        scripts[rel_path] = _read_script_file(filepath)
                    except Exception as e:
                        current_app.logger.error(f"Error reading default script {filepath}: {e}")

    for root, _, files in os.walk(scripts_dir):
        for filename in files:
            if filename.lower().endswith(SCRIPT_READ_EXTENSIONS):
                filepath = os.path.join(root, filename)
                # Get relative path from scripts_dir
                rel_path = os.path.relpath(filepath, scripts_dir)
                try:
                    scripts[rel_path] = _read_script_file(filepath)
                except Exception as e:
                    current_app.logger.error(f"Error reading script {filepath}: {e}")
    return scripts


def _write_preset_scripts(preset_path, scripts_data):
    """Write scripts to a preset's scripts/ folder."""
    if not scripts_data:
        return

    scripts_dir = os.path.join(preset_path, 'scripts')
    os.makedirs(scripts_dir, exist_ok=True)

    for rel_path, content in scripts_data.items():
        # Security: ensure path doesn't escape scripts directory
        full_path = os.path.normpath(os.path.join(scripts_dir, rel_path))
        if not full_path.startswith(os.path.normpath(scripts_dir)):
            current_app.logger.warning(f"Skipping script with invalid path: {rel_path}")
            continue

        # Create parent directories if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if isinstance(content, bytes):
            # Only reached via the ZIP-import bundle, which already ran the
            # ELF magic + size checks in preset_import_validation.py.
            with open(full_path, 'wb') as f:
                f.write(content)
        elif rel_path.lower().endswith('.so'):
            # .so content from the API is base64 text (see _read_script_file).
            # Validated the same way ZIP-imported .so files are: size cap and
            # ELF magic. Raising ValueError surfaces a 400 to the caller
            # instead of silently saving a preset with a dropped plugin.
            try:
                decoded = base64.b64decode(content, validate=True)
            except (ValueError, TypeError):
                raise ValueError(f"Script {rel_path} is not valid base64.")
            if len(decoded) > MAX_BINARY_FILE_SIZE:
                raise ValueError(
                    f"Script {rel_path} exceeds {MAX_BINARY_FILE_SIZE // (1024 * 1024)}MB."
                )
            if not decoded.startswith(ELF_MAGIC):
                raise ValueError(f"Script {rel_path} is not a valid ELF binary.")
            with open(full_path, 'wb') as f:
                f.write(decoded)
        else:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
        current_app.logger.info(f"Wrote preset script: {full_path}")


def _read_preset_factories(preset_path):
    """Read selected .factories files from a preset's factories/ folder.

    If checked_factories.json exists, only the listed filenames are returned
    (those are the user-selected factories for the preset). If it is absent,
    all files in factories/ are returned for backward-compatibility with
    presets created before this field was introduced.
    """
    factories = {}
    factories_dir = os.path.join(preset_path, 'factories')
    if not os.path.exists(factories_dir):
        return factories

    checked = _read_preset_checked_factories(preset_path)
    # checked == None  → legacy preset, include all files
    # checked == []   → no factories selected
    # checked == [..] → only those filenames are selected

    for filename in sorted(os.listdir(factories_dir)):
        filepath = os.path.join(factories_dir, filename)
        if not os.path.isfile(filepath) or not filename.lower().endswith('.factories'):
            continue
        if checked is not None and filename not in checked:
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                factories[filename] = f.read()
        except Exception as e:
            current_app.logger.error(f"Error reading factory {filepath}: {e}")
    return factories


def _write_preset_factories(preset_path, factories_data):
    """Write preset factory files with sync semantics."""
    factories = _normalize_preset_factory_files(factories_data)
    factories_dir = os.path.join(preset_path, 'factories')
    os.makedirs(factories_dir, exist_ok=True)

    existing = {
        filename for filename in os.listdir(factories_dir)
        if filename.lower().endswith('.factories') and
        os.path.isfile(os.path.join(factories_dir, filename))
    }

    for filename, content in factories.items():
        filepath = os.path.join(factories_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        current_app.logger.info(f"Wrote preset factory: {filepath}")

    for filename in sorted(existing - set(factories.keys())):
        filepath = os.path.join(factories_dir, filename)
        try:
            os.remove(filepath)
            current_app.logger.info(f"Removed preset factory: {filepath}")
        except OSError as e:
            current_app.logger.error(f"Error removing preset factory {filepath}: {e}")


def _read_preset_checked_plugins(preset_path):
    """Read checked_plugins.json from a preset folder.
    Returns a list of plugin paths, or None if the file does not exist.
    """
    filepath = os.path.join(preset_path, 'checked_plugins.json')
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading checked_plugins.json from {filepath}: {e}")
        return None


def _write_preset_checked_plugins(preset_path, checked_plugins):
    """Write checked_plugins.json to a preset folder."""
    os.makedirs(preset_path, exist_ok=True)
    filepath = os.path.join(preset_path, 'checked_plugins.json')
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(checked_plugins, f)
        current_app.logger.info(f"Wrote checked_plugins.json: {filepath}")
    except Exception as e:
        current_app.logger.error(f"Error writing checked_plugins.json to {filepath}: {e}")


def _read_preset_checked_factories(preset_path):
    """Read checked_factories.json from a preset folder.
    Returns a list of factory filenames, or None if the file does not exist.
    None means "legacy" — treat all files in factories/ as selected.
    """
    filepath = os.path.join(preset_path, 'checked_factories.json')
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading checked_factories.json from {filepath}: {e}")
        return None


def _write_preset_checked_factories(preset_path, checked_factories):
    """Write checked_factories.json to a preset folder."""
    os.makedirs(preset_path, exist_ok=True)
    filepath = os.path.join(preset_path, 'checked_factories.json')
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(checked_factories, f)
        current_app.logger.info(f"Wrote checked_factories.json: {filepath}")
    except Exception as e:
        current_app.logger.error(f"Error writing checked_factories.json to {filepath}: {e}")


def _read_preset_enabled_hooks(preset_path):
    """Read enabled_hooks.json from a preset folder.
    Returns a list of hook filenames (LD_PRELOAD order), or None if the file
    does not exist — None means the preset never recorded an enabled-hooks state.
    """
    filepath = os.path.join(preset_path, 'enabled_hooks.json')
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading enabled_hooks.json from {filepath}: {e}")
        return None


def _write_preset_enabled_hooks(preset_path, enabled_hooks):
    """Write enabled_hooks.json to a preset folder."""
    os.makedirs(preset_path, exist_ok=True)
    filepath = os.path.join(preset_path, 'enabled_hooks.json')
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(enabled_hooks, f)
        current_app.logger.info(f"Wrote enabled_hooks.json: {filepath}")
    except Exception as e:
        current_app.logger.error(f"Error writing enabled_hooks.json to {filepath}: {e}")


def _list_preset_config_files(preset_path):
    """Yield relative managed config paths, excluding reserved preset subdirs."""
    if not os.path.isdir(preset_path):
        return
    for root, dirs, files in os.walk(preset_path):
        if root == preset_path:
            dirs[:] = [
                d for d in dirs
                if d.lower() not in RESERVED_CONFIG_FOLDER_NAMES
            ]
        for filename in sorted(files):
            if os.path.splitext(filename)[1].lower() not in ALLOWED_PRESET_CONFIG_EXTENSIONS:
                continue
            full_path = os.path.join(root, filename)
            yield os.path.relpath(full_path, preset_path).replace(os.sep, '/')


def _list_preset_config_folders(preset_path):
    """Return top-level managed config folder names for a preset."""
    if not os.path.isdir(preset_path):
        return []
    return sorted(
        name for name in os.listdir(preset_path)
        if os.path.isdir(os.path.join(preset_path, name))
        and name.lower() not in RESERVED_CONFIG_FOLDER_NAMES
    )


def _write_preset_configs(preset_path, config_data):
    """Write preset config files.

    Legacy API keys are partial writes. The generic configs map is a sync
    payload and removes managed config files absent from the map.
    """
    config_files, should_sync = _normalize_preset_config_files(config_data)
    config_folders_present = 'config_folders' in config_data
    config_folders = _normalize_config_folders(
        config_data.get('config_folders')
    ) if config_folders_present else None
    os.makedirs(preset_path, exist_ok=True)

    for rel_path, content in config_files.items():
        filepath = os.path.join(preset_path, rel_path)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        current_app.logger.info(f"Wrote preset config file: {filepath}")

    if not should_sync:
        return

    desired_folders = set(config_folders or [])
    for rel_path in config_files:
        if '/' in rel_path:
            desired_folders.add(rel_path.split('/', 1)[0])

    for folder in sorted(desired_folders):
        os.makedirs(os.path.join(preset_path, folder), exist_ok=True)

    for rel_path in _list_preset_config_files(preset_path):
        if rel_path in PROTECTED_CONFIG_FILES:
            continue
        if rel_path in config_files:
            continue
        filepath = os.path.join(preset_path, rel_path)
        try:
            os.remove(filepath)
            current_app.logger.info(f"Removed preset config file: {filepath}")
        except OSError as e:
            current_app.logger.error(f"Error removing preset config file {filepath}: {e}")

    if not config_folders_present:
        return

    for folder in _list_preset_config_folders(preset_path):
        if folder in desired_folders:
            continue
        folder_path = os.path.join(preset_path, folder)
        try:
            os.rmdir(folder_path)
            current_app.logger.info(f"Removed empty preset config folder: {folder_path}")
        except OSError as e:
            current_app.logger.warning(
                f"Skipping non-empty preset config folder {folder_path}: {e}"
            )


def _validation_status(reason):
    return 400 if reason == 'format' else 409


def _copy_binary_metadata(from_type, from_key, to_key):
    """Stage BinaryMetadata upserts from a source context to a preset context."""
    rows = BinaryMetadata.query.filter_by(
        context_type=from_type,
        context_key=from_key,
    ).all()

    for row in rows:
        existing = BinaryMetadata.query.filter_by(
            context_type='preset',
            context_key=to_key,
            file_path=row.file_path,
        ).first()
        if existing:
            existing.description = row.description
        else:
            db.session.add(BinaryMetadata(
                context_type='preset',
                context_key=to_key,
                file_path=row.file_path,
                description=row.description,
            ))

    db.session.flush()
    return len(rows)


def _rename_binary_metadata(old_key, new_key):
    """Stage BinaryMetadata re-keying when a preset is renamed."""
    if old_key == new_key:
        return 0

    rows = BinaryMetadata.query.filter_by(
        context_type='preset',
        context_key=old_key,
    ).all()

    for row in rows:
        existing = BinaryMetadata.query.filter_by(
            context_type='preset',
            context_key=new_key,
            file_path=row.file_path,
        ).first()
        if existing:
            existing.description = row.description
            db.session.delete(row)
        else:
            row.context_key = new_key

    db.session.flush()
    return len(rows)


def _validate_binary_meta_source(source):
    """Return a normalized binary metadata source tuple, or (None, None)."""
    if not isinstance(source, dict):
        return None, None

    src_type = source.get('context_type')
    src_key = source.get('context_key')
    if not isinstance(src_type, str) or not isinstance(src_key, str):
        return None, None

    src_type = src_type.strip()
    src_key = src_key.strip()
    if src_type not in ('preset', 'instance'):
        return None, None
    if not src_key or '/' in src_key or '\\' in src_key or '..' in src_key:
        return None, None

    return src_type, src_key


@preset_api_bp.route('/validate-name', methods=['GET'], endpoint='validate_preset_name_api')
@jwt_required()
def validate_preset_name_api():
    """Check if a preset name is valid and available."""
    name = request.args.get('name', '').strip()

    is_valid, error, _ = validate_user_preset_name(name)

    return jsonify({
        "data": {
            "is_valid": is_valid,
            "error": error
        }
    })


@preset_api_bp.route('/', methods=['GET'], endpoint='list_presets_api')
@jwt_required()
def list_presets_api():
    """Returns a list of all configuration presets (metadata only)."""
    presets = get_presets()
    preset_list = [preset.to_dict() for preset in presets]
    return jsonify({"data": preset_list})


@preset_api_bp.route('/', methods=['POST'], endpoint='create_preset_api')
@jwt_required()
def create_preset_api():
    """Creates a new configuration preset (saves to filesystem)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    name = data.get('name', '').strip()

    # Validate name
    is_valid, error, reason = validate_user_preset_name(name)
    if not is_valid:
        return jsonify({"error": {"message": error}}), _validation_status(reason)

    checked_plugins_error = _validate_checked_plugins_payload(data)
    if checked_plugins_error:
        return jsonify({"error": {"message": checked_plugins_error}}), 400

    checked_factories_error = _validate_checked_factories_payload(data)
    if checked_factories_error:
        return jsonify({"error": {"message": checked_factories_error}}), 400

    enabled_hooks_error = _validate_enabled_hooks_payload(data)
    if enabled_hooks_error:
        return jsonify({"error": {"message": enabled_hooks_error}}), 400

    description = data.get('description', '')
    preset_path = os.path.join(PRESETS_DIR, name)

    # Validate draft before any filesystem mutations
    draft_id = data.get('draft_id')
    if draft_id:
        from ui.routes.draft_routes import (
            _validate_draft_id, _draft_exists,
            _get_draft_scripts_path
        )
        if not _validate_draft_id(draft_id):
            return jsonify({"error": {"message": "Invalid draft_id"}}), 400
        if not _draft_exists(draft_id):
            return jsonify({"error": {"message": "Draft not found"}}), 400

    try:
        _validate_preset_write_payload(data)
    except ValueError as e:
        return _validation_error_response(e)

    try:
        # Step 1: Create folder and write config files
        _write_preset_configs(preset_path, data)

        # Step 1b: Write scripts via draft or legacy
        if draft_id:
            from ui.routes.draft_routes import _get_draft_user_hooks_path

            draft_scripts = _get_draft_scripts_path(draft_id)
            preset_scripts_dir = os.path.join(preset_path, 'scripts')
            if os.path.exists(draft_scripts):
                if os.path.exists(preset_scripts_dir):
                    shutil.rmtree(preset_scripts_dir)
                shutil.copytree(
                    draft_scripts,
                    preset_scripts_dir,
                    ignore=_ignore_generated_script_cruft,
                )
            draft_user_hooks = _get_draft_user_hooks_path(draft_id)
            preset_user_hooks = os.path.join(preset_path, 'user-hooks')
            if os.path.isdir(draft_user_hooks):
                shutil.copytree(draft_user_hooks, preset_user_hooks, dirs_exist_ok=True)
            # Don't delete the draft — the form continues using it after preset save
        elif 'scripts' in data:
            _write_preset_scripts(preset_path, data['scripts'])

        # Step 1c: Write factories if provided
        if 'factories' in data:
            _write_preset_factories(preset_path, data['factories'])

        # Step 1d: Write checked plugins/factories if provided
        if 'checked_plugins' in data:
            _write_preset_checked_plugins(preset_path, data['checked_plugins'])

        if 'checked_factories' in data:
            _write_preset_checked_factories(preset_path, data['checked_factories'])

        if 'enabled_hooks' in data:
            _write_preset_enabled_hooks(preset_path, data['enabled_hooks'])

        # Step 2: Create DB record
        preset_data = {
            'name': name,
            'description': description,
            'path': preset_path
        }
        new_preset = create_preset(**preset_data)
        current_app.logger.info(f"ConfigPreset '{new_preset.name}' created with ID {new_preset.id} at {preset_path}")

        binary_meta_source = data.get('binary_meta_source')
        metadata_copied = False
        if binary_meta_source:
            src_type, src_key = _validate_binary_meta_source(binary_meta_source)
            same_preset_context = src_type == 'preset' and src_key == name
            if src_type and not same_preset_context:
                metadata_copied = _copy_binary_metadata(src_type, src_key, name) > 0

        # Return preset data with config content and scripts for immediate use
        response_data = new_preset.to_dict()
        response_data.update(_read_preset_configs(preset_path))
        response_data['scripts'] = _read_preset_scripts(preset_path)
        response_data['factories'] = _read_preset_factories(preset_path)
        response_data['checked_plugins'] = _read_preset_checked_plugins(preset_path)
        response_data['checked_factories'] = _read_preset_checked_factories(preset_path)
        response_data['enabled_hooks'] = _read_preset_enabled_hooks(preset_path)

        if metadata_copied:
            db.session.commit()

        return jsonify({"data": response_data, "message": "Preset created successfully."}), 201

    except ValueError as e:
        if os.path.exists(preset_path):
            try:
                shutil.rmtree(preset_path)
            except Exception as cleanup_err:
                current_app.logger.error(f"Failed to cleanup preset folder {preset_path}: {cleanup_err}")
        db.session.rollback()
        return _validation_error_response(e)

    except Exception as e:
        # Cleanup folder if DB creation fails
        if os.path.exists(preset_path):
            try:
                shutil.rmtree(preset_path)
            except Exception as cleanup_err:
                current_app.logger.error(f"Failed to cleanup preset folder {preset_path}: {cleanup_err}")
        db.session.rollback()
        current_app.logger.error(f"Error creating preset: {e}", exc_info=True)
        return jsonify({"error": {"message": f"Error creating preset: {str(e)}"}}), 500


@preset_api_bp.route('/<int:preset_id>', methods=['GET'], endpoint='get_preset_api')
@jwt_required()
def get_preset_api(preset_id):
    """Returns a specific configuration preset with config content (reads from filesystem)."""
    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    # Check if preset folder exists
    if not os.path.exists(preset.path):
        current_app.logger.error(f"Preset folder missing for preset {preset_id}: {preset.path}")
        return jsonify({"error": {"message": "Preset configuration files not found."}}), 500

    # Build response with metadata, config content, and scripts
    response_data = preset.to_dict()
    response_data.update(_read_preset_configs(preset.path))
    response_data['scripts'] = _read_preset_scripts(preset.path)
    response_data['factories'] = _read_preset_factories(preset.path)
    response_data['checked_plugins'] = _read_preset_checked_plugins(preset.path)
    response_data['checked_factories'] = _read_preset_checked_factories(preset.path)
    response_data['enabled_hooks'] = _read_preset_enabled_hooks(preset.path)

    return jsonify({"data": response_data})


@preset_api_bp.route('/<int:preset_id>/download', methods=['GET'], endpoint='download_preset_api')
@jwt_required()
def download_preset_api(preset_id):
    """Download a saved preset directory as a portable ZIP archive."""
    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    if preset.is_builtin:
        return jsonify({"error": {"message": "Cannot download a built-in preset."}}), 403

    try:
        root = _resolve_export_root(preset.path)
    except ValueError:
        current_app.logger.error(
            "Preset export path outside presets directory for preset %s", preset_id
        )
        return jsonify({"error": {"message": "Preset path is invalid."}}), 500

    if not os.path.isdir(root):
        current_app.logger.error(
            "Preset folder missing for preset %s", preset_id
        )
        return jsonify({"error": {"message": "Preset configuration files not found."}}), 500

    try:
        archive = _build_preset_export_zip(preset, root)
        return send_file(
            archive,
            as_attachment=True,
            download_name=f'{_safe_export_filename(preset.name)}.zip',
            mimetype='application/zip',
        )
    except Exception as e:
        current_app.logger.error(
            "Error exporting preset %s: %s", preset_id, e, exc_info=True
        )
        return jsonify({"error": {"message": "Failed to export preset archive."}}), 500


@preset_api_bp.route('/<int:preset_id>', methods=['PUT'], endpoint='update_preset_api')
@jwt_required()
def update_preset_api(preset_id):
    """Updates a specific configuration preset."""
    data = request.get_json()
    if not data:
        return jsonify({"error": {"message": "Request body must be JSON"}}), 400

    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    original_preset_name = preset.name
    name_provided = 'name' in data
    requested_name = data.get('name')
    new_name = None
    if name_provided:
        if not isinstance(requested_name, str):
            return jsonify({"error": {"message": "Preset name must be a string."}}), 400
        new_name = requested_name.strip()
        data['name'] = new_name
        if preset.is_builtin and new_name != preset.name:
            return jsonify({"error": {"message": "Cannot rename a built-in preset."}}), 403

    checked_plugins_error = _validate_checked_plugins_payload(data)
    if checked_plugins_error:
        return jsonify({"error": {"message": checked_plugins_error}}), 400

    checked_factories_error = _validate_checked_factories_payload(data)
    if checked_factories_error:
        return jsonify({"error": {"message": checked_factories_error}}), 400

    enabled_hooks_error = _validate_enabled_hooks_payload(data)
    if enabled_hooks_error:
        return jsonify({"error": {"message": enabled_hooks_error}}), 400

    # Check for name change
    if name_provided and new_name != original_preset_name:
        is_valid, error, reason = validate_user_preset_name(
            new_name, current_preset_id=preset.id
        )
        if not is_valid:
            return jsonify({"error": {"message": error}}), _validation_status(reason)

    # Validate draft before any filesystem mutations
    draft_id = data.get('draft_id')
    if draft_id:
        from ui.routes.draft_routes import (
            _validate_draft_id, _draft_exists,
            _get_draft_scripts_path
        )
        if not _validate_draft_id(draft_id):
            return jsonify({"error": {"message": "Invalid draft_id"}}), 400
        if not _draft_exists(draft_id):
            return jsonify({"error": {"message": "Draft not found"}}), 400

    has_config_updates = 'configs' in data or any(
        key in data for key in API_TO_FILE_MAP.keys()
    )
    try:
        _validate_preset_write_payload(data, has_config_updates)
    except ValueError as e:
        return _validation_error_response(e)

    try:
        # Update config files if provided
        if has_config_updates:
            _write_preset_configs(preset.path, data)

        # Update scripts via draft or legacy
        if draft_id:
            from ui.routes.draft_routes import _get_draft_user_hooks_path

            draft_scripts = _get_draft_scripts_path(draft_id)
            preset_scripts_dir = os.path.join(preset.path, 'scripts')
            if os.path.exists(draft_scripts):
                if os.path.exists(preset_scripts_dir):
                    shutil.rmtree(preset_scripts_dir)
                shutil.copytree(
                    draft_scripts,
                    preset_scripts_dir,
                    ignore=_ignore_generated_script_cruft,
                )
            draft_user_hooks = _get_draft_user_hooks_path(draft_id)
            preset_user_hooks = os.path.join(preset.path, 'user-hooks')
            if os.path.isdir(draft_user_hooks):
                shutil.copytree(draft_user_hooks, preset_user_hooks, dirs_exist_ok=True)
            # Don't delete the draft — the form continues using it after preset save
        elif 'scripts' in data:
            _write_preset_scripts(preset.path, data['scripts'])

        # Update factories if provided
        if 'factories' in data:
            _write_preset_factories(preset.path, data['factories'])

        # Update checked plugins/factories if provided
        if 'checked_plugins' in data:
            _write_preset_checked_plugins(preset.path, data['checked_plugins'])

        if 'checked_factories' in data:
            _write_preset_checked_factories(preset.path, data['checked_factories'])

        if 'enabled_hooks' in data:
            _write_preset_enabled_hooks(preset.path, data['enabled_hooks'])

        # Handle name change (rename folder)
        renamed_preset = name_provided and new_name != original_preset_name
        if renamed_preset:
            old_path = preset.path
            new_path = os.path.join(PRESETS_DIR, new_name)
            shutil.move(old_path, new_path)
            data['path'] = new_path
            current_app.logger.info(f"Renamed preset folder from {old_path} to {new_path}")

        # Update DB record
        update_data = {}
        if 'name' in data:
            update_data['name'] = data['name']
        if 'description' in data:
            update_data['description'] = data['description']
        if 'path' in data:
            update_data['path'] = data['path']

        if update_data:
            updated_preset = update_preset(preset_id, **update_data)
        else:
            updated_preset = preset

        if updated_preset:
            current_app.logger.info(f"ConfigPreset '{updated_preset.name}' (ID: {preset_id}) updated.")

            metadata_renamed = False
            if renamed_preset:
                metadata_renamed = (
                    _rename_binary_metadata(original_preset_name, updated_preset.name) > 0
                )

            binary_meta_source = data.get('binary_meta_source')
            metadata_copied = False
            if binary_meta_source:
                src_type, src_key = _validate_binary_meta_source(binary_meta_source)
                if src_type:
                    metadata_copied = (
                        _copy_binary_metadata(src_type, src_key, updated_preset.name) > 0
                    )

            response_data = updated_preset.to_dict()
            response_data.update(_read_preset_configs(updated_preset.path))
            response_data['scripts'] = _read_preset_scripts(updated_preset.path)
            response_data['factories'] = _read_preset_factories(updated_preset.path)
            response_data['checked_plugins'] = _read_preset_checked_plugins(updated_preset.path)
            response_data['checked_factories'] = _read_preset_checked_factories(updated_preset.path)
            response_data['enabled_hooks'] = _read_preset_enabled_hooks(updated_preset.path)

            if metadata_copied or metadata_renamed:
                db.session.commit()

            return jsonify({"data": response_data, "message": "Preset updated successfully."})
        else:
            return jsonify({"error": {"message": "Preset update failed."}}), 500

    except ValueError as e:
        db.session.rollback()
        return _validation_error_response(e)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating preset {preset_id}: {e}", exc_info=True)
        return jsonify({"error": {"message": f"Error updating preset: {str(e)}"}}), 500


@preset_api_bp.route('/<int:preset_id>', methods=['DELETE'], endpoint='delete_preset_api')
@jwt_required()
def delete_preset_api(preset_id):
    """Deletes a specific configuration preset (removes DB record + folder)."""
    preset = get_preset(preset_id)
    if not preset:
        return jsonify({"error": {"message": "Preset not found."}}), 404

    if preset.is_builtin:
        return jsonify({"error": {"message": "Cannot delete a built-in preset."}}), 403
    if is_internal_preset_name(preset.name):
        return jsonify({"error": {"message": "Cannot delete an internal preset namespace."}}), 403

    try:
        preset_name = preset.name
        preset_path = preset.path

        # Step 1: Delete DB record first
        if delete_preset(preset_id):
            current_app.logger.info(f"ConfigPreset '{preset_name}' (ID: {preset_id}) deleted from database.")

            # Step 2: Delete folder
            if os.path.exists(preset_path):
                shutil.rmtree(preset_path)
                current_app.logger.info(f"Deleted preset folder: {preset_path}")

            return jsonify({"message": f"Preset '{preset_name}' deleted successfully."}), 200
        else:
            return jsonify({"error": {"message": "Preset deletion failed."}}), 500

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting preset {preset_id}: {e}", exc_info=True)
        return jsonify({"error": {"message": f"Error deleting preset: {str(e)}"}}), 500
