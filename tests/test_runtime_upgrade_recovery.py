"""Interrupted host runtime upgrades: a worker dies at each durable step, a
fresh recovery worker is built from DB + disk + the (surviving) remote state,
and the host must end exactly as it was, with exclusive ownership throughout."""
import datetime
import json
import os
from types import SimpleNamespace

import pytest

from tests.helpers import auth_headers
from tests.runtime_upgrade_harness import (
    Crash,
    FakeDeps,
    FakeLocks,
    FakeRemote,
    assert_original,
    capture_originals,
    create_operation,
    fresh_worker,
    make_env,
    make_host,
    restore_lock_release,
)
from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.runtime_upgrade_guard import active_runtime_upgrade
from ui.task_logic.host_runtime_upgrade import upgrade_host_runtime_logic
from ui.task_logic.host_runtime_upgrade_recovery import (
    RETRY_INTERVAL_SECONDS,
    handle_upgrade_job_failure,
    reconcile_runtime_upgrades,
    recover_host_runtime_logic,
    request_recovery,
    start_upgrade_job,
)
from ui.task_logic.host_runtime_upgrade_state import claim_operation


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    with app.app_context():
        yield make_env(app, tmp_path, monkeypatch)


@pytest.fixture
def world(env):
    host = make_host(env)
    ids = {inst.name[-1]: inst.id for inst in host.instances}
    op = create_operation(host, answers={str(ids['A']): ['ban.py']})
    return SimpleNamespace(env=env, host_id=host.id, host_name=host.name, ids=ids, op_id=op.id,
                           remote=FakeRemote(host), locks=FakeLocks(),
                           orig=capture_originals(env, host))


def _op(op_id):
    return db.session.get(HostRuntimeUpgradeOperation, op_id)


def _die_at(world, checkpoint, **kwargs):
    deps = FakeDeps(world.remote, world.locks, crash_at=checkpoint, **kwargs)
    with pytest.raises(Crash):
        upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-1')
    fresh_worker()
    # The dead worker's job and execution locks are still recorded.
    assert _op(world.op_id).rq_job_id == 'job-1'
    assert world.locks.owners  # never released
    assert active_runtime_upgrade(world.host_id) is not None  # still reserved
    restore_lock_release(world.locks)
    return deps


def _recover(world, job_id='job-2', **kwargs):
    deps = FakeDeps(world.remote, world.locks, **kwargs)
    return recover_host_runtime_logic(world.op_id, deps=deps, job_id=job_id), deps


def _assert_exclusive_end(world):
    assert world.locks.owners == {}
    assert active_runtime_upgrade(world.host_id) is None


@pytest.mark.parametrize('checkpoint', ['snapshot_published'])
def test_death_after_snapshot_publication_terminates_preparation(world, checkpoint):
    _die_at(world, checkpoint)
    result, deps = _recover(world)
    assert result is False
    op = _op(world.op_id)
    assert op.state == 'failed_preparation' and op.fencing_token == 2
    assert [c for c in deps.calls if c[0] in ('stop', 'start', 'configure', 'install')] == []
    host = db.session.get(Host, world.host_id)
    assert host.status == HostStatus.ACTIVE and host.runtime == 'minqlx'
    assert not os.path.exists(os.path.join(str(world.env.upgrades), str(world.host_id), world.op_id))
    for iid, original in world.orig.items():
        assert db.session.get(QLInstance, iid).status == original['status']
        assert world.remote.services[iid]['active'] == (original['status'].value == 'running')
    _assert_exclusive_end(world)


def _first(world, kind):
    return f'{kind}:{world.ids["A"]}'


