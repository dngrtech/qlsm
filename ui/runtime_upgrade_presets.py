"""Manual-fallback presets saved with a pre-upgrade snapshot.

One minqlx preset per instance, built from the snapshot's verified staged copy
(never the live directory) with the same writers the "save as preset" route
uses. Rollback restores the directory snapshot, not these presets; they exist
so the operator can see and reapply the pre-upgrade state from the preset
manager.

Preset names are `pre-minqlxtended-<host>-<instance id>-<operation id>`. The
whole suffix is reserved, and only the host fragment is truncated to fit the
100-character column. The full operation id makes each attempt unique and
marks the preset as owned by that operation, which is how cleanup finds them.
"""
import json
import os
import re
import shutil

from ui import db
from ui.admin_permissions import strip_numeric_admin_lines
from ui.models import BinaryMetadata, ConfigPreset
from ui.runtime import MINQLX
from ui.runtime_upgrade import _checked_plugins, _tree_digests

PRESET_PREFIX = 'pre-minqlxtended-'
MAX_PRESET_NAME_LENGTH = ConfigPreset.__table__.c.name.type.length
_UNSAFE_NAME_CHARS = re.compile(r'[^A-Za-z0-9_-]')


class SnapshotPresetError(RuntimeError):
    """A fallback preset could not be written or did not read back as written."""


def snapshot_preset_name(host_name, instance_id, operation_id):
    suffix = f'-{instance_id}-{operation_id}'
    room = MAX_PRESET_NAME_LENGTH - len(PRESET_PREFIX) - len(suffix)
    fragment = _UNSAFE_NAME_CHARS.sub('-', host_name or '')[:max(room, 0)]
    return f'{PRESET_PREFIX}{fragment}{suffix}'


def _is_owned(name, operation_id):
    return name.startswith(PRESET_PREFIX) and name.endswith(f'-{operation_id}')


def _create_preset_row(**fields):
    from ui.database import create_preset
    return create_preset(**fields)


def _parse_hooks(ld_preload_hooks):
    """Same split as the instance hooks endpoint; None stays None."""
    if ld_preload_hooks is None:
        return None
    return [hook.strip() for hook in ld_preload_hooks.split(',') if hook.strip()]


def _read_text(root, rel_path):
    with open(os.path.join(root, *rel_path.split('/')), 'r', encoding='utf-8') as handle:
        return handle.read()


def _read_factories(tree):
    factories_dir = os.path.join(tree, 'factories')
    if not os.path.isdir(factories_dir):
        return {}
    return {
        name: _read_text(factories_dir, name)
        for name in sorted(os.listdir(factories_dir))
        if name.lower().endswith('.factories') and os.path.isfile(os.path.join(factories_dir, name))
    }


def _copied_tree_digests(root):
    """Digests of the files `copytree(..., ignore=_ignore_generated_script_cruft)` keeps."""
    from ui.routes.preset_api_routes import _should_skip_export_path

    return {rel: digest for rel, digest in _tree_digests(root).items()
            if not _should_skip_export_path(rel)}


def _expected_contents(tree, meta):
    from ui.routes import preset_api_routes as routes

    configs = {rel: _read_text(tree, rel) for rel in routes._list_preset_config_files(tree)}
    for filename in routes.PROTECTED_CONFIG_FILES:
        configs.setdefault(filename, '')
    factories = _read_factories(tree)
    checked_plugins = None
    if meta['qlx_plugins'] is not None:
        checked_plugins = routes._enableable_plugin_entries(
            _checked_plugins(meta['qlx_plugins']) or [])
    return {
        'payload': {
            'configs': configs,
            'config_folders': routes._list_preset_config_folders(tree),
            'factories': factories,
        },
        'checked_factories': sorted(factories),
        'checked_plugins': checked_plugins,
        'enabled_hooks': _parse_hooks(meta['ld_preload_hooks']),
        'lan_rate_enabled': bool(meta['lan_rate_enabled']),
    }


def _write_preset_files(preset_path, tree, expected):
    from ui.routes import preset_api_routes as routes

    payload = expected['payload']
    routes._validate_preset_write_payload(payload, preset_path=preset_path)
    routes._write_preset_configs(preset_path, payload)
    for subdir in ('scripts', 'user-hooks'):
        source = os.path.join(tree, subdir)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(preset_path, subdir),
                            ignore=routes._ignore_generated_script_cruft)
    routes._write_preset_factories(preset_path, payload['factories'])
    routes._write_preset_checked_factories(preset_path, expected['checked_factories'])
    # A NULL selection is "never recorded" (no file), distinct from an empty list.
    if expected['checked_plugins'] is not None:
        routes._write_preset_checked_plugins(preset_path, expected['checked_plugins'])
    if expected['enabled_hooks'] is not None:
        routes._write_preset_enabled_hooks(preset_path, expected['enabled_hooks'])
    routes._write_preset_lan_rate_enabled(preset_path, expected['lan_rate_enabled'])


