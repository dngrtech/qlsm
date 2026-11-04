"""The one-click minqlx -> minqlxtended host upgrade: eligibility, the
per-instance compatibility dry-run, and the captured confirmation inputs."""
import hashlib
import json
import os
import re

from ui.runtime import MINQLX, host_runtime, normalize_runtime, runtime_paths

UPGRADE_TARGET_RUNTIME = 'minqlxtended'

_MIN_UBUNTU = (24, 4)
_OS_DISPLAY = {'debian': 'Debian', 'ubuntu': 'Ubuntu'}


def _result(visible, enabled, reason=None):
    return {'visible': visible, 'enabled': enabled, 'reason': reason}


def _disabled(reason):
    return _result(True, False, reason)


def _parse_version(value):
    """'24.04' -> (24, 4); None if not a dotted numeric version."""
    if not isinstance(value, str) or not re.fullmatch(r'\d+(\.\d+)*', value.strip()):
        return None
    return tuple(int(part) for part in value.strip().split('.'))


def _enum_value(value):
    return getattr(value, 'value', value)


def upgrade_eligibility(host, *, assume_status=None):
    """Decide whether the upgrade action is shown and enabled for a host.

    Checks run in order (runtime, status, OS, instances); only the first
    failure is reported. ``assume_status`` replaces ``host.status`` for the
    status check only, for callers that hold the host in a transitional state
    under their own reservation.
    """
    from ui.models import HostStatus, InstanceStatus

    if normalize_runtime(host.runtime) != MINQLX:
        return _result(False, False)

    status = assume_status if assume_status is not None else host.status
    if status != HostStatus.ACTIVE:
        current = _enum_value(status)
        label = str(current).upper() if current else 'UNKNOWN'
        return _disabled(f'Host must be ACTIVE to upgrade; current status is {label}')

    os_type = (host.os_type or '').strip().lower()
    version = _parse_version(host.os_version)
    if not os_type or version is None:
        return _disabled('minqlxtended requires Ubuntu 24.04 or newer; OS version unknown')
    if os_type != 'ubuntu' or version < _MIN_UBUNTU:
        display = _OS_DISPLAY.get(os_type, host.os_type)
        return _disabled(
            f'minqlxtended requires Ubuntu 24.04 or newer; this host runs {display} {host.os_version}'
        )

    allowed = (InstanceStatus.RUNNING, InstanceStatus.STOPPED)
    for instance in host.instances:
        if instance.status not in allowed:
            label = str(_enum_value(instance.status)).upper()
            return _disabled(
                f'Instance {instance.name} is {label}; all instances must be RUNNING or STOPPED'
            )

    return _result(True, True)


# ---------------------------------------------------------------------------
# Per-instance compatibility dry-run, confirmation fingerprint, and the
# immutable operation-owned copies of everything the conversion consumes.
#
# The dry-run (classify_instance) is what the dialog shows. The capture
# (capture_upgrade_inputs) is everything the operator's confirmation depends
# on, as a JSON-serializable dict of DIGESTS -- never file bodies -- so it can
# be persisted with the operation. The fingerprint is its content identity: a
# worker recaptures under its locks and compares, so an edit that keeps the
# same compatibility verdict (or touches a config, hook, requirement or target
# replacement file) still invalidates the approval before any downtime.
# materialize_upgrade_inputs then copies exactly the captured bytes into an
# operation-owned directory, so conversion never reads mutable live pools.
# ---------------------------------------------------------------------------
#
# ui.models imports this module, and preset_compat/preset_support/plugin_pool
# reach back into ui.models via ui.database, so those are imported inside the
# functions that use them rather than at module load.

# Working-directory relative, like every other configs/<host>/<id> lookup.
# Resolved at call time so tests can point it at tmp_path.
CONFIGS_BASE = 'configs'

CAPTURE_SCHEMA_VERSION = 1

# Model fields the config/service renderer reads (ansible_instance_mgmt
# _build_qlds_args_string, _redis_args, deploy/apply-config extravars).
# logs, timestamps and runtime_invocation_id are deliberately absent: they
# change without the operator changing anything that conversion consumes.
_RENDERER_FIELDS = (
    'name', 'port', 'hostname', 'config', 'cpu_affinity', 'redis_db',
    'zmq_rcon_port', 'zmq_rcon_password', 'zmq_stats_port', 'zmq_stats_password',
)

_RUNTIME_IDENTITY_FIELDS = (
    'runtime', 'git_repo', 'git_version', 'plugins_dirname', 'shared_dir',
    'engine_so', 'launch_script',
)


class UpgradeInputsChanged(RuntimeError):
    """Live files no longer match the captured upgrade inputs."""


def _instance_config_dir(host_name, instance_id):
    return os.path.join(CONFIGS_BASE, host_name, str(instance_id))


def _checked_plugins(qlx_plugins):
    """`QLInstance.qlx_plugins` ('a, b') -> ['a.py', 'b.py']; None for NULL/''."""
    if not qlx_plugins:
        return None
    return [f'{name.strip()}.py' for name in qlx_plugins.split(',') if name.strip()]