@pytest.mark.parametrize('point', ['converted', 'runtime_committed', 'configured'])
def test_death_after_mutation_is_rolled_back_by_a_fresh_worker(world, point):
    checkpoint = 'runtime_committed' if point == 'runtime_committed' else _first(world, point)
    _die_at(world, checkpoint)

    result, deps = _recover(world)

    assert result is False
    host, op = assert_original(world.env, world.host_id, world.orig, world.remote)
    assert host.status == HostStatus.ERROR
    assert 'Rolled back to minqlx.' in host.logs
    assert op.fencing_token == 2 and op.rq_job_id == 'job-2'
    assert ('start', world.ids['B']) not in deps.calls
    assert world.remote.finalized == [world.op_id]
    assert not [p for p in os.listdir(world.env.configs / world.host_name) if p.startswith('.upgrade-')]
    _assert_exclusive_end(world)


def test_death_during_rollback_is_resumed(world):
    rollback_point = f'rollback_restored:{world.ids["A"]}'
    _die_at(world, rollback_point, fail={('configure', world.ids['C'], False)})
    assert _op(world.op_id).state == 'rolling_back'

    result, deps = _recover(world)

    assert result is False
    assert_original(world.env, world.host_id, world.orig, world.remote)
    _assert_exclusive_end(world)


def test_repeated_recovery_is_idempotent(world):
    _die_at(world, 'runtime_committed')
    _recover(world)
    calls_before = list(world.remote.finalized)
    result, deps = _recover(world, job_id='job-3')
    assert result is True and deps.calls == []
    assert world.remote.finalized == calls_before
    assert_original(world.env, world.host_id, world.orig, world.remote)


def test_replayed_rollback_reverifies_actual_state(world):
    """An incomplete rollback replayed after the cause is gone completes."""
    _die_at(world, _first(world, 'configured'))
    result, _deps = _recover(world, fail={('start', world.ids['C'])})
    assert result is False and _op(world.op_id).state == 'recovery_required'
    assert active_runtime_upgrade(world.host_id) is not None

    result, deps = _recover(world, job_id='job-3')
    assert result is False
    assert_original(world.env, world.host_id, world.orig, world.remote)
    _assert_exclusive_end(world)


def test_retry_never_bounces_an_instance_whose_rollback_completed(world):
    """One instance keeps failing across recovery runs: the instances already
    restored are only re-verified (read-only), never stopped, reconfigured or
    restarted again."""
    _die_at(world, _first(world, 'configured'))
    failing = world.ids['C']
    result, first = _recover(world, fail={('start', failing)})
    assert result is False and _op(world.op_id).state == 'recovery_required'
    outcomes = json.loads(_op(world.op_id).instance_outcomes_json)['instances']
    restored = [iid for iid in world.ids.values()
                if iid != failing and outcomes[str(iid)].get('rollback', {}).get('ok')]
    assert restored  # at least one instance was fully rolled back by the first run
    assert any(c[0] in ('stop', 'configure', 'start') and c[1] in restored for c in first.calls)

    result, second = _recover(world, job_id='job-3', fail={('start', failing)})
    assert result is False and _op(world.op_id).state == 'recovery_required'
    bounced = [c for c in second.calls if c[0] in ('stop', 'configure', 'start', 'ready') and c[1] in restored]
    assert bounced == []
    assert ('start', failing) in second.calls  # the failing instance is still retried
    for iid in restored:
        assert world.remote.services[iid]['active'] == (world.orig[iid]['status'] == InstanceStatus.RUNNING)
        assert db.session.get(QLInstance, iid).status == world.orig[iid]['status']

    _recover(world, job_id='job-4')
    assert_original(world.env, world.host_id, world.orig, world.remote)
    _assert_exclusive_end(world)


def test_restored_instance_drift_is_recorded_not_acted_on(world):
    """A restored instance whose service drifted before a retry is noted and
    left alone: the retry never stops or starts it."""
    _die_at(world, _first(world, 'configured'))
    failing = world.ids['C']
    _recover(world, fail={('start', failing)})
    world.remote.services[world.ids['A']]['active'] = False  # someone stopped it meanwhile

    _result, deps = _recover(world, job_id='job-3', fail={('start', failing)})
    assert not [c for c in deps.calls if c[1] == world.ids['A'] and c[0] in ('stop', 'start', 'configure')]
    outcome = json.loads(_op(world.op_id).instance_outcomes_json)['instances'][str(world.ids['A'])]
    assert outcome['rollback']['ok'] is True and 'expected RUNNING' in outcome['rollback']['note']
    assert 'expected RUNNING' in db.session.get(Host, world.host_id).logs


