"""Pre-upgrade snapshots of a host's instance state, and per-instance restore.

Layout of one operation's snapshot, under RUNTIME_UPGRADES_DIR:

    <host_id>/<operation_id>/
        manifest.json                  inventory; `complete: true` once published
        inputs/                        materialize_upgrade_inputs output: verified
            instances/<id>/...         copies of each instance config tree (bytes,
            <shared tree key>/...      modes, mtimes, empty dirs) and shared trees
        instances/<id>/instance.json   the instance's original DB fields
        restore/<id>.json              restore swap journal (written by restore)

prepare_upgrade_snapshot builds all of it in `<operation_id>.staging/`, creates
the fallback presets, fsyncs, renames staging into place, re-verifies the
published copy and only then sets the operation row's snapshot_complete. Until
that commit everything it made is preparation-only: a failure removes the
staging/published directories and this operation's presets, and never touches
a live directory.

restore_instance stages a verified copy next to the live directory, journals
its swap intent, renames live -> backup and staged -> live, and verifies the
result. Rerunning it after a crash completes the swap from whichever side it
stopped on. Live data is never deleted before a verified replacement exists.

instance.json and the operation's inputs hold ZMQ passwords: never log them or
return them to a client.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import stat

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from ui import db, runtime_upgrade
from ui.models import InstanceStatus
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.runtime_upgrade import (
    _RENDERER_FIELDS,
    UpgradeInputsChanged,
    _copy_verified_tree,
    _tree_digests,
    classification_fingerprint,
    materialize_upgrade_inputs,
)
from ui.runtime_upgrade_presets import (  # noqa: F401 -- re-exported
    PRESET_PREFIX,
    delete_snapshot_presets,
    save_snapshot_presets,
    snapshot_preset_name,
)

DEFAULT_RUNTIME_UPGRADES_DIR = os.path.join('data', 'runtime-upgrades')
SNAPSHOT_SCHEMA_VERSION = 1
STAGING_SUFFIX = '.staging'
_OPERATION_ID = re.compile(r'^[0-9a-f]{32}$')


class SnapshotInvalid(RuntimeError):
    """A snapshot, or a copy made from it, does not match its manifest."""


class RestoreSwapError(RuntimeError):
    """The live/staged/backup directories are in a state the swap cannot resolve."""


# --- paths ---------------------------------------------------------------------

def runtime_upgrades_base():
    """The snapshot root from app config; a relative path is under the app root."""
    base = current_app.config.get('RUNTIME_UPGRADES_DIR') or DEFAULT_RUNTIME_UPGRADES_DIR
    if os.path.isabs(base):
        return base
    return os.path.join(os.path.dirname(current_app.root_path), base)


def _check_operation_id(operation_id):
    if not isinstance(operation_id, str) or not _OPERATION_ID.match(operation_id):
        raise ValueError('operation_id must be 32 lowercase hex characters')


def snapshot_dir(host_id, operation_id):
    _check_operation_id(operation_id)
    return os.path.join(runtime_upgrades_base(), str(int(host_id)), operation_id)


def snapshot_source_dir(host_id, operation_id):
    """The staging directory while preparing, else the published one."""
    published = snapshot_dir(host_id, operation_id)
    staging = published + STAGING_SUFFIX
    return staging if os.path.isdir(staging) else published


# --- durable filesystem helpers ------------------------------------------------------

def _rename(src, dst):
    os.rename(src, dst)


def _fsync_path(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_tree(root):
    for current, _dirs, files in os.walk(root, topdown=False):
        for filename in files:
            _fsync_path(os.path.join(current, filename))
        _fsync_path(current)


def _write_json_durable(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    _fsync_path(os.path.dirname(path))


def _read_json(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def _sha256_file(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _discard(path):
    if os.path.lexists(path):
        shutil.rmtree(path)


def tree_inventory(root):
    """(files, dirs): files maps POSIX relpath -> {sha256, mode}; dirs maps
    relpath ('.' for the root) -> mode. Empty when `root` does not exist."""
    files, dirs = {}, {}
    if not os.path.isdir(root):
        return files, dirs
    for current, _subdirs, filenames in os.walk(root):
        rel_dir = os.path.relpath(current, root).replace(os.sep, '/')
        dirs[rel_dir] = stat.S_IMODE(os.stat(current).st_mode)
        for filename in filenames:
            full_path = os.path.join(current, filename)
            rel_path = os.path.relpath(full_path, root).replace(os.sep, '/')
            files[rel_path] = {'sha256': _sha256_file(full_path),
                               'mode': stat.S_IMODE(os.stat(full_path).st_mode)}
    return files, dirs


def _tree_problems(root, entry):
    """Differences between `root` and a manifest instance entry, as text."""
    files, dirs = tree_inventory(root)
    problems = []
    for rel_path in sorted(set(files) | set(entry['files'])):
        have, want = files.get(rel_path), entry['files'].get(rel_path)
        if have is None:
            problems.append(f'{rel_path} is missing')
        elif want is None:
            problems.append(f'{rel_path} is unexpected')
        elif have['sha256'] != want['sha256']:
            problems.append(f'{rel_path} changed')
        elif have['mode'] != want['mode']:
            problems.append(f'{rel_path} mode {oct(have["mode"])} != {oct(want["mode"])}')
    for rel_dir in sorted(set(dirs) | set(entry['dirs'])):
        if dirs.get(rel_dir) != entry['dirs'].get(rel_dir):
            problems.append(f'directory {rel_dir} differs')
    return problems


# --- prepare ---------------------------------------------------------------------

def _write_instance_metadata(path, meta):
    _write_json_durable(path, meta)


def _instance_metadata(operation_id, host_inputs, captured):
    return {
        'schema': SNAPSHOT_SCHEMA_VERSION,
        'operation_id': operation_id,
        'instance_id': captured['instance_id'],
        'instance_name': captured['instance_name'],
        'original_runtime': host_inputs['runtime'],
        'original_status': captured['original_status'],
        'qlx_plugins': captured['qlx_plugins_raw'],
        'ld_preload_hooks': captured['ld_preload_hooks'],
        'lan_rate_enabled': captured['lan_rate_enabled'],
        'renderer': captured['renderer'],
    }


def _snapshot_instances(staging, operation_id, inputs):
    """Write each instance.json and inventory the staged tree against the capture."""
    entries = []
    for captured in sorted(inputs.get('instances') or [], key=lambda item: item['instance_id']):
        instance_id = captured['instance_id']
        tree = os.path.join(staging, 'inputs', 'instances', str(instance_id))
        os.makedirs(tree, exist_ok=True)
        files, dirs = tree_inventory(tree)
        digests = {rel: info['sha256'] for rel, info in files.items()}
        if digests != (captured.get('config_files') or {}):
            raise UpgradeInputsChanged(f'Staged copy of instance {instance_id} does not match the capture')
        meta_path = os.path.join(staging, 'instances', str(instance_id), 'instance.json')
        _write_instance_metadata(meta_path, _instance_metadata(operation_id, inputs['host'], captured))
        entries.append({
            'instance_id': instance_id,
            'instance_name': captured['instance_name'],
            'metadata_sha256': _sha256_file(meta_path),
            'files': files,
            'dirs': dirs,
        })
    return entries


def _manifest_problems(path, manifest, operation_id, host_id):
    problems = []
    if manifest.get('schema') != SNAPSHOT_SCHEMA_VERSION:
        problems.append('unknown manifest schema')
    if manifest.get('complete') is not True:
        problems.append('manifest is not complete')
    if manifest.get('operation_id') != operation_id:
        problems.append('manifest belongs to another operation')
    if host_id is not None and manifest.get('host_id') != host_id:
        problems.append('manifest belongs to another host')
    return problems


def _verify_published(path, operation_id, host_id):
    """Re-read the published manifest and verify every file it lists."""
    manifest = _read_json(os.path.join(path, 'manifest.json'))
    problems = _manifest_problems(path, manifest, operation_id, host_id)
    for key, digests in sorted((manifest.get('trees') or {}).items()):
        if _tree_digests(os.path.join(path, 'inputs', key)) != digests:
            problems.append(f'shared tree {key} differs')
    for entry in manifest.get('instances') or []:
        instance_id = entry['instance_id']
        tree = os.path.join(path, 'inputs', 'instances', str(instance_id))
        problems += [f'instance {instance_id}: {p}' for p in _tree_problems(tree, entry)]
        meta_path = os.path.join(path, 'instances', str(instance_id), 'instance.json')
        if not os.path.isfile(meta_path) or _sha256_file(meta_path) != entry['metadata_sha256']:
            problems.append(f'instance {instance_id}: instance.json differs')
    if problems:
        raise SnapshotInvalid('Published snapshot failed verification: ' + '; '.join(problems))
    return manifest


def prepare_upgrade_snapshot(host, operation_id, inputs):
    """Publish a complete, verified snapshot of every instance and return its path.

    `operation_id` names an existing HostRuntimeUpgradeOperation for `host`
    (the orchestrator creates and reserves it). `inputs` is the validated
    capture; its fingerprint must match the row's when the row has one.
    Raises on any failure, after removing only what this call created.
    """
    _check_operation_id(operation_id)
    operation = db.session.get(HostRuntimeUpgradeOperation, operation_id)
    if operation is None or operation.host_id != host.id:
        raise LookupError(f'No runtime upgrade operation {operation_id} for host {host.id}')
    if operation.fingerprint and classification_fingerprint(inputs) != operation.fingerprint:
        raise UpgradeInputsChanged('Inputs do not match the operation fingerprint')

    published = snapshot_dir(host.id, operation_id)
    if operation.snapshot_complete and os.path.isdir(published):
        _verify_published(published, operation_id, host.id)
        return published

    staging = published + STAGING_SUFFIX
    # Leftovers of an earlier attempt at this operation are preparation-only.
    _discard(staging)
    _discard(published)
    delete_snapshot_presets(operation_id)
    try:
        os.makedirs(os.path.dirname(staging), exist_ok=True)
        materialize_upgrade_inputs(host, inputs, os.path.join(staging, 'inputs'))
        instances = _snapshot_instances(staging, operation_id, inputs)
        presets = save_snapshot_presets(host, operation_id)
        manifest = {
            'schema': SNAPSHOT_SCHEMA_VERSION,
            'complete': True,
            'operation_id': operation_id,
            'host_id': host.id,
            'host_name': host.name,
            'original_runtime': inputs['host']['runtime'],
            'fingerprint': classification_fingerprint(inputs),
            'created_at': datetime.datetime.utcnow().isoformat(),
            'presets': presets,
            'trees': inputs.get('trees') or {},
            'instances': instances,
        }
        _write_json_durable(os.path.join(staging, 'manifest.json'), manifest)
        _fsync_tree(staging)
        _rename(staging, published)
        _fsync_path(os.path.dirname(published))
        _verify_published(published, operation_id, host.id)
        operation.snapshot_path = published
        operation.snapshot_complete = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        _cleanup_preparation(operation_id, staging, published)
        raise
    return published


def _cleanup_preparation(operation_id, staging, published):
    for path in (staging, published):
        try:
            _discard(path)
        except OSError:
            current_app.logger.exception('Could not remove upgrade snapshot directory %s', path)
    try:
        delete_snapshot_presets(operation_id)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Could not remove fallback presets of operation %s', operation_id)


# --- restore ---------------------------------------------------------------------

def _safe_error(exc):
    """Error text for results and logs; SQLAlchemy messages can embed bound
    parameters (ZMQ passwords), so only the driver message is kept."""
    if isinstance(exc, SQLAlchemyError):
        return f'{type(exc).__name__}: {getattr(exc, "orig", None) or "database error"}'
    return str(exc) or type(exc).__name__


def _write_intent(path, intent):
    _write_json_durable(path, intent)


def _load_snapshot(instance, snapshot_root):
    manifest = _read_json(os.path.join(snapshot_root, 'manifest.json'))
    problems = _manifest_problems(snapshot_root, manifest, manifest.get('operation_id'),
                                  instance.host_id)
    if problems:
        raise SnapshotInvalid('; '.join(problems))
    _check_operation_id(manifest['operation_id'])
    entry = next((item for item in manifest.get('instances') or []
                  if item['instance_id'] == instance.id), None)
    if entry is None:
        raise SnapshotInvalid(f'Instance {instance.id} is not in the snapshot')
    meta_path = os.path.join(snapshot_root, 'instances', str(instance.id), 'instance.json')
    if _sha256_file(meta_path) != entry['metadata_sha256']:
        raise SnapshotInvalid('instance.json does not match the manifest')
    return manifest, entry, _read_json(meta_path)


def _stage(source, staged, entry, instance_id):
    _discard(staged)
    problems = []
    digests = {rel: info['sha256'] for rel, info in entry['files'].items()}
    try:
        _copy_verified_tree(f'snapshot of instance {instance_id}', source, digests, staged, problems)
        problems += _tree_problems(staged, entry)
        if problems:
            raise SnapshotInvalid('; '.join(problems))
        _fsync_tree(staged)
    except Exception:
        _discard(staged)
        raise


def _complete_swap(live, staged, backup, entry, source, instance_id):
    """Idempotently move the staged restore into place, keeping live as backup."""
    if os.path.isdir(staged):
        if _tree_problems(staged, entry):
            if os.path.lexists(live) and not os.path.lexists(backup):
                raise RestoreSwapError('Staged restore is damaged; live data left in place')
            _stage(source, staged, entry, instance_id)
        if os.path.lexists(live):
            if os.path.lexists(backup):
                raise RestoreSwapError(f'Both {live} and backup {backup} exist; refusing to swap')
            _rename(live, backup)
        try:
            _rename(staged, live)
        except Exception:
            if os.path.lexists(backup) and not os.path.lexists(live):
                _rename(backup, live)
            raise
        _fsync_path(os.path.dirname(live))
    elif not os.path.isdir(live):
        raise RestoreSwapError(f'Neither {live} nor a staged restore exists')
    problems = _tree_problems(live, entry)
    if problems:
        raise SnapshotInvalid('Restored directory does not match the snapshot: ' + '; '.join(problems))


def _restore_tree(instance, snapshot_root, manifest, entry, result):
    operation_id = manifest['operation_id']
    live = runtime_upgrade._instance_config_dir(instance.host.name, instance.id)
    parent = os.path.dirname(live)
    staged = os.path.join(parent, f'.upgrade-restore-{instance.id}-{operation_id}')
    source = os.path.join(snapshot_root, 'inputs', 'instances', str(instance.id))
    intent_path = os.path.join(snapshot_root, 'restore', f'{instance.id}.json')
    intent = _read_json(intent_path) if os.path.exists(intent_path) else None

    if intent is None or intent['state'] in ('swapped', 'complete'):
        if os.path.isdir(live) and not _tree_problems(live, entry):
            return intent, intent_path
        intent = {
            'instance_id': instance.id,
            'attempt': (intent['attempt'] + 1) if intent else 1,
            'live': live,
            'staged': staged,
            'state': 'staging',
        }
        intent['backup'] = os.path.join(
            parent, f'.upgrade-backup-{instance.id}-{operation_id}-{intent["attempt"]}')
        _write_intent(intent_path, intent)

    if intent['state'] == 'staging':
        result['phase'] = 'stage'
        _stage(source, staged, entry, instance.id)
        intent['state'] = 'swapping'
        _write_intent(intent_path, intent)

    result['phase'] = 'swap'
    _complete_swap(live, staged, intent['backup'], entry, source, instance.id)
    intent['state'] = 'swapped'
    _write_intent(intent_path, intent)
    return intent, intent_path


def _restore_db_fields(instance, meta):
    instance.qlx_plugins = meta['qlx_plugins']
    instance.ld_preload_hooks = meta['ld_preload_hooks']
    instance.lan_rate_enabled = bool(meta['lan_rate_enabled'])
    for field in _RENDERER_FIELDS:
        if field in meta['renderer']:
            setattr(instance, field, meta['renderer'][field])


def restore_instance(instance, snapshot_root, *, service_state=None):
    """Restore one instance's local config tree and DB fields from a snapshot.

    Never raises: returns {instance_id, ok, phase, error, status_verified}, so
    the caller carries on with later instances. `status` is left alone unless
    `service_state(instance)` is given; it must return the InstanceStatus the
    caller verified on the host, never one read from the snapshot. The
    snapshot and any swap backup are kept on failure; on success the backup
    (the pre-restore tree) is removed.
    """
    result = {'instance_id': instance.id, 'ok': False, 'phase': 'validate',
              'error': None, 'status_verified': False}
    try:
        manifest, entry, meta = _load_snapshot(instance, snapshot_root)
        intent, intent_path = _restore_tree(instance, snapshot_root, manifest, entry, result)

        result['phase'] = 'database'
        _restore_db_fields(instance, meta)
        db.session.commit()

        if service_state is not None:
            result['phase'] = 'verify_service'
            status = service_state(instance)
            if not isinstance(status, InstanceStatus):
                raise TypeError('service_state must return an InstanceStatus')
            instance.status = status
            db.session.commit()
            result['status_verified'] = True

        if intent is not None and intent['state'] != 'complete':
            result['phase'] = 'cleanup'
            _discard(intent['backup'])
            intent['state'] = 'complete'
            _write_intent(intent_path, intent)
        result.update(ok=True, phase='complete')
    except Exception as exc:  # reported per instance; the caller continues
        db.session.rollback()
        result['error'] = _safe_error(exc)
        current_app.logger.error('Restore of instance %s failed in %s: %s',
                                 instance.id, result['phase'], result['error'])
    return result