def instance_plugin_snapshot(instance):
    """The instance's plugins in the shape `apply_compatibility` reads.

    Every `.py` under configs/<host>/<id>/scripts/, read as UTF-8. A file that
    is not valid UTF-8 is skipped, as `_read_preset_scripts` does; it still
    counts toward the capture's byte digests.
    """
    scripts_dir = os.path.join(_instance_config_dir(instance.host.name, instance.id), 'scripts')
    scripts = {}
    for root, _dirs, filenames in os.walk(scripts_dir):
        for filename in filenames:
            if not filename.lower().endswith('.py'):
                continue
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, scripts_dir).replace(os.sep, '/')
            try:
                with open(full_path, 'r', encoding='utf-8') as handle:
                    scripts[rel_path] = handle.read()
            except (OSError, ValueError):
                continue
    return {'scripts': scripts, 'checked_plugins': _checked_plugins(instance.qlx_plugins)}


def classify_instance(instance):
    """The dialog rows for one instance: `apply_compatibility`'s verdicts for
    loading its current scripts onto the upgrade target."""
    from ui import preset_compat

    result = preset_compat.apply_compatibility(
        instance_plugin_snapshot(instance), MINQLX, UPGRADE_TARGET_RUNTIME)
    compat = result['compatibility']
    return {
        'instance_id': instance.id,
        'instance_name': instance.name,
        'stripped': compat['stripped'],
        'replacements': compat['replacements'],
        'auto_accepted': compat['auto_accepted'],
        'checked_plugins': result['checked_plugins'],
    }


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _tree_digests(root):
    """POSIX relpath -> sha256 of the raw bytes of every file under `root`.

    A missing root is {}; an unreadable file raises, because silently dropping
    it would let a change to it go unnoticed.
    """
    digests = {}
    if not os.path.isdir(root):
        return digests
    for current, _dirs, filenames in os.walk(root):
        for filename in filenames:
            full_path = os.path.join(current, filename)
            rel_path = os.path.relpath(full_path, root).replace(os.sep, '/')
            with open(full_path, 'rb') as handle:
                digests[rel_path] = _sha256_bytes(handle.read())
    return digests


def _shared_tree_roots():
    """Every non-instance directory whose bytes the conversion depends on.

    Keys are stable names used in the capture and as subdirectories of a
    materialized input directory.
    """
    from ui import plugin_pool, preset_compat
    from ui.preset_support import default_preset_name_for_runtime

    assets = preset_compat.ASSETS_DIR
    source_paths = runtime_paths(MINQLX)
    target_paths = runtime_paths(UPGRADE_TARGET_RUNTIME)
    presets = preset_compat.BUILTIN_PRESETS_DIR
    return {
        # Source stock comparison: what "untouched stock plugin" is judged by.
        'source_default_preset_scripts': os.path.join(
            presets, default_preset_name_for_runtime(MINQLX), 'scripts'),
        'source_baseline': os.path.join(assets, source_paths['asset_plugins_dir']),
        # Target replacements, baseline manifest, and the pools staged to the host.
        'target_default_preset_scripts': os.path.join(
            presets, default_preset_name_for_runtime(UPGRADE_TARGET_RUNTIME), 'scripts'),
        'target_baseline': os.path.join(assets, target_paths['asset_plugins_dir']),
        'target_builtin_pool': plugin_pool.builtin_pool_dir(UPGRADE_TARGET_RUNTIME),
        'target_operator_pool': plugin_pool.operator_pool_dir(UPGRADE_TARGET_RUNTIME),
        'system_hooks': os.path.join(assets, 'system-hooks'),
    }


def _runtime_identity(runtime):
    paths = runtime_paths(runtime)
    return {field: paths[field] for field in _RUNTIME_IDENTITY_FIELDS}


def _capture_instance(instance, target_scripts):
    classification = classify_instance(instance)
    replacements = {}
    for path, text in classification['replacements'].items():
        # Prefer the byte digest of the file the materialized copy will hold;
        # fall back to the text the classifier read.
        replacements[path] = target_scripts.get(path) or _sha256_bytes(text.encode('utf-8'))
    renderer = {field: getattr(instance, field, None) for field in _RENDERER_FIELDS}
    return {
        'instance_id': instance.id,
        'instance_name': instance.name,
        'original_status': _enum_value(instance.status),
        'config_files': _tree_digests(_instance_config_dir(instance.host.name, instance.id)),
        # Raw preserves NULL versus '', which the renderer and the dialog treat differently.
        'qlx_plugins_raw': instance.qlx_plugins,
        'qlx_plugins_effective': _checked_plugins(instance.qlx_plugins),
        'ld_preload_hooks': instance.ld_preload_hooks,
        'lan_rate_enabled': bool(instance.lan_rate_enabled),
        'renderer': renderer,
        'classification': {
            'stripped': classification['stripped'],
            'replacements': replacements,
            'auto_accepted': classification['auto_accepted'],
            'checked_plugins': classification['checked_plugins'],
        },
    }


