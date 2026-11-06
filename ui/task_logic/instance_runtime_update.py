"""Entry points the runtime-upgrade orchestrator calls on a host and on its
existing instances (upgrade and rollback).

    install_runtime_on_host(host_id, *, operation_id, fencing_token, immutable_inputs)
        install_runtime.yml: additive build prerequisites, the patched
        minqlxtended build, the target common pool from captured inputs, and
        one isolated venv per instance. Never setup_host.yml, never global pip.

    configure_existing_instance(instance_id, runtime, immutable_inputs, dependency_path,
                                *, operation_id, fencing_token, restore_from_operation=None)
        update_instance_runtime.yml: configure an existing, stopped instance
        for `runtime` from immutable inputs, without starting it. Never the
        creation-only deploy path. With `restore_from_operation` it first
        restores that operation's remote inventory (rollback).

    finalize_runtime_operation(host_id, *, operation_id, fencing_token)
        Mark a terminal operation finished in the host's token record so the
        next operation can take the host's runtime lock.

Each returns {'ok': bool, 'error': str | None, 'details': dict} and never
raises. All three take the host's remote runtime-operation lock and are
fenced by (operation_id, fencing_token): a stale token, another play still
running, or another non-terminal operation owning the host is refused before
any side effect.
"""
import logging
import os
import re
import shutil
import tarfile
import tempfile

from ui import db
from ui.models import Host, QLInstance
from ui.models_runtime_upgrade import TERMINAL_STATES, HostRuntimeUpgradeOperation
from ui.runtime import MINQLX, MINQLXTENDED, host_runtime, runtime_extravars, runtime_paths
from .ansible_instance_mgmt import _build_ld_preload_paths, _build_qlds_args_string
from .ansible_runner import _run_host_ansible_playbook

log = logging.getLogger(__name__)

_OPERATION_ID = re.compile(r'^[0-9a-f]{32}$')
RUNTIME_DEPS_ROOT = '/home/ql/runtime-deps'
_DEPS_PATH = re.compile(r'^/home/ql/runtime-deps/minqlxtended/[0-9a-f]{32}/[0-9]+$')
DEFAULT_SYSTEM_HOOKS_DIR = os.path.join('ql-assets', 'data', 'system-hooks')

# Runtime artifacts that ui.runtime does not name: the Python archive (zip, or
# the minqlx/ package) and optional extras. The engine .so and launcher come
# from runtime_paths() so a rename there can't leave this list stale.
_RUNTIME_ARCHIVE_AND_EXTRAS = {
    MINQLXTENDED: ('minqlxtended.zip', []),
    MINQLX: ('minqlx', ['minqlx-cmd', 'quake_live.sh']),
}


def _runtime_artifacts(runtime):
    """(required, optional) artifact names in the runtime's shared dir."""
    paths = runtime_paths(runtime)
    archive, optional = _RUNTIME_ARCHIVE_AND_EXTRAS[runtime]
    return [paths['engine_so'], archive, paths['launch_script']], list(optional)
_CONFIG_SUFFIXES = ('.cfg', '.txt', '.ent')


def _result(ok, error=None, **details):
    return {'ok': ok, 'error': error, 'details': details}


def dependency_path(operation_id, instance_id):
    """Where install_runtime.yml puts an instance's venv for an operation."""
    return f'{RUNTIME_DEPS_ROOT}/minqlxtended/{operation_id}/{int(instance_id)}'


def _check_identity(operation_id, fencing_token):
    if not isinstance(operation_id, str) or not _OPERATION_ID.match(operation_id):
        raise ValueError('operation_id must be 32 lowercase hex characters')
    if isinstance(fencing_token, bool) or not isinstance(fencing_token, int) or fencing_token < 0:
        raise ValueError('fencing_token must be a non-negative integer')


def _terminal_operation_ids(host_id):
    rows = (HostRuntimeUpgradeOperation.query
            .filter(HostRuntimeUpgradeOperation.host_id == host_id,
                    HostRuntimeUpgradeOperation.state.in_(TERMINAL_STATES))
            .order_by(HostRuntimeUpgradeOperation.id).all())
    return [row.id for row in rows]


def _run_playbook(host, playbook, extravars):
    """(ok, error text) from _run_host_ansible_playbook, which returns
    (ok, stdout, stderr) normally but (None, error) on its early exits."""
    outcome = _run_host_ansible_playbook(host, playbook, extravars=extravars)
    if len(outcome) == 2:
        return False, outcome[1] or 'ansible-playbook could not run'
    ok, stdout, stderr = outcome
    return bool(ok), None if ok else _failure_text(stdout, stderr)


