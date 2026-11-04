"""The host runtime upgrade task: success, stale approvals, preparation
failures and whole-host rollback. Remote calls are faked; snapshot files,
config trees, conversion and the DB are real (see runtime_upgrade_harness)."""
import json
import os

import pytest

from tests.runtime_upgrade_harness import (
    STOCK,
    FakeDeps,
    FakeLocks,
    FakeRemote,
    assert_original,
    capture_originals,
    create_operation,
    make_env,
    make_host,
    tree_state,
)
from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.runtime_upgrade_guard import active_runtime_upgrade
from ui.task_logic import host_runtime_upgrade as orchestrator
from ui.task_logic import host_runtime_upgrade_rollback as rollback_module
from ui.task_logic.host_runtime_upgrade import upgrade_host_runtime_logic

TARGET_PRESET = os.path.join(os.path.dirname(STOCK), '..', 'default-minqlxtended', 'scripts')


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    with app.app_context():
        yield make_env(app, tmp_path, monkeypatch)


@pytest.fixture
def world(env):
    host = make_host(env)
    ids = {inst.name[-1]: inst.id for inst in host.instances}
    answers = {str(ids['A']): ['ban.py']}
    op = create_operation(host, answers=answers)
    remote, locks = FakeRemote(host), FakeLocks()
    return env, host, ids, op, remote, locks, capture_originals(env, host)


def _run(op, remote, locks, **kwargs):
    deps = FakeDeps(remote, locks, **kwargs)
    result = upgrade_host_runtime_logic(op.id, deps=deps, job_id='job-1')
    return result, deps


def _called(deps, name):
    return [call for call in deps.calls if call[0] == name]


def _op(op_id):
    return db.session.get(HostRuntimeUpgradeOperation, op_id)


def test_upgrade_succeeds_with_original_states(world):
    env, host, ids, op, remote, locks, _orig = world
    result, deps = _run(op, remote, locks)

    assert result is True
    host = db.session.get(Host, host.id)
    assert host.runtime == 'minqlxtended' and host.runtime_deps_isolated is True
    assert host.status == HostStatus.ACTIVE
    assert 'Upgraded to minqlxtended' in host.logs and 'Fallback presets:' in host.logs
    a, b, c = (db.session.get(QLInstance, ids[k]) for k in 'ABC')
    assert (a.status, b.status, c.status) == (InstanceStatus.RUNNING, InstanceStatus.STOPPED,
                                              InstanceStatus.RUNNING)
    assert remote.services[ids['A']]['active'] and remote.services[ids['C']]['active']
    assert not remote.services[ids['B']]['active']
    assert ('start', ids['B']) not in deps.calls  # a STOPPED instance is never started
    for inst in (a, b, c):
        assert remote.services[inst.id]['runtime'] == 'minqlxtended'
        assert inst.python_deps_path == f'/home/ql/runtime-deps/minqlxtended/{op.id}/{inst.id}'
        assert 'force_rate.so' not in remote.services[inst.id]['hooks']
    # Converted selections: ticked ban.py kept, custom mine.py dropped, NULL kept.
    assert a.qlx_plugins == 'balance, ban'
    assert c.qlx_plugins is None
    assert b.ld_preload_hooks is None  # force_rate.so is native on minqlxtended
    scripts = env.configs / host.name / str(a.id) / 'scripts'
    assert sorted(os.listdir(scripts)) == ['balance.py', 'ban.py']
    with open(os.path.join(TARGET_PRESET, 'ban.py'), encoding='utf-8') as handle:
        assert (scripts / 'ban.py').read_text() == handle.read()
    assert not [p for p in os.listdir(env.configs / host.name) if p.startswith('.upgrade-')]

    finished = _op(op.id)
    assert finished.state == 'succeeded' and finished.recovery_required is False
    assert remote.finalized == [op.id]
    assert locks.owners == {}
    assert active_runtime_upgrade(host.id) is None


def test_upgrade_host_with_no_instances(env):
    host = make_host(env, specs=())
    op = create_operation(host)
    remote, locks = FakeRemote(host), FakeLocks()
    result, deps = _run(op, remote, locks)
    assert result is True, (_op(op.id).state, _op(op.id).last_error)
    host = db.session.get(Host, host.id)
    assert host.runtime == 'minqlxtended' and host.status == HostStatus.ACTIVE
    assert _called(deps, 'install') == [('install', host.id)]
    assert not _called(deps, 'stop') and not _called(deps, 'configure')
    assert _op(op.id).state == 'succeeded'