def capture_upgrade_inputs(host):
    """Everything an upgrade confirmation depends on, as JSON-serializable digests.

    Holds no file bodies and no timestamps or logs. NOTE: `renderer` carries the
    instances' ZMQ passwords in plain text (the conversion re-renders from it),
    so the result must be stored server-side only and never returned by an API.
    """
    trees = {key: _tree_digests(root) for key, root in _shared_tree_roots().items()}
    target = UPGRADE_TARGET_RUNTIME
    instances = sorted(host.instances, key=lambda inst: inst.id)
    return {
        'schema': CAPTURE_SCHEMA_VERSION,
        'host': {
            'id': host.id,
            'name': host.name,
            'runtime': host.runtime,
            'lan_rate_uses_hook': bool(host.lan_rate_uses_hook),
        },
        'source_runtime': _runtime_identity(host_runtime(host)),
        'target_runtime': {
            **_runtime_identity(target),
            'excluded_system_hooks': sorted(runtime_paths(target)['excluded_system_hooks']),
            'builtin_pool': trees['target_builtin_pool'],
            'core_requirements': trees['target_builtin_pool'].get('requirements.txt'),
        },
        'trees': trees,
        'instances': [
            _capture_instance(inst, trees['target_default_preset_scripts'])
            for inst in instances
        ],
    }


def _canonical_inputs(inputs):
    """A copy with every path/instance collection in a fixed order.

    Round-tripped through JSON first so enum/int-key/tuple differences between
    a fresh capture and one loaded back from the database cannot matter.
    Order-significant raw strings (qlx_plugins, ld_preload_hooks) are kept as is.
    """
    data = json.loads(json.dumps(inputs))
    data['instances'] = sorted(data.get('instances') or [], key=lambda inst: inst['instance_id'])
    for inst in data['instances']:
        classification = inst.get('classification') or {}
        classification['stripped'] = sorted(
            classification.get('stripped') or [], key=lambda row: row['path'])
        classification['auto_accepted'] = sorted(classification.get('auto_accepted') or [])
    target = data.get('target_runtime') or {}
    if 'excluded_system_hooks' in target:
        target['excluded_system_hooks'] = sorted(target['excluded_system_hooks'])
    return data


def classification_fingerprint(inputs):
    """SHA-256 of the canonical UTF-8 JSON of a capture."""
    canonical = json.dumps(_canonical_inputs(inputs), sort_keys=True,
                           separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _safe_join(base, rel_path):
    parts = rel_path.split('/')
    if os.path.isabs(rel_path) or any(part in ('', '.', '..') for part in parts):
        raise UpgradeInputsChanged(f'Unsafe captured path: {rel_path!r}')
    return os.path.join(base, *parts)


def _copy_verified_tree(label, source_root, captured, dest_root, problems):
    live = set(_tree_digests(source_root))
    for rel_path in sorted(live - set(captured)):
        problems.append(f'{label}: {rel_path} was added')
    for rel_path, digest in sorted(captured.items()):
        try:
            with open(_safe_join(source_root, rel_path), 'rb') as handle:
                data = handle.read()
        except OSError:
            problems.append(f'{label}: {rel_path} is missing')
            continue
        # Hash the bytes we hold and write those same bytes, so the copy is
        # exactly what was verified even if the live file changes afterwards.
        if _sha256_bytes(data) != digest:
            problems.append(f'{label}: {rel_path} changed')
            continue
        target = _safe_join(dest_root, rel_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as handle:
            handle.write(data)


def materialize_upgrade_inputs(host, inputs, dest_dir):
    """Copy the captured bytes into `dest_dir` as operation-owned inputs.

    Layout: `instances/<id>/...` (each instance's whole config tree) and one
    directory per shared tree key (`target_default_preset_scripts/`,
    `target_builtin_pool/`, `target_operator_pool/`, ...). Every file is
    re-hashed as it is copied; any changed, missing or added file raises
    UpgradeInputsChanged after all trees are checked. `dest_dir` must be new or
    empty; on failure the caller owns removing whatever was written there.
    """
    if os.path.exists(dest_dir) and (not os.path.isdir(dest_dir) or os.listdir(dest_dir)):
        raise ValueError(f'Destination {dest_dir} must be new or empty')
    captured_host = inputs.get('host') or {}
    if captured_host.get('id') != host.id or captured_host.get('name') != host.name:
        raise UpgradeInputsChanged('Captured inputs belong to a different host')
    os.makedirs(dest_dir, exist_ok=True)

    problems = []
    roots = _shared_tree_roots()
    for key, captured in sorted((inputs.get('trees') or {}).items()):
        if key not in roots:
            raise UpgradeInputsChanged(f'Unknown captured tree {key!r}')
        _copy_verified_tree(key, roots[key], captured, os.path.join(dest_dir, key), problems)
    for inst in inputs.get('instances') or []:
        instance_id = inst['instance_id']
        _copy_verified_tree(
            f'instance {instance_id}',
            _instance_config_dir(host.name, instance_id),
            inst.get('config_files') or {},
            os.path.join(dest_dir, 'instances', str(instance_id)),
            problems,
        )
    if problems:
        raise UpgradeInputsChanged('Upgrade inputs changed: ' + '; '.join(problems))
