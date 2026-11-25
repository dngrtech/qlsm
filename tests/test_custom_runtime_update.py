import json
from types import SimpleNamespace

import pytest

from tests.helpers import auth_headers
from tests.runtime_upgrade_harness import (
    Crash, FakeDeps, FakeLocks as WorkerLocks, FakeRemote, make_env, make_host, tree_state,
)
from tests.test_custom_runtime_release import PROVIDER, activate, runtime_package
from tests.test_host_runtime_upgrade_routes import FakeLocks
from ui import db, task_lock
from ui.addons.install import install_addon_zip
from ui.models import HostStatus, InstanceStatus
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.task_logic.host_runtime_upgrade import upgrade_host_runtime_logic
from ui.task_logic.host_runtime_upgrade_recovery import recover_host_runtime_logic, request_recovery


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    packages = tmp_path / 'packages'
    first, old = runtime_package()
    second, new = runtime_package('2.0', metadata={
        'launch_script': 'next.sh', 'required_plugins': ['next_plugin'], 'forced_lan_rate': True,
        'excluded_preloads': ['force_rate.so'],
    }, extra_members=[('next.sh', b'#!/bin/sh\n'), ('plugins/next_plugin.py', b'')])
    with app.app_context():
        install_addon_zip(first, packages)
        install_addon_zip(second, packages)
    activate(app, packages)
    env = make_env(app, tmp_path, monkeypatch)
    locks = FakeLocks()
    for method in ('acquire_lock', 'release_lock', 'acquire_locks', 'release_locks'):
        monkeypatch.setattr(task_lock, method, getattr(locks, method))
    queued = []
    monkeypatch.setattr('ui.tasks.enqueue_task', lambda *a, **kw: queued.append(kw['job_id']))
    with app.app_context():
        host = make_host(env)
        host.provider = 'standalone'
        host.is_standalone = True
        host.runtime = 'custom'
        host.runtime_provider_id = PROVIDER
        host.runtime_plugin_api = 'minqlx'
        host.runtime_release_sha256 = old
        db.session.commit()
        yield SimpleNamespace(host=host, url=f'/api/hosts/{host.id}/custom-runtime-update',
                              headers=auth_headers(app, 'u'), old=old, new=new,
                              packages=packages, locks=locks, queued=queued, env=env)


def preview(client, world):
    response = client.get(world.url, headers=world.headers)
    assert response.status_code == 200, response.data
    return response.get_json()['data']


def confirm(client, world, action='update', **changes):
    data = preview(client, world)
    target = data['target' if action == 'update' else 'rollback']
    body = {'fingerprint': data['fingerprint'], 'action': action, 'target_sha256': target['sha256']}
    return client.post(world.url, headers=world.headers, json={**body, **changes})


def test_preview_and_reserve(app, client, world):
    assert client.get(world.url).status_code == 401
    assert client.post(world.url, json={}).status_code == 401
    data = preview(client, world)
    assert data['eligibility'] == {'enabled': True, 'reason': None}
    assert data['current']['sha256'] == world.old and data['rollback'] is None
    assert data['target'] == {
        'sha256': world.new, 'provider_id': PROVIDER, 'label': 'Fixture runtime',
        'plugin_api': 'minqlx', 'build': '2.0', 'platform': {
            'os_id': 'ubuntu', 'os_version': '24.04', 'arch': 'x86_64', 'python': [3, 12]}}
    assert data['instances'][0] == {'id': world.host.instances[0].id, 'name': 'uh-A', 'status': 'running'}
    assert 'rcon' not in json.dumps(data)
    assert confirm(client, world, target_sha256='f' * 64).status_code == 409
    assert confirm(client, world, action_override='unknown').status_code == 400
    world.host.instances[0].status = InstanceStatus.STOPPED
    db.session.commit()
    assert confirm(client, world, fingerprint=data['fingerprint']).status_code == 409
    world.locks.maintenance = True
    assert confirm(client, world).status_code == 409
    world.locks.maintenance = False
    response = confirm(client, world)
    assert response.status_code == 202, response.data
    op = HostRuntimeUpgradeOperation.query.one()
    assert response.get_json()['data'] == {'operation_id': op.id, 'status': 'configuring'}
    assert op.original_runtime == 'custom' and op.rq_job_id == world.queued[0]
    assert world.host.status == HostStatus.CONFIGURING and world.host.runtime_release_sha256 == world.old
    assert not world.locks.held
    assert client.post(world.url, headers=world.headers, json={
        'action': 'update', 'fingerprint': data['fingerprint'], 'target_sha256': world.new}).status_code == 409