def test_live_previous_job_delays_takeover(world):
    _die_at(world, 'runtime_committed')
    result, deps = _recover(world, alive={'job-1'})
    assert result.startswith('pending: job job-1')
    assert _op(world.op_id).fencing_token == 1 and deps.calls == []


def test_remote_play_still_running_keeps_recovery_pending(world):
    _die_at(world, _first(world, 'configured'))
    world.remote.busy = 10
    result, _deps = _recover(world)
    op = _op(world.op_id)
    host = db.session.get(Host, world.host_id)
    assert result is False and op.state == 'recovery_required' and op.recovery_required
    assert host.status == HostStatus.ERROR and host.runtime == 'minqlx'
    assert 'waiting to retry' in host.logs and 'recovery will retry' in host.logs
    outcome = json.loads(op.instance_outcomes_json)['instances'][str(world.ids['A'])]['rollback']
    assert outcome['pending'] is True and outcome['phase'] == 'configure'
    assert active_runtime_upgrade(world.host_id) is not None

    world.remote.busy = 0
    _recover(world, job_id='job-3')
    assert_original(world.env, world.host_id, world.orig, world.remote)
    _assert_exclusive_end(world)


def test_stale_execution_token_is_rejected(world):
    """A takeover while the old worker is still running stops the old worker
    before its next side effect, locally and on the host."""
    def takeover(name):
        if name == 'runtime_committed':
            assert claim_operation(world.op_id, 'job-2') == 2

    deps = FakeDeps(world.remote, world.locks, on_checkpoint=takeover)
    assert upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-1') is False
    assert not [c for c in deps.calls if c[0] == 'configure']
    op = _op(world.op_id)
    assert op.fencing_token == 2 and op.state == 'configuring' and op.rq_job_id == 'job-2'

    # The host rejects a play carrying the superseded token.
    world.remote.max_token[world.op_id] = 2
    refused = deps.configure(world.ids['A'], 'minqlxtended', {'config_dir': str(world.env.tmp),
                                                              'system_hooks_dir': str(world.env.tmp)},
                             None, operation_id=world.op_id, fencing_token=1)
    assert refused['ok'] is False and 'stale fencing token' in refused['error']


def test_lock_expiry_keeps_the_mutation_blockade(app, client, world):
    _die_at(world, 'runtime_committed')
    world.locks.owners.clear()  # Redis TTLs lapsed
    headers = auth_headers(app, 'u')
    response = client.post(f'/api/instances/{world.ids["A"]}/stop', headers=headers)
    assert response.status_code == 409
    assert 'being upgraded to minqlxtended' in response.get_json()['error']['message']


def test_failure_callback_requests_recovery_and_reconciler_covers_enqueue_failure(world):
    _die_at(world, 'runtime_committed')
    deps = FakeDeps(world.remote, world.locks)
    deps.enqueue_error = ConnectionError('redis down')
    job = SimpleNamespace(id='job-1', args=[world.op_id])

    new_job = handle_upgrade_job_failure(job, RuntimeError, 'worker died', deps=deps)

    op = _op(world.op_id)
    assert new_job and op.rq_job_id == new_job and op.recovery_required is True
    assert deps.enqueued == []
    assert 'recovery scheduled' in db.session.get(Host, world.host_id).logs

    # The reconciler sees a nonterminal operation whose job never existed.
    deps.enqueue_error = None
    later = datetime.datetime.utcnow() + datetime.timedelta(seconds=5)
    assert reconcile_runtime_upgrades(deps=deps, now=later) == [world.op_id]
    (_, recovery_job), = deps.enqueued
    assert _op(world.op_id).rq_job_id == recovery_job

    result, _ = _recover(world, job_id=recovery_job)
    assert result is False
    assert_original(world.env, world.host_id, world.orig, world.remote)