def _validate_preset(name, preset_path, tree, expected):
    """Read the preset back. The JSON writers log and swallow their own errors,
    so a write that silently failed is only caught here."""
    from ui.routes import preset_api_routes as routes

    problems = []
    for rel_path, content in expected['payload']['configs'].items():
        want = strip_numeric_admin_lines(content) if os.path.basename(rel_path) == 'access.txt' else content
        try:
            if _read_text(preset_path, rel_path) != want:
                problems.append(f'{rel_path} differs')
        except (OSError, ValueError):
            problems.append(f'{rel_path} unreadable')
    for folder in expected['payload']['config_folders']:
        if not os.path.isdir(os.path.join(preset_path, folder)):
            problems.append(f'folder {folder} missing')
    for subdir in ('scripts', 'user-hooks'):
        want = _copied_tree_digests(os.path.join(tree, subdir))
        if _tree_digests(os.path.join(preset_path, subdir)) != want:
            problems.append(f'{subdir}/ differs')
    if routes._read_preset_factories(preset_path) != expected['payload']['factories']:
        problems.append('factories differ')
    checks = (
        ('checked_factories', routes._read_preset_checked_factories),
        ('checked_plugins', routes._read_preset_checked_plugins),
        ('enabled_hooks', routes._read_preset_enabled_hooks),
        ('lan_rate_enabled', routes._read_preset_lan_rate_enabled),
    )
    for key, reader in checks:
        if reader(preset_path) != expected[key]:
            problems.append(f'{key} differs')
    row = ConfigPreset.query.filter_by(name=name).first()
    if row is None or row.path != preset_path or row.runtime != MINQLX:
        problems.append('database row missing or wrong')
    if problems:
        raise SnapshotPresetError(f'Fallback preset {name} failed validation: ' + '; '.join(problems))


def _save_one(host, operation_id, instance_id, tree, meta):
    from ui.preset_support import validate_user_preset_name
    from ui.routes import preset_api_routes as routes

    name = snapshot_preset_name(host.name, instance_id, operation_id)
    valid, error, _reason = validate_user_preset_name(name)
    if not valid:
        raise SnapshotPresetError(error)
    preset_path = os.path.join(routes.PRESETS_DIR, name)
    if os.path.lexists(preset_path):
        raise SnapshotPresetError(f'Preset directory {preset_path} already exists')

    expected = _expected_contents(tree, meta)
    _write_preset_files(preset_path, tree, expected)
    _create_preset_row(
        name=name,
        description=(f'Automatic snapshot of instance {meta["instance_name"]} on host '
                     f'{host.name} before the minqlxtended upgrade (operation {operation_id}).'),
        path=preset_path,
        runtime=MINQLX,
    )
    routes._copy_binary_metadata('instance', str(instance_id), name)
    db.session.commit()
    _validate_preset(name, preset_path, tree, expected)
    return name


def save_snapshot_presets(host, operation_id):
    """Create, commit and validate one fallback preset per snapshotted instance.

    Reads the operation's staged snapshot (or the published one when staging
    is gone). On any failure, removes every preset this operation created and
    re-raises.
    """
    from ui.runtime_upgrade_snapshot import snapshot_source_dir

    source = snapshot_source_dir(host.id, operation_id)
    names = []
    try:
        meta_root = os.path.join(source, 'instances')
        # A host with no instances has no instances/ directory and no presets.
        entries = os.listdir(meta_root) if os.path.isdir(meta_root) else []
        for instance_id in sorted(int(entry) for entry in entries):
            with open(os.path.join(meta_root, str(instance_id), 'instance.json'),
                      encoding='utf-8') as handle:
                meta = json.load(handle)
            tree = os.path.join(source, 'inputs', 'instances', str(instance_id))
            names.append(_save_one(host, operation_id, instance_id, tree, meta))
    except Exception:
        db.session.rollback()
        delete_snapshot_presets(operation_id)
        raise
    return names


def delete_snapshot_presets(operation_id):
    """Remove the rows, binary metadata and directories of this operation's presets.

    Only names carrying this operation's id are touched.
    """
    from ui.routes import preset_api_routes as routes

    owned = [row for row in ConfigPreset.query.filter(
        ConfigPreset.name.like(f'{PRESET_PREFIX}%-{operation_id}')).all()
        if _is_owned(row.name, operation_id)]
    names = {row.name for row in owned}
    if os.path.isdir(routes.PRESETS_DIR):
        names |= {entry for entry in os.listdir(routes.PRESETS_DIR) if _is_owned(entry, operation_id)}
    for name in names:
        BinaryMetadata.query.filter_by(context_type='preset', context_key=name).delete()
    for row in owned:
        db.session.delete(row)
    db.session.commit()
    for name in names:
        shutil.rmtree(os.path.join(routes.PRESETS_DIR, name), ignore_errors=True)
    return sorted(names)