def _failure_text(stdout, stderr):
    """The failing task lines from ansible-playbook stdout (where Ansible
    reports them), else the tail of stderr/stdout."""
    lines = (stdout or '').splitlines()
    failures = [line.strip() for line in lines
                if line.lstrip().startswith(('fatal:', 'failed:')) or 'FAILED!' in line]
    text = '\n'.join(failures) or (stderr or '').strip() or (stdout or '').strip()
    return text[-2000:] if text else 'ansible-playbook failed'


# --- install ---------------------------------------------------------------------

def install_inputs_from_materialized(inputs_dir, instance_ids):
    """install_runtime_on_host inputs from a materialize_upgrade_inputs()
    directory (Task 3 snapshot `inputs/`): the captured target built-in and
    operator pools, the core requirements inside the built-in pool, and each
    instance's captured scripts/requirements.txt."""
    builtin = os.path.join(inputs_dir, 'target_builtin_pool')
    operator = os.path.join(inputs_dir, 'target_operator_pool')
    core = os.path.join(builtin, 'requirements.txt')
    instances = {}
    for instance_id in instance_ids:
        req = os.path.join(inputs_dir, 'instances', str(int(instance_id)), 'scripts', 'requirements.txt')
        instances[int(instance_id)] = {'requirements': req if os.path.isfile(req) else None}
    return {
        'core_requirements': core if os.path.isfile(core) else None,
        'builtin_pool_dir': builtin,
        'operator_pool_dir': operator if os.path.isdir(operator) else None,
        'instances': instances,
    }


def install_runtime_on_host(host_id, *, operation_id, fencing_token, immutable_inputs):
    """Install minqlxtended beside minqlx and build one venv per instance.

    immutable_inputs: {'core_requirements': path|None, 'builtin_pool_dir': path,
    'operator_pool_dir': path|None, 'instances': {instance_id: {'requirements': path|None}}}
    (see install_inputs_from_materialized). An empty `instances` builds only
    the runtime and common assets. details['dependency_paths'] maps each
    instance id to its venv when the play succeeded.
    """
    empty_pool = None
    try:
        _check_identity(operation_id, fencing_token)
        host = db.session.get(Host, host_id)
        if host is None:
            return _result(False, f'Host {host_id} not found', dependency_paths={})
        instances = immutable_inputs.get('instances') or {}
        runtime_instances = [
            {'id': int(instance_id),
             'requirements_src': os.path.abspath(spec['requirements']) if spec.get('requirements') else ''}
            for instance_id, spec in sorted(instances.items(), key=lambda kv: int(kv[0]))
        ]
        target = runtime_paths(MINQLXTENDED)
        extravars = {
            # The target runtime identity comes from ui.runtime, the single
            # source of truth, so the play can't build a stale pin.
            'minqlxtended_git_repo': target['git_repo'],
            'minqlxtended_git_version': target['git_version'],
            'minqlxtended_shared_dir': target['shared_dir'],
            'runtime_plugins_dirname': target['plugins_dirname'],
            'operation_id': operation_id,
            'fencing_token': fencing_token,
            'terminal_operation_ids': _terminal_operation_ids(host.id),
            'core_requirements_src': os.path.abspath(immutable_inputs['core_requirements'])
            if immutable_inputs.get('core_requirements') else '',
            'common_plugins_builtin_src': os.path.abspath(immutable_inputs['builtin_pool_dir']),
            'runtime_instances': runtime_instances,
        }
        operator_pool = immutable_inputs.get('operator_pool_dir')
        if not operator_pool:
            # Nothing captured: an empty dir, so sync_common_plugins.yml never
            # falls back to the live data/shared-plugins/<runtime>.
            operator_pool = empty_pool = tempfile.mkdtemp(prefix='qlsm-empty-operator-pool-')
        extravars['common_plugins_operator_src'] = os.path.abspath(operator_pool)
        ok, error = _run_playbook(host, 'install_runtime.yml', extravars)
        if not ok:
            return _result(False, error, dependency_paths={})
        return _result(True, dependency_paths={
            item['id']: dependency_path(operation_id, item['id']) for item in runtime_instances})
    except Exception as exc:  # never raise into the orchestrator
        log.exception('install_runtime_on_host failed for host %s', host_id)
        return _result(False, f'{type(exc).__name__}: {exc}', dependency_paths={})
    finally:
        if empty_pool:
            shutil.rmtree(empty_pool, ignore_errors=True)