def test_callback_for_a_superseded_job_is_ignored(world):
    _die_at(world, 'runtime_committed')
    deps = FakeDeps(world.remote, world.locks)
    request_recovery(world.op_id, deps=deps)
    assert handle_upgrade_job_failure(SimpleNamespace(id='job-1', args=[world.op_id]),
                                      RuntimeError, 'late', deps=deps) is None
    assert len(deps.enqueued) == 1


def test_reconciler_skips_live_fresh_and_recently_retried_operations(world):
    deps = FakeDeps(world.remote, world.locks)
    now = datetime.datetime.utcnow()
    # Fresh row, job not recorded yet: Task 6 may still be enqueueing.
    assert reconcile_runtime_upgrades(deps=deps, now=now) == []
    # Job recorded and alive.
    start_upgrade_job(world.op_id, enqueue=lambda op_id, job_id: None)
    deps.alive = {_op(world.op_id).rq_job_id}
    assert reconcile_runtime_upgrades(deps=deps, now=now + datetime.timedelta(hours=1)) == []
    # Incomplete rollback retried only after the retry interval.
    op = _op(world.op_id)
    op.state = 'recovery_required'
    db.session.commit()
    deps.alive = set()
    soon = op.updated_at + datetime.timedelta(seconds=RETRY_INTERVAL_SECONDS - 10)
    assert reconcile_runtime_upgrades(deps=deps, now=soon) == []
    late = op.updated_at + datetime.timedelta(seconds=RETRY_INTERVAL_SECONDS + 10)
    assert reconcile_runtime_upgrades(deps=deps, now=late) == [world.op_id]


def test_unassigned_job_row_is_recovered_after_grace(world):
    deps = FakeDeps(world.remote, world.locks)
    later = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    assert reconcile_runtime_upgrades(deps=deps, now=later) == [world.op_id]
    (_, job_id), = deps.enqueued
    result, _ = _recover(world, job_id=job_id)
    assert result is False and _op(world.op_id).state == 'failed_preparation'
    assert db.session.get(Host, world.host_id).status == HostStatus.ACTIVE


def test_job_timeout_records_recovery_and_returns(world):
    """A timeout stops the job without an inline rollback; the reconciler then
    finds the finished job and hands the operation to recovery."""
    from rq.timeouts import JobTimeoutException

    def timeout(name):
        if name == 'runtime_committed':
            raise JobTimeoutException('Task exceeded maximum timeout value (3600 seconds)')

    deps = FakeDeps(world.remote, world.locks, on_checkpoint=timeout)
    result = upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-1')
    assert isinstance(result, str) and 'timed out' in result
    op = _op(world.op_id)
    assert op.recovery_required is True and not op.is_terminal and op.state == 'configuring'
    assert 'timed out' in op.last_error
    assert not [c for c in deps.calls if c[0] == 'configure']  # no further work
    assert world.locks.owners == {}

    later = datetime.datetime.utcnow() + datetime.timedelta(seconds=5)
    assert reconcile_runtime_upgrades(deps=deps, now=later) == [world.op_id]
    (_, job_id), = deps.enqueued
    result, _ = _recover(world, job_id=job_id)
    assert result is False
    assert_original(world.env, world.host_id, world.orig, world.remote)