@pytest.mark.parametrize('change', [
    {'plugin_api': 'minqlxtended'},
    {'platform': {'os_id': 'ubuntu', 'os_version': '24.04', 'arch': 'aarch64', 'python': [3, 12]}},
])
def test_incompatible_approved_release_is_unavailable(app, client, world, change):
    package, digest = runtime_package('3.0', metadata=change)
    install_addon_zip(package, world.packages)
    activate(app, world.packages)
    data = preview(client, world)
    assert data['current']['sha256'] == world.old and data['target'] is None and data['reason']
    result = client.post(world.url, headers=world.headers, json={
        'action': 'update', 'fingerprint': data['fingerprint'], 'target_sha256': digest})
    assert result.status_code == 409 and not world.queued



class Remote(FakeDeps):
    def __init__(self, host):
        super().__init__(FakeRemote(host), WorkerLocks())
        self.units = {i.id: f'original {i.port}' for i in host.instances}
        self.original_units = self.units.copy()
        self.staged = []
        self.ever_started = []
        self.faults = set()
        self.crash_after = None

    def custom_step(self, host, action, *, operation_id, fencing_token, instance=None, unit=None, **kwargs):
        iid = instance.id if instance else None
        if self._fenced(operation_id, fencing_token) or 'unreachable' in self.faults:
            return False
        if action == 'stage':
            if 'platform' in self.faults:
                return False
            self.staged.append(kwargs['release'].sha256)
        elif action == 'apply':
            self.units[iid] = unit
        elif action == 'restore':
            self.units[iid] = self.original_units[iid]
        elif action == 'stop':
            self.remote.services[iid]['active'] = False
        elif action == 'start':
            self.remote.services[iid]['active'] = True
            self.ever_started.append(iid)
        elif action == 'receipt':
            return 'closed' if operation_id in self.remote.finalized else 'open'
        elif action == 'finalize':
            if ('finalize', None) in self.faults:
                return False
            self.remote.finalized.append(operation_id)
        if self.crash_after == (action, iid):
            self.crash_after = None
            raise Crash()
        return (action, iid) not in self.faults


def reserve(client, world, action='update'):
    response = confirm(client, world, action)
    assert response.status_code == 202, response.data
    return db.session.get(HostRuntimeUpgradeOperation, response.get_json()['data']['operation_id'])


def run(op, remote):
    return upgrade_host_runtime_logic(op.id, job_id=op.rq_job_id, deps=remote)


def recover(op, remote):
    jid = request_recovery(op.id, deps=remote)
    return recover_host_runtime_logic(op.id, job_id=jid, deps=remote)