# --- configure an existing instance -------------------------------------------------

def _add_file(tar, source, arcname):
    if os.path.islink(source) or not os.path.isfile(source):
        return
    info = tar.gettarinfo(source, arcname=arcname)
    info.uid = info.gid = 0
    info.uname = info.gname = 'root'
    with open(source, 'rb') as handle:
        tar.addfile(info, handle)


def _walk_files(root):
    for current, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(current, name)
            yield path, os.path.relpath(path, root).replace(os.sep, '/')


def _build_stage_archive(config_dir, system_hooks_dir, plugins_dirname, dest_dir):
    """A .tar.gz laid out relative to /home/ql/qlds-<port>/ holding exactly
    the managed files, with the same selection the existing sync playbooks
    use: cfg/txt/ent under baseq3/ (scripts/ and factories/ excluded), every
    file of scripts/ into the runtime plugin dir, factories/ into
    baseq3/scripts/, user-hooks/*.so and built-in system-hooks/*.so."""
    archive = os.path.join(dest_dir, 'managed.tar.gz')
    with tarfile.open(archive, 'w:gz') as tar:
        for path, rel in _walk_files(config_dir):
            top = rel.split('/', 1)[0]
            if '/' in rel and top == 'scripts':
                _add_file(tar, path, f'{plugins_dirname}/{rel.split("/", 1)[1]}')
            elif '/' in rel and top == 'factories':
                _add_file(tar, path, f'baseq3/scripts/{rel.split("/", 1)[1]}')
            elif '/' in rel and top == 'user-hooks':
                if rel.endswith('.so') and rel.count('/') == 1:
                    _add_file(tar, path, rel)
            elif rel.endswith(_CONFIG_SUFFIXES):
                _add_file(tar, path, f'baseq3/{rel}')
        if system_hooks_dir and os.path.isdir(system_hooks_dir):
            for name in sorted(os.listdir(system_hooks_dir)):
                if name.endswith('.so'):
                    _add_file(tar, os.path.join(system_hooks_dir, name), f'system-hooks/{name}')
    return archive


def _validate_dependency_path(runtime, value):
    if not value:
        return ''
    if runtime != MINQLXTENDED:
        raise ValueError('A dependency venv is only used by minqlxtended')
    if not isinstance(value, str) or not _DEPS_PATH.match(value):
        raise ValueError(f'Dependency path {value!r} is not an operation venv under {RUNTIME_DEPS_ROOT}')
    return value


def _local_manifest_path(host_id, operation_id, instance_id):
    from ui.runtime_upgrade_snapshot import snapshot_dir

    path = os.path.join(snapshot_dir(host_id, operation_id), 'remote', f'{int(instance_id)}.json')
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    return path


def _reraise_stale(exc):
    """A fenced commit refused by a takeover must reach the orchestrator as is."""
    from ui.task_logic.host_runtime_upgrade_state import StaleExecution

    if isinstance(exc, StaleExecution):
        raise exc