def test_job_timeout_during_rollback_is_recovery_pending_not_instance_error(world):
    from rq.timeouts import JobTimeoutException

    deps = FakeDeps(world.remote, world.locks, fail={('configure', world.ids['C'], False)})
    real_ready = deps.wait_ready
    first = {'A': True}

    def ready(instance, timeout=60):
        if instance.id == world.ids['A'] and first['A'] and \
                db.session.get(Host, world.host_id).runtime == 'minqlx':
            first['A'] = False
            raise JobTimeoutException('Task exceeded maximum timeout value (3600 seconds)')
        return real_ready(instance, timeout)

    deps.wait_ready = ready
    result = upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-1')
    assert isinstance(result, str) and 'timed out' in result
    op = _op(world.op_id)
    assert op.state == 'rolling_back' and op.recovery_required is True
    outcomes = json.loads(op.instance_outcomes_json)['instances']
    assert 'rollback' not in outcomes[str(world.ids['A'])] or \
        outcomes[str(world.ids['A'])]['rollback']['phase'] != 'unexpected'
    assert db.session.get(QLInstance, world.ids['A']).status.value != 'error'
    # Work stopped in that job: later instances were not rolled back by it.
    assert 'rollback' not in outcomes[str(world.ids['C'])]

    result, _ = _recover(world)
    assert result is False
    assert_original(world.env, world.host_id, world.orig, world.remote)
    _assert_exclusive_end(world)


def test_stale_executor_writes_are_rejected_after_takeover(world):
    from ui.task_logic.host_runtime_upgrade_state import Execution, StaleExecution

    token = claim_operation(world.op_id, 'job-1')
    old = Execution(world.op_id, token, 'job-1', FakeDeps(world.remote, world.locks))
    old.record(world.ids['A'], stop='ok')  # still the owner: accepted
    assert claim_operation(world.op_id, 'job-2') == token + 1
    new = Execution(world.op_id, token + 1, 'job-2', FakeDeps(world.remote, world.locks))
    new.record(world.ids['A'], rollback={'phase': 'complete', 'ok': True})

    with pytest.raises(StaleExecution):
        old.record(world.ids['A'], stop='overwritten-by-stale')
    instance = db.session.get(QLInstance, world.ids['A'])
    instance.status = InstanceStatus.ERROR
    db.session.get(Host, world.host_id).runtime = 'minqlxtended'
    with pytest.raises(StaleExecution):
        old.commit()
    with pytest.raises(StaleExecution):
        old.fence()
    fresh_worker()
    outcome = json.loads(_op(world.op_id).instance_outcomes_json)['instances'][str(world.ids['A'])]
    assert outcome == {'stop': 'ok', 'rollback': {'phase': 'complete', 'ok': True}}
    assert db.session.get(QLInstance, world.ids['A']).status == world.orig[world.ids['A']]['status']
    assert db.session.get(Host, world.host_id).runtime == 'minqlx'


def test_takeover_during_readiness_wait_rejects_the_stale_status_write(world):
    """The old worker's RUNNING status and journal write after a 60 s wait
    are rejected once a recovery execution has taken over."""
    deps = FakeDeps(world.remote, world.locks)
    real_ready = deps.wait_ready

    def ready(instance, timeout=60):
        ok = real_ready(instance, timeout)
        if instance.id == world.ids['A']:
            assert claim_operation(world.op_id, 'job-2') == 2
        return ok

    deps.wait_ready = ready
    assert upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-1') is False
    fresh_worker()
    outcome = json.loads(_op(world.op_id).instance_outcomes_json)['instances'][str(world.ids['A'])]
    assert outcome['start'] == 'requested'  # the stale 'ok' never landed
    assert db.session.get(QLInstance, world.ids['A']).status.value != 'running'
    assert ('start', world.ids['C']) not in deps.calls  # side effects stopped


def test_late_forward_job_hands_over_to_recovery(world):
    _die_at(world, 'runtime_committed')
    deps = FakeDeps(world.remote, world.locks)
    assert upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-9') is False
    assert_original(world.env, world.host_id, world.orig, world.remote)


# --- production dependency seams ------------------------------------------------------

class _DictRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def expire(self, key, ttl):
        return key in self.data