def _assert_cancelled(host_id, op_id, deps, originals, env):
    host = db.session.get(Host, host_id)
    assert host.status == HostStatus.ACTIVE and host.runtime == 'minqlx'
    assert 'cancelled before any change' in host.logs
    assert [c for c in deps.calls if c[0] in ('stop', 'start', 'install', 'configure')] == []
    op = _op(op_id)
    assert op.state == 'failed_preparation' and op.snapshot_complete is False
    assert not os.path.exists(env.upgrades / str(host_id) / op_id)
    for iid, original in originals.items():
        assert db.session.get(QLInstance, iid).status == original['status']
    assert active_runtime_upgrade(host_id) is None


def test_upgrade_aborts_when_classification_changed(world):
    env, host, ids, op, remote, locks, orig = world
    scripts = env.configs / host.name / str(ids['A']) / 'scripts'
    (scripts / 'mine.py').write_text('import minqlx\n# edited after the dialog\n')
    orig[ids['A']]['tree'] = tree_state(env.configs / host.name / str(ids['A']))

    result, deps = _run(op, remote, locks)

    assert result is False
    _assert_cancelled(host.id, op.id, deps, orig, env)
    assert 'changed after the upgrade was confirmed' in _op(op.id).last_error


def test_upgrade_aborts_when_selection_changed(world):
    env, host, ids, op, remote, locks, orig = world
    db.session.get(QLInstance, ids['C']).qlx_plugins = 'balance'
    db.session.commit()
    result, deps = _run(op, remote, locks)
    assert result is False
    _assert_cancelled(host.id, op.id, deps, orig, env)


def test_upgrade_aborts_when_target_inputs_changed(world):
    env, host, ids, op, remote, locks, orig = world
    pool = env.pool / 'minqlxtended'
    pool.mkdir(parents=True, exist_ok=True)
    (pool / 'new_shared.py').write_text('x = 1\n')
    result, deps = _run(op, remote, locks)
    assert result is False
    _assert_cancelled(host.id, op.id, deps, orig, env)


def test_upgrade_aborts_on_answers_never_offered(env):
    host = make_host(env)
    a = next(inst for inst in host.instances if inst.name.endswith('A'))
    op = create_operation(host, answers={str(a.id): ['mine.py']})
    remote, locks = FakeRemote(host), FakeLocks()
    orig = capture_originals(env, host)
    result, deps = _run(op, remote, locks)
    assert result is False
    _assert_cancelled(host.id, op.id, deps, orig, env)


def test_snapshot_failure_calls_neither_stop_nor_restore(world, monkeypatch):
    env, host, ids, op, remote, locks, orig = world

    def broken(*_a, **_k):
        raise OSError('disk full')

    restores = []
    monkeypatch.setattr(orchestrator, 'prepare_upgrade_snapshot', broken)
    monkeypatch.setattr(rollback_module, 'restore_instance', lambda *a, **k: restores.append(a))
    result, deps = _run(op, remote, locks)
    assert result is False and restores == []
    _assert_cancelled(host.id, op.id, deps, orig, env)
    assert 'disk full' in _op(op.id).last_error


def _assert_rolled_back(env, host_id, orig, remote, deps, locks, b_id):
    host, op = assert_original(env, host_id, orig, remote)
    assert host.status == HostStatus.ERROR
    assert f'Upgrade failed: {op.last_error}. Rolled back to minqlx.' in host.logs
    assert op.recovery_required is False
    assert ('start', b_id) not in deps.calls
    assert locks.owners == {}
    assert active_runtime_upgrade(host_id) is None
    assert remote.finalized == [op.id]
    return host, op


def _dir_identity(root):
    """(inode, mtime_ns, bytes) of a directory and everything under it."""
    entries = {}
    for current, _dirs, files in os.walk(root):
        stat_result = os.stat(current)
        entries[current] = (stat_result.st_ino, stat_result.st_mtime_ns, None)
        for name in files:
            path = os.path.join(current, name)
            stat_result = os.stat(path)
            with open(path, 'rb') as handle:
                entries[path] = (stat_result.st_ino, stat_result.st_mtime_ns, handle.read())
    return entries