def configure_existing_instance(instance_id, runtime, immutable_inputs, dependency_path,
                                *, operation_id, fencing_token, restore_from_operation=None,
                                commit=None):
    """Configure existing instance `instance_id` for `runtime` without starting it.

    The host row must already carry `runtime` (the orchestrator commits the
    target runtime before upgrading and the original runtime before rolling
    back), because the service renderer reads it.

    Forward: immutable_inputs = {'config_dir': the instance's converted config
    tree, 'system_hooks_dir': optional, defaults to ql-assets/data/system-hooks}.
    dependency_path: the instance's venv from install_runtime_on_host, or None
    for the host's system Python (always None for minqlx). On success it is
    persisted as QLInstance.python_deps_path.

    Rollback (restore_from_operation=<operation id>): an exact inventory
    restore only -- backed-up files (including the original systemd unit) are
    put back and files the forward run created are removed. Nothing is
    re-copied from the shared runtime dir. immutable_inputs is not used and
    dependency_path must be None; python_deps_path is cleared on success.

    commit: how the DB write is committed. The orchestrator passes its
    Execution.commit, so a superseded executor's write is rolled back and its
    StaleExecution propagates (it is never turned into a failure result).
    Defaults to a plain session commit for standalone use.
    """
    commit = commit or db.session.commit
    stage_dir = None
    try:
        _check_identity(operation_id, fencing_token)
        if restore_from_operation is not None and not _OPERATION_ID.match(str(restore_from_operation)):
            raise ValueError('restore_from_operation must be 32 lowercase hex characters')
        instance = db.session.get(QLInstance, instance_id)
        if instance is None or instance.host is None:
            return _result(False, f'Instance {instance_id} not found')
        host = instance.host
        if runtime not in _RUNTIME_ARCHIVE_AND_EXTRAS:
            return _result(False, f'Unknown runtime {runtime!r}')
        if host_runtime(host) != runtime:
            return _result(False, f'Host {host.name} runtime is {host_runtime(host)}, not {runtime}; '
                                  'commit the runtime before configuring its instances')

        if restore_from_operation:
            if dependency_path:
                return _result(False, 'A rollback restores the original environment; '
                                      'dependency_path must be None')
            extravars = {
                'operation_id': operation_id,
                'fencing_token': fencing_token,
                'terminal_operation_ids': _terminal_operation_ids(host.id),
                'instance_id': instance.id,
                'port': instance.port,
                'restore_from_operation': restore_from_operation,
            }
            ok, error = _run_playbook(host, 'update_instance_runtime.yml', extravars)
            if not ok:
                return _result(False, error, instance_id=instance.id)
            instance.python_deps_path = None
            commit()
            return _result(True, instance_id=instance.id, python_deps_path=None, manifest_path=None)

        deps = _validate_dependency_path(runtime, dependency_path)
        config_dir = immutable_inputs['config_dir']
        if not os.path.isdir(config_dir):
            return _result(False, f'Config inputs {config_dir} do not exist')
        hooks_dir = immutable_inputs.get('system_hooks_dir') or DEFAULT_SYSTEM_HOOKS_DIR

        paths = runtime_paths(runtime)
        required, optional = _runtime_artifacts(runtime)
        stage_dir = tempfile.mkdtemp(prefix='qlsm-runtime-update-')
        archive = _build_stage_archive(config_dir, hooks_dir, paths['plugins_dirname'], stage_dir)
        # Built explicitly rather than via instance_runtime_extravars(): the
        # unit must carry the venv being configured now, not the stored one.
        extravars = {
            **runtime_extravars(host),
            'operation_id': operation_id,
            'fencing_token': fencing_token,
            'terminal_operation_ids': _terminal_operation_ids(host.id),
            'instance_id': instance.id,
            'port': instance.port,
            'qlds_args': _build_qlds_args_string(instance),
            'ld_preload_paths': _build_ld_preload_paths(instance),
            'cpu_affinity': instance.cpu_affinity,
            'python_deps_path': deps,
            'runtime_artifacts': required,
            'runtime_optional_artifacts': optional,
            'stage_archive': archive,
            'restore_from_operation': '',
            'local_manifest_path': _local_manifest_path(host.id, operation_id, instance.id),
        }
        ok, error = _run_playbook(host, 'update_instance_runtime.yml', extravars)
        if not ok:
            return _result(False, error, instance_id=instance.id)
        instance.python_deps_path = deps or None
        commit()
        return _result(True, instance_id=instance.id, python_deps_path=deps or None,
                       manifest_path=extravars['local_manifest_path'])
    except Exception as exc:  # never raise into the orchestrator, except a takeover
        _reraise_stale(exc)
        log.exception('configure_existing_instance failed for instance %s', instance_id)
        try:
            db.session.rollback()
        except Exception:
            pass
        return _result(False, f'{type(exc).__name__}: {exc}', instance_id=instance_id)
    finally:
        if stage_dir:
            shutil.rmtree(stage_dir, ignore_errors=True)


# --- finalize ----------------------------------------------------------------------

def finalize_runtime_operation(host_id, *, operation_id, fencing_token):
    """Release the host's runtime-operation record for a terminal operation.
    The orchestrator calls this once the operation is terminal (succeeded,
    rolled back, or failed preparation after any remote play ran)."""
    try:
        _check_identity(operation_id, fencing_token)
        host = db.session.get(Host, host_id)
        if host is None:
            return _result(False, f'Host {host_id} not found')
        ok, error = _run_playbook(host, 'finalize_runtime_operation.yml',
                                  {'operation_id': operation_id, 'fencing_token': fencing_token})
        return _result(True) if ok else _result(False, error)
    except Exception as exc:
        log.exception('finalize_runtime_operation failed for host %s', host_id)
        return _result(False, f'{type(exc).__name__}: {exc}')