def test_update_and_explicit_rollback(app, client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    original = tree_state(world.env.configs)
    assert run(op, remote) is True, op.last_error
    assert op.state == 'succeeded' and world.host.runtime_release_sha256 == world.new
    assert remote.staged == [world.new] and remote.remote.finalized == [op.id]
    a, b, c = world.host.instances
    assert remote.ever_started == [a.id, c.id] and b.status == InstanceStatus.STOPPED
    for unit in remote.units.values():
        assert world.new + '/next.sh' in unit and 'next_plugin' in unit
        assert 'sv_lanForceRate 1' in unit and 'force_rate.so' not in unit
    assert tree_state(world.env.configs) == original
    assert preview(client, world)['rollback']['sha256'] == world.old
    back = reserve(client, world, 'rollback')
    assert run(back, remote) is True
    assert world.host.runtime_release_sha256 == world.old
    assert world.old + '/launch.sh' in remote.units[a.id]
    from datetime import timedelta
    world.host.created_at += timedelta(days=1)
    db.session.commit()
    assert preview(client, world)['rollback'] is None


@pytest.mark.parametrize('failure', ['second-unit', 'readiness', 'crash', 'platform', 'stale-capture'])
def test_failures_preserve_pin_units_and_original_service_set(client, world, failure):
    op = reserve(client, world)
    remote = Remote(world.host)
    a, b, c = world.host.instances
    if failure == 'second-unit':
        remote.faults.add(('apply', b.id))
    elif failure == 'readiness':
        real = remote.wait_ready
        remote.wait_ready = lambda i, t: ((False, 'stale') if world.host.runtime_release_sha256 == world.new
                                         else real(i, t))
    elif failure == 'platform':
        remote.faults.add('platform')
    elif failure == 'stale-capture':
        a.hostname = 'edited since confirmation'
        db.session.commit()
    else:
        remote.crash_after = ('apply', a.id)
        with pytest.raises(Crash):
            run(op, remote)
        assert op.state == 'configuring'
        remote.faults.add('unreachable')
        recover(op, remote)
        assert op.state == 'recovery_required' and world.host.status == HostStatus.ERROR
        remote.faults.clear()
        remote.faults.add(('restore', a.id))
        recover(op, remote)
        assert op.state == 'recovery_required'
        remote.faults.clear()
    if failure == 'crash':
        recover(op, remote)
    else:
        assert run(op, remote) is False
    assert world.host.status == HostStatus.ACTIVE and world.host.runtime_release_sha256 == world.old
    if failure in ('platform', 'stale-capture'):
        assert op.state == 'failed_preparation' and remote.ever_started == []
    else:
        assert op.state == 'rolled_back'
    assert remote.units == remote.original_units
    assert b.id not in remote.ever_started
    assert [remote.service_state(i) for i in (a, b, c)] == ['active', 'inactive', 'active']


def test_empty_host_and_late_forward_job(client, world):
    for i in list(world.host.instances):
        db.session.delete(i)
    db.session.commit()
    op = reserve(client, world)
    remote = Remote(world.host)
    upgrade_host_runtime_logic(op.id, job_id='obsolete', deps=remote)
    assert op.state == 'preparing' and op.fencing_token == 0 and not remote.staged
    assert run(op, remote) is True and remote.staged == [world.new]


def test_finalization_interruption_replays_verified_decision(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    remote.crash_after = ('finalize', None)
    with pytest.raises(Crash):
        run(op, remote)
    assert not op.is_terminal and world.host.status == HostStatus.CONFIGURING
    recover(op, remote)
    assert op.state == 'succeeded'
    assert remote.ever_started == [i.id for i in world.host.instances if i.status == InstanceStatus.RUNNING]


def test_remote_step_passes_only_a_private_unit_path(client, world, monkeypatch):
    from pathlib import Path
    from ui.task_logic import custom_runtime_remote

    op = reserve(client, world)
    private = 'unit with a private rcon credential'
    paths = []
    def runner(host, play, extravars, capture_output, inventory_path):
        assert capture_output and private not in json.dumps(extravars)
        unit = Path(extravars['unit_src'])
        paths.append(unit)
        assert unit.stat().st_mode & 0o777 == 0o600 and unit.read_text() == private
        return True, 'QLSM_CUSTOM_STEP_VERIFIED', ''
    monkeypatch.setattr(custom_runtime_remote, '_run_host_ansible_playbook', runner)
    assert custom_runtime_remote.run_step(world.host, 'apply', operation_id=op.id, fencing_token=1,
                                         endpoint=json.loads(op.inputs_json),
                                         unit=private, instance=world.host.instances[0])
    assert paths and not paths[0].exists()
    monkeypatch.setattr(custom_runtime_remote, '_run_host_ansible_playbook',
                        lambda *a, **kw: (True, 'skipping: no hosts matched', ''))
    assert not custom_runtime_remote.run_step(world.host, 'barrier', operation_id=op.id, fencing_token=1,
                                              endpoint=json.loads(op.inputs_json))


def test_installer_checks_actual_platform_even_for_existing_release(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    args = [sys.executable, str(root / 'ansible/files/install_custom_runtime.py'),
            str(tmp_path / 'unused'), 'a' * 64, str(tmp_path), 'requirements.txt', 'launch.sh', '[]',
            '--platform', json.dumps({'os_id': 'wrong', 'os_version': '1',
                                       'arch': 'x86_64', 'python': [3, 11]})]
    run = subprocess.run(args, capture_output=True, text=True)
    assert run.returncode and 'incompatible with the release platform' in run.stderr


def test_reserved_custom_host_has_accurate_guard_message(client, world):
    from ui.runtime_upgrade_guard import ensure_no_runtime_upgrade, RuntimeUpgradeReserved
    reserve(client, world)
    with pytest.raises(RuntimeUpgradeReserved) as err:
        ensure_no_runtime_upgrade(world.host.id)
    assert 'minqlxtended' not in str(err.value) and 'runtime' in str(err.value).lower()


def test_interrupted_inventory_releases_all_instance_locks(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    remote.crash_after = ('inventory', world.host.instances[0].id)
    with pytest.raises(Crash):
        run(op, remote)
    assert not remote.locks.owners
    recover(op, remote)
    assert op.state == 'failed_preparation' and not remote.ever_started


def test_job_failure_callback_omits_custom_private_error(client, world):
    from ui.task_logic.host_runtime_upgrade_recovery import handle_upgrade_job_failure
    op = reserve(client, world)
    remote = Remote(world.host)
    job = SimpleNamespace(args=[op.id], id=op.rq_job_id)
    handle_upgrade_job_failure(job, Exception, 'a-private-unit-value', deps=remote)
    assert 'a-private-unit-value' not in world.host.logs


def test_all_stopped_hosts_remain_inactive(client, world):
    for i in world.host.instances:
        i.status = InstanceStatus.STOPPED
    db.session.commit()
    op = reserve(client, world)
    remote = Remote(world.host)
    assert run(op, remote)
    assert not remote.ever_started
    assert all(i.status == InstanceStatus.STOPPED for i in world.host.instances)


def test_settings_edited_during_staging_cancel_before_downtime(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    step = remote.custom_step
    def stage_then_edit(host, action, **kwargs):
        ok = step(host, action, **kwargs)
        if action == 'stage':
            host.instances[0].hostname = 'changed during installation'
            db.session.commit()
        return ok
    remote.custom_step = stage_then_edit
    assert run(op, remote) is False
    assert not remote.ever_started and op.state == 'failed_preparation'
    assert world.host.runtime_release_sha256 == world.old


def test_recovery_refuses_to_contact_reassigned_remote_address(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    a = world.host.instances[0]
    remote.crash_after = ('apply', a.id)
    with pytest.raises(Crash):
        run(op, remote)
    world.host.ip_address = '192.0.2.200'
    db.session.commit()
    recover(op, remote)
    assert op.state == 'recovery_required' and world.host.status == HostStatus.ERROR
    assert not remote.ever_started


def test_unreachable_stopped_probe_keeps_preparation_reserved_until_reachable(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    b = world.host.instances[1]
    remote.fail.add(('state', b.id))
    remote.faults.add('unreachable')
    run(op, remote)
    assert op.state == 'recovery_required' and world.host.status == HostStatus.ERROR
    recover(op, remote)
    assert op.state == 'recovery_required' and not remote.ever_started
    remote.fail.clear()
    remote.faults.clear()
    recover(op, remote)
    assert op.state == 'failed_preparation' and world.host.status == HostStatus.ACTIVE
    assert remote.staged == [] and not remote.ever_started


def test_service_reactivated_during_quiescence_blocks_pin_switch(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    first, _, last = world.host.instances
    actions = []
    step = remote.custom_step
    def reactivate(host, action, *, instance=None, **kwargs):
        actions.append(action)
        ok = step(host, action, instance=instance, **kwargs)
        if action == 'stop' and instance.id == last.id:
            remote.remote.services[first.id]['active'] = True
        return ok
    remote.custom_step = reactivate
    run(op, remote)
    assert op.state == 'rolled_back' and 'apply' not in actions
    assert world.host.runtime_release_sha256 == world.old

@pytest.mark.parametrize('closed', [True, False])
def test_finalize_replay_rechecks_state_and_receipt(client, world, closed):
    op = reserve(client, world)
    remote = Remote(world.host)
    first = world.host.instances[0]
    if closed:
        remote.crash_after = ('finalize', None)
        with pytest.raises(Crash):
            run(op, remote)
    else:
        remote.faults.add(('finalize', None))
        run(op, remote)
        remote.faults.clear()
    remote.remote.services[first.id]['active'] = False
    recover(op, remote)
    if closed:
        assert op.state == 'recovery_required' and world.host.status == HostStatus.ERROR
        assert world.host.runtime_release_sha256 == world.new
        assert remote.ever_started.count(first.id) == 1 and remote.remote.finalized == [op.id]
        remote.remote.services[first.id]['active'] = True
        recover(op, remote)
        assert op.state == 'succeeded' and world.host.status == HostStatus.ACTIVE
    else:
        assert op.state == 'rolled_back' and world.host.runtime_release_sha256 == world.old
        assert remote.units == remote.original_units


def test_closed_receipt_requires_pin_and_fresh_status(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    remote.crash_after = ('finalize', None)
    with pytest.raises(Crash):
        run(op, remote)
    world.host.runtime_release_sha256 = world.old
    db.session.commit()
    recover(op, remote)
    assert op.state == 'recovery_required' and world.host.status == HostStatus.ERROR
    world.host.runtime_release_sha256 = world.new
    db.session.commit()
    remote.fail.add(('ready', world.host.instances[0].id))
    recover(op, remote)
    assert op.state == 'recovery_required'
    remote.fail.clear()
    recover(op, remote)
    assert op.state == 'succeeded' and remote.remote.finalized == [op.id]


def test_preparation_recovery_requires_verified_inactivity(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    stopped = world.host.instances[1]
    remote.fail.add(('state', stopped.id))
    run(op, remote)
    remote.fail.clear()
    remote.remote.services[stopped.id]['active'] = True
    recover(op, remote)
    assert op.state == 'recovery_required' and world.host.status == HostStatus.ERROR
    remote.remote.services[stopped.id]['active'] = False
    recover(op, remote)
    assert op.state == 'failed_preparation' and remote.ever_started == []


def test_all_remote_actions_use_one_captured_ssh_endpoint(client, world, monkeypatch):
    from pathlib import Path
    from ui.task_logic import ansible_runner, custom_runtime_remote

    world.host.name = 'all'
    world.host.ssh_port = 2222
    world.host.ssh_user = 'operator'
    world.host.ssh_key_path = '/captured/key'
    db.session.commit()
    op = reserve(client, world)
    snapshot = json.loads(op.inputs_json)
    # A changed live row and unrelated inventory must never select another machine.
    world.host.ip_address = '192.0.2.200'
    world.host.ssh_port = 9999
    world.host.ssh_user = 'unconfirmed'
    world.host.ssh_key_path = '/other/key'
    db.session.commit()
    paths = []
    class Process:
        def __init__(self, cmd, **kwargs):
            source = Path(cmd[cmd.index('-i') + 1])
            assert source.is_file() and source.stat().st_mode & 0o777 == 0o600
            paths.append(source)
            alias = cmd[cmd.index('-l') + 1]
            assert alias != 'all'
            hosts = json.loads(source.read_text())['all']['hosts']
            assert list(hosts) == [alias]
            assert hosts[alias]['ansible_host'] == '203.0.113.9'
            assert hosts[alias]['ansible_port'] == 2222
            assert hosts[alias]['ansible_user'] == 'operator'
            assert hosts[alias]['ansible_ssh_private_key_file'] == '/captured/key'
            extra = json.loads(cmd[cmd.index('-e') + 1])
            assert extra['target_host_name'] == alias and 'unconfirmed' not in json.dumps(extra)
        def communicate(self):
            return 'QLSM_CUSTOM_STEP_VERIFIED', ''
        def wait(self):
            return 0
    monkeypatch.setattr(ansible_runner.subprocess, 'Popen', Process)
    for action in ('stop', 'finalize'):
        assert custom_runtime_remote.run_step(world.host, action, operation_id=op.id, fencing_token=1,
                                              endpoint=snapshot, instance=world.host.instances[0])
    assert len(paths) == 2 and all(not path.exists() for path in paths)


def test_closed_rollback_receipt_requires_original_readiness(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    a, b, _ = world.host.instances
    remote.faults.add(('apply', b.id))
    remote.crash_after = ('finalize', None)
    with pytest.raises(Crash):
        run(op, remote)
    assert remote.units == remote.original_units and world.host.runtime_release_sha256 == world.old
    remote.fail.add(('ready', a.id))
    recover(op, remote)
    assert op.state == 'recovery_required' and world.host.status == HostStatus.ERROR
    remote.fail.clear()
    recover(op, remote)
    assert op.state == 'rolled_back' and remote.remote.finalized == [op.id]


def test_earlier_service_lost_during_last_start_rolls_back_before_close(client, world):
    op = reserve(client, world)
    remote = Remote(world.host)
    first, stopped, last = world.host.instances
    step = remote.custom_step
    pins_at_close = []

    def lose_first_service(host, action, *, instance=None, **kwargs):
        if action == 'finalize':
            pins_at_close.append(host.runtime_release_sha256)
        result = step(host, action, instance=instance, **kwargs)
        if action == 'start' and instance.id == last.id and host.runtime_release_sha256 == world.new:
            remote.remote.services[first.id]['active'] = False
        return result

    remote.custom_step = lose_first_service
    run(op, remote)
    assert pins_at_close == [world.old]
    assert op.state == 'rolled_back' and world.host.status == HostStatus.ACTIVE
    assert world.host.runtime_release_sha256 == world.old and remote.units == remote.original_units
    assert [remote.service_state(i) for i in (first, stopped, last)] == ['active', 'inactive', 'active']