def test_failed_initial_stop_never_installs_or_switches(world, monkeypatch):
    env, host, ids, op, remote, locks, orig = world
    c_dir = env.configs / host.name / str(ids['C'])
    before = _dir_identity(c_dir)
    restored = []
    real_restore = rollback_module.restore_instance
    monkeypatch.setattr(rollback_module, 'restore_instance',
                        lambda instance, root, **k: restored.append(instance.id) or real_restore(instance, root, **k))
    result, deps = _run(op, remote, locks, fail={('stop', ids['C'])})
    assert result is False
    # C was never quiesced: its live directory is untouched (same inodes,
    # mtimes and bytes) and the snapshot restore never ran for any instance,
    # since nothing was converted.
    assert _dir_identity(c_dir) == before
    assert restored == []
    outcome = json.loads(_op(op.id).instance_outcomes_json)['instances'][str(ids['C'])]
    assert outcome['stop'] == 'failed' and outcome['forward_stop_failed'] == 'stop playbook failed'
    assert not _called(deps, 'install') and not _called(deps, 'configure')
    _host, finished = _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])
    assert 'could not stop instance uh-C' in finished.last_error
    assert ('start', ids['A']) in deps.calls  # A had been stopped: it comes back


def test_install_failure_rolls_back(world):
    env, host, ids, op, remote, locks, orig = world
    result, deps = _run(op, remote, locks, fail={'install'})
    assert result is False
    assert [c for c in _called(deps, 'configure') if not c[3]] == []
    _host, finished = _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])
    assert finished.last_error.startswith('minqlxtended install failed')


def test_target_configure_failure_rolls_back(world):
    env, host, ids, op, remote, locks, orig = world
    result, deps = _run(op, remote, locks, fail={('configure', ids['C'], False)})
    assert result is False
    rollback_configures = [c[1] for c in _called(deps, 'configure') if c[3]]
    assert sorted(rollback_configures) == sorted([ids['A'], ids['B'], ids['C']])
    _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])


def test_running_readiness_timeout_rolls_back(world):
    env, host, ids, op, remote, locks, orig = world
    calls = {'n': 0}
    deps = FakeDeps(remote, locks)
    original_ready = deps.wait_ready

    def flaky_ready(instance, timeout=60):
        calls['n'] += 1
        if calls['n'] == 1:  # the first readiness check, on minqlxtended
            return False, 'not ready within 60s: server has not reported status since it started'
        return original_ready(instance, timeout)

    deps.wait_ready = flaky_ready
    assert upgrade_host_runtime_logic(op.id, deps=deps, job_id='job-1') is False
    _host, finished = _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])
    assert 'did not come up on minqlxtended' in finished.last_error


def test_stopped_instance_conversion_failure_rolls_back(world, monkeypatch):
    env, host, ids, op, remote, locks, orig = world
    real = orchestrator.build_converted_tree

    def convert(inputs_dir, captured, ticked, excluded, dest):
        if captured['instance_id'] == ids['B']:
            raise RuntimeError('cannot convert B')
        return real(inputs_dir, captured, ticked, excluded, dest)

    monkeypatch.setattr(orchestrator, 'build_converted_tree', convert)
    result, deps = _run(op, remote, locks)
    assert result is False
    _host, finished = _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])
    assert 'cannot convert B' in finished.last_error


def test_stopped_instance_that_comes_up_active_rolls_back(world):
    env, host, ids, op, remote, locks, orig = world
    deps = FakeDeps(remote, locks)
    real_configure = deps.configure

    def configure(instance_id, runtime, *args, **kwargs):
        result = real_configure(instance_id, runtime, *args, **kwargs)
        if instance_id == ids['B'] and runtime == 'minqlxtended':
            remote.services[ids['B']]['active'] = True  # something started it
        return result

    deps.configure = configure
    assert upgrade_host_runtime_logic(op.id, deps=deps, job_id='job-1') is False
    _host, finished = _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])
    assert 'STOPPED instance uh-B is active' in finished.last_error


def test_rollback_restores_ld_preload_hooks(world):
    env, host, ids, op, remote, locks, orig = world
    deps = FakeDeps(remote, locks, fail={('configure', ids['C'], False)})
    seen = {}
    real_configure = deps.configure

    def configure(instance_id, runtime, *args, **kwargs):
        if instance_id == ids['C'] and runtime == 'minqlxtended':
            seen['converted'] = db.session.get(QLInstance, ids['B']).ld_preload_hooks
        return real_configure(instance_id, runtime, *args, **kwargs)

    deps.configure = configure
    assert upgrade_host_runtime_logic(op.id, deps=deps, job_id='job-1') is False
    assert seen['converted'] is None  # dropped in the converted state only
    b = db.session.get(QLInstance, ids['B'])
    assert b.ld_preload_hooks == 'force_rate.so'
    assert (env.configs / host.name / str(b.id) / 'user-hooks' / 'force_rate.so').is_file()
    _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])