def _patch_task_lock(monkeypatch, store):
    from ui import task_lock

    def acquire(kind, entity_id, token, ttl):
        key = f'task_lock:{kind}:{entity_id}'
        if key in store.data:
            return False
        store.data[key] = token
        return True

    def release(kind, entity_id, token):
        key = f'task_lock:{kind}:{entity_id}'
        if store.data.get(key) == token:
            del store.data[key]
            return True
        return False

    monkeypatch.setattr(task_lock, '_get_redis', lambda: store)
    monkeypatch.setattr(task_lock, 'acquire_lock', acquire)
    monkeypatch.setattr(task_lock, 'release_lock', release)
    monkeypatch.setattr(task_lock, 'force_release_lock',
                        lambda kind, entity_id: store.data.pop(f'task_lock:{kind}:{entity_id}', None))


def test_execution_locks_take_over_only_from_the_same_operation(app, monkeypatch):
    from ui.task_logic.host_runtime_upgrade_deps import RedisExecutionLocks, execution_lock_token

    store = _DictRedis()
    _patch_task_lock(monkeypatch, store)
    locks = RedisExecutionLocks()
    old, new = execution_lock_token('a' * 32, 1), execution_lock_token('a' * 32, 2)
    assert locks.acquire('a' * 32, old, 7, [1, 2])
    assert locks.acquire('a' * 32, new, 7, [1, 2])  # newer token of the same operation
    assert set(store.data.values()) == {new}
    other = execution_lock_token('b' * 32, 1)
    assert not locks.acquire('b' * 32, other, 7, [1, 2])  # someone else's
    assert set(store.data.values()) == {new}
    store.data.pop('task_lock:instance:2')  # TTL lapse
    assert locks.renew('a' * 32, new, 7, [1, 2]) and store.data['task_lock:instance:2'] == new
    locks.release('a' * 32, old, 7, [1, 2])  # a stale token releases nothing
    assert len(store.data) == 3
    locks.release('a' * 32, new, 7, [1, 2])
    assert store.data == {}


def test_remote_pending_classifier():
    from ui.task_logic.host_runtime_upgrade_deps import is_remote_pending

    assert is_remote_pending('another runtime operation play is still running on this host (operation x)')
    assert is_remote_pending('fatal: [h]: UNREACHABLE! => {"msg": "ssh: connect"}')
    assert not is_remote_pending('fatal: [h]: FAILED! => {"msg": "python 3.12 required"}')
    assert not is_remote_pending(None)


def test_job_alive_reads_rq_state(app, monkeypatch):
    from rq.exceptions import NoSuchJobError
    from rq.job import Job, JobStatus

    from ui.task_logic.host_runtime_upgrade_deps import UpgradeDeps

    now = datetime.datetime.now(datetime.timezone.utc)
    jobs = {
        'queued': SimpleNamespace(get_status=lambda refresh=False: JobStatus.QUEUED),
        'failed': SimpleNamespace(get_status=lambda refresh=False: JobStatus.FAILED),
        'beating': SimpleNamespace(get_status=lambda refresh=False: JobStatus.STARTED,
                                   last_heartbeat=now, started_at=now),
        'silent': SimpleNamespace(get_status=lambda refresh=False: JobStatus.STARTED,
                                  last_heartbeat=now - datetime.timedelta(minutes=10), started_at=None),
    }

    def fetch(job_id, connection=None):
        if job_id not in jobs:
            raise NoSuchJobError(job_id)
        return jobs[job_id]

    monkeypatch.setattr(Job, 'fetch', staticmethod(fetch))
    monkeypatch.setattr('ui.rq.get_queue', lambda *a, **k: SimpleNamespace(connection=None))
    deps = UpgradeDeps()
    with app.app_context():
        assert deps.job_alive('queued') and deps.job_alive('beating')
        assert not deps.job_alive('failed') and not deps.job_alive('silent')
        assert not deps.job_alive('gone') and not deps.job_alive(None)


def test_rq_entry_points_are_registered_with_an_hour_timeout():
    from ui import tasks

    assert tasks.upgrade_host_runtime.helper.timeout == 3600
    assert tasks.recover_host_runtime.helper.timeout == 3600