def test_unexpected_exception_after_mutation_rolls_back(world, monkeypatch):
    env, host, ids, op, remote, locks, orig = world

    def explode(*_a, **_k):
        raise KeyError('surprise')

    monkeypatch.setattr(orchestrator, 'build_target_system_hooks', explode)
    result, deps = _run(op, remote, locks)
    assert result is False
    _host, finished = _assert_rolled_back(env, host.id, orig, remote, deps, locks, ids['B'])
    assert finished.last_error.startswith('unexpected error')


def test_restore_failure_is_isolated_and_keeps_the_reservation(world, monkeypatch):
    env, host, ids, op, remote, locks, orig = world
    real_restore = rollback_module.restore_instance

    def restore(instance, root, **kwargs):
        if instance.id == ids['A']:
            return {'instance_id': instance.id, 'ok': False, 'phase': 'swap',
                    'error': 'disk error', 'status_verified': False}
        return real_restore(instance, root, **kwargs)

    monkeypatch.setattr(rollback_module, 'restore_instance', restore)
    # C's configure fails, so A (converted + configured) and C (converted) roll
    # back; C's restart then fails too.
    result, deps = _run(op, remote, locks, fail={('configure', ids['C'], False), ('start', ids['C'])})
    assert result is False

    host = db.session.get(Host, host.id)
    finished = _op(op.id)
    assert host.runtime == 'minqlx' and host.status == HostStatus.ERROR
    assert finished.state == 'recovery_required' and finished.recovery_required is True
    outcomes = json.loads(finished.instance_outcomes_json)['instances']
    assert outcomes[str(ids['A'])]['rollback']['phase'] == 'restore:swap'
    assert outcomes[str(ids['C'])]['rollback']['phase'] == 'start'
    assert outcomes[str(ids['B'])]['rollback']['ok'] is True  # later instance still attempted
    assert 'Rollback of instance uh-A failed in restore:swap: disk error' in host.logs
    assert 'Rollback of instance uh-C failed in start: start playbook failed' in host.logs
    assert os.path.isdir(finished.snapshot_path)  # artifacts retained
    assert active_runtime_upgrade(host.id) is not None
    assert remote.finalized == []
    assert locks.owners == {}  # execution locks released, reservation kept


def test_stop_failure_during_rollback_keeps_running_files(world):
    env, host, ids, op, remote, locks, orig = world
    deps = FakeDeps(remote, locks, fail={('ready', ids['A'])})
    real_stop = deps.stop

    def stop(instance):
        if instance.id == ids['A'] and remote.services[ids['A']]['runtime'] == 'minqlxtended':
            return False, 'stop timed out'
        return real_stop(instance)

    deps.stop = stop
    assert upgrade_host_runtime_logic(op.id, deps=deps, job_id='job-1') is False
    finished = _op(op.id)
    outcome = json.loads(finished.instance_outcomes_json)['instances'][str(ids['A'])]['rollback']
    assert outcome['phase'] == 'stop' and outcome['ok'] is False
    # A's converted files were left alone; the other instances were restored.
    assert sorted(os.listdir(env.configs / host.name / str(ids['A']) / 'scripts')) == ['balance.py', 'ban.py']
    assert tree_state(env.configs / host.name / str(ids['C'])) == orig[ids['C']]['tree']
    assert finished.state == 'recovery_required'
    assert db.session.get(Host, host.id).runtime == 'minqlx'


def test_busy_host_cancels_before_any_change(world):
    env, host, ids, op, remote, locks, orig = world
    locks.owners[('instance', ids['B'])] = 'some-other-task'
    result, deps = _run(op, remote, locks)
    assert result is False
    _assert_cancelled(host.id, op.id, deps, orig, env)
    assert 'another operation is running' in _op(op.id).last_error
    assert locks.owners == {('instance', ids['B']): 'some-other-task'}


def test_answers_with_auto_accepted_paths_succeed(env):
    """The dialog may send combineAcceptedPaths(auto_accepted + ticked)."""
    host = make_host(env)
    a = next(inst for inst in host.instances if inst.name.endswith('A'))
    op = create_operation(host, answers={str(a.id): ['balance.py', 'ban.py']})
    result, _deps = _run(op, FakeRemote(host), FakeLocks())
    assert result is True
    assert db.session.get(QLInstance, a.id).qlx_plugins == 'balance, ban'


def test_stopped_instance_with_a_stray_server_process_aborts_the_upgrade(world):
    """STOPPED means systemd inactive AND no server process for the port."""
    env, host, ids, op, remote, locks, orig = world
    result, deps = _run(op, remote, locks, fail={('stray', ids['B'])})
    assert result is False
    assert not _called(deps, 'install')
    finished = _op(op.id)
    assert 'was STOPPED but its service is stray_process' in finished.last_error
    assert ('start', ids['B']) not in deps.calls