def test_death_between_conversion_renames_is_rolled_back(world, monkeypatch):
    """The live directory was renamed aside and the converted copy never
    renamed in: the live path is missing until the rollback rebuilds it."""
    from ui.runtime_upgrade_conversion import conversion_paths
    from ui.task_logic import host_runtime_upgrade as orchestrator

    def die_mid_swap(live, converted, tag):
        _staged, original = conversion_paths(live, tag)
        os.rename(live, original)
        world.locks.release = lambda *a, **k: None
        raise Crash('between renames')

    monkeypatch.setattr(orchestrator, 'install_converted_tree', die_mid_swap)
    with pytest.raises(Crash):
        upgrade_host_runtime_logic(world.op_id, deps=FakeDeps(world.remote, world.locks), job_id='job-1')
    fresh_worker()
    restore_lock_release(world.locks)
    live = world.env.configs / world.host_name / str(world.ids['A'])
    assert not live.exists()

    result, _deps = _recover(world)
    assert result is False
    assert_original(world.env, world.host_id, world.orig, world.remote)
    _assert_exclusive_end(world)


def _die_inside_stop(world, *, took_effect):
    """The worker dies inside the stop of A: 'requested' is recorded, the
    outcome never is."""
    deps = FakeDeps(world.remote, world.locks)

    def stop(instance):
        if instance.id == world.ids['A']:
            if took_effect:
                world.remote.services[instance.id]['active'] = False
            world.locks.release = lambda *a, **k: None
            raise Crash('inside stop')
        return FakeDeps.stop(deps, instance)

    deps.stop = stop
    with pytest.raises(Crash):
        upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-1')
    fresh_worker()
    restore_lock_release(world.locks)
    outcome = json.loads(_op(world.op_id).instance_outcomes_json)['instances'][str(world.ids['A'])]
    assert outcome['stop'] == 'requested'


def test_stop_requested_and_taken_effect_is_restarted_and_verified(world):
    _die_inside_stop(world, took_effect=True)
    result, deps = _recover(world)
    assert result is False
    assert ('start', world.ids['A']) in deps.calls and ('ready', world.ids['A']) in deps.calls
    assert_original(world.env, world.host_id, world.orig, world.remote)  # A RUNNING again
    _assert_exclusive_end(world)


def test_stop_requested_but_still_active_is_left_running(world):
    _die_inside_stop(world, took_effect=False)
    result, deps = _recover(world)
    assert result is False
    assert ('start', world.ids['A']) not in deps.calls
    op = _op(world.op_id)
    rollback = json.loads(op.instance_outcomes_json)['instances'][str(world.ids['A'])]['rollback']
    assert rollback['ok'] is True and rollback['untouched'] is True and rollback['note'] is None
    assert_original(world.env, world.host_id, world.orig, world.remote)
    _assert_exclusive_end(world)


@pytest.mark.parametrize('rollback', [False, True])
def test_takeover_during_configure_rejects_the_stale_db_write(world, rollback):
    """configure_existing_instance commits through the executor's fence: after a
    takeover, the old worker's python_deps_path write never lands (forward), and
    neither does its rollback clear (rollback)."""
    fail = {('ready', world.ids['A'])} if rollback else set()
    deps = FakeDeps(world.remote, world.locks, fail=fail)
    real_configure = deps.configure
    seen = {}

    def configure(instance_id, runtime, inputs, dependency_path, **kwargs):
        is_rollback = kwargs.get('restore_from_operation') is not None
        if instance_id == world.ids['A'] and is_rollback == rollback:
            seen['before'] = db.session.get(QLInstance, instance_id).python_deps_path
            assert claim_operation(world.op_id, 'job-2') == 2
        return real_configure(instance_id, runtime, inputs, dependency_path, **kwargs)

    deps.configure = configure
    assert upgrade_host_runtime_logic(world.op_id, deps=deps, job_id='job-1') is False
    fresh_worker()
    assert db.session.get(QLInstance, world.ids['A']).python_deps_path == seen['before']
    assert ('start', world.ids['C']) not in deps.calls or rollback
