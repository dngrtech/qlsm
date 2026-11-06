"""Pending (not yet restarted) instance changes: diff recording, clearing,
the pending-changes API and the defer-restarts setting."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus, InstanceStatus, PendingInstanceChange, QLInstance
from ui.pending_changes import (
    MAX_DIFF_CHARS,
    SOURCE_CONFIG_SAVE,
    clear_pending_changes,
    diff_snapshots,
    list_pending_changes,
    record_pending_change,
    snapshot_dir,
)


def _configs(**overrides):
    configs = {'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': ''}
    configs.update(overrides)
    return configs


@pytest.fixture
def headers(app):
    with app.app_context():
        return {'Authorization': f"Bearer {create_access_token(identity='testuser')}"}


@pytest.fixture
def running_instance(app):
    with app.app_context():
        host = create_host(name='pending-host', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(name='pending-inst', host_id=host.id, port=27960, hostname='Pending')
        instance.status = InstanceStatus.RUNNING
        db.session.commit()
        return SimpleNamespace(id=instance.id, host_name=host.name)


# --- snapshot / diff -------------------------------------------------------

def test_diff_reports_added_modified_removed_and_binary(tmp_path):
    base = tmp_path / 'inst'
    (base / 'scripts').mkdir(parents=True)
    (base / 'server.cfg').write_text('set sv_hostname "a"\nset g_gametype 1\n')
    (base / 'old.cfg').write_text('gone\n')
    (base / 'scripts' / 'hook.so').write_bytes(b'\x7fELF\x00\x01')
    before = snapshot_dir(str(base))

    (base / 'server.cfg').write_text('set sv_hostname "b"\nset g_gametype 1\n')
    (base / 'old.cfg').unlink()
    (base / 'new.cfg').write_text('fresh\n')
    (base / 'scripts' / 'hook.so').write_bytes(b'\x7fELF\x00\x02')
    after = snapshot_dir(str(base))

    changes = {c['path']: c for c in diff_snapshots(before, after)}

    assert set(changes) == {'server.cfg', 'old.cfg', 'new.cfg', 'scripts/hook.so'}
    assert changes['server.cfg']['change'] == 'modified'
    assert '-set sv_hostname "a"' in changes['server.cfg']['diff']
    assert '+set sv_hostname "b"' in changes['server.cfg']['diff']
    assert changes['old.cfg']['change'] == 'removed'
    assert changes['new.cfg']['change'] == 'added'
    assert '+fresh' in changes['new.cfg']['diff']
    hook = changes['scripts/hook.so']
    assert hook['binary'] is True and hook['diff'] is None
    assert hook['sha256_before'] != hook['sha256_after']


def test_unchanged_files_are_not_reported(tmp_path):
    (tmp_path / 'server.cfg').write_text('same\n')
    snap = snapshot_dir(str(tmp_path))
    assert diff_snapshots(snap, snapshot_dir(str(tmp_path))) == []


def test_large_diff_is_truncated(tmp_path):
    (tmp_path / 'big.cfg').write_text('')
    before = snapshot_dir(str(tmp_path))
    (tmp_path / 'big.cfg').write_text(''.join(f'set line{i} "{i}"\n' for i in range(5000)))
    [change] = diff_snapshots(before, snapshot_dir(str(tmp_path)))
    assert change['truncated'] is True
    assert len(change['diff']) == MAX_DIFF_CHARS


# --- config save -----------------------------------------------------------

def _put_config(client, headers, instance_id, payload):
    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')) as enqueue:
        response = client.put(f'/api/instances/{instance_id}/config', json=payload, headers=headers)
    assert response.status_code == 202, response.get_json()
    return enqueue


def test_save_without_restart_records_diff_and_accumulates(
    client, app, headers, running_instance, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    instance_dir = tmp_path / 'configs' / running_instance.host_name / str(running_instance.id)
    instance_dir.mkdir(parents=True)
    (instance_dir / 'server.cfg').write_text('set g_gametype 1\n')

    _put_config(client, headers, running_instance.id, {
        'configs': _configs(**{'server.cfg': 'set g_gametype 4\n'}),
        'hostname': 'Renamed',
        'restart': False,
    })
    _put_config(client, headers, running_instance.id, {
        'configs': _configs(**{'server.cfg': 'set g_gametype 4\n', 'extra.cfg': 'x\n'}),
        'restart': False,
    })

    response = client.get(f'/api/instances/{running_instance.id}/pending-changes', headers=headers)
    assert response.status_code == 200
    entries = response.get_json()['data']['entries']
    assert len(entries) == 2

    first = {f['path']: f for f in entries[0]['files']}
    assert entries[0]['source'] == SOURCE_CONFIG_SAVE
    assert '+set g_gametype 4' in first['server.cfg']['diff']
    assert {'field': 'hostname', 'before': 'Pending', 'after': 'Renamed'} in entries[0]['settings']

    second = {f['path']: f for f in entries[1]['files']}
    assert 'server.cfg' not in second
    assert second['extra.cfg']['change'] == 'added'


def test_save_with_restart_records_nothing(client, app, headers, running_instance, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _put_config(client, headers, running_instance.id, {
        'configs': _configs(**{'server.cfg': 'set g_gametype 4\n'}),
        'restart': True,
    })
    with app.app_context():
        assert list_pending_changes(running_instance.id) == []


def test_save_on_stopped_instance_records_nothing(client, app, headers, running_instance, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        db.session.get(QLInstance, running_instance.id).status = InstanceStatus.STOPPED
        db.session.commit()
    _put_config(client, headers, running_instance.id, {
        'configs': _configs(**{'server.cfg': 'set g_gametype 4\n'}),
        'restart': False,
    })
    with app.app_context():
        assert list_pending_changes(running_instance.id) == []


def test_pending_changes_404_for_unknown_instance(client, headers):
    assert client.get('/api/instances/99999/pending-changes', headers=headers).status_code == 404


# --- clearing --------------------------------------------------------------

def test_deleting_instance_drops_its_records(app, running_instance):
    with app.app_context():
        record_pending_change(running_instance.id, SOURCE_CONFIG_SAVE, [{'path': 'a.cfg'}])
        db.session.commit()
        db.session.delete(db.session.get(QLInstance, running_instance.id))
        db.session.commit()
        assert PendingInstanceChange.query.count() == 0


def test_runtime_promotion_clears_records(app, running_instance):
    from ui.task_logic.instance_runtime_reconciliation import reconcile_runtime_observations
    from ui.task_logic.service_runtime import RuntimeObservation

    with app.app_context():
        instance = db.session.get(QLInstance, running_instance.id)
        instance.status = InstanceStatus.UPDATED
        instance.runtime_invocation_id = 'a' * 32
        record_pending_change(instance.id, SOURCE_CONFIG_SAVE, [{'path': 'a.cfg'}])
        db.session.commit()

        observation = RuntimeObservation(
            status={'map': 'campgrounds', 'players': [], 'updated': 1_786_320_010},
            invocation_id='b' * 32,
            active=True,
            service_started_at=1_786_320_000,
        )
        assert reconcile_runtime_observations([instance], {'27960': observation}) == 1

        db.session.expire_all()
        assert db.session.get(QLInstance, instance.id).status is InstanceStatus.RUNNING
        assert list_pending_changes(instance.id) == []


def test_unchanged_runtime_keeps_records(app, running_instance):
    from ui.task_logic.instance_runtime_reconciliation import reconcile_runtime_observations
    from ui.task_logic.service_runtime import RuntimeObservation

    with app.app_context():
        instance = db.session.get(QLInstance, running_instance.id)
        instance.status = InstanceStatus.UPDATED
        instance.runtime_invocation_id = 'a' * 32
        record_pending_change(instance.id, SOURCE_CONFIG_SAVE, [{'path': 'a.cfg'}])
        db.session.commit()

        observation = RuntimeObservation(
            status={'map': 'campgrounds', 'players': [], 'updated': 1_786_320_010},
            invocation_id='a' * 32,
            active=True,
            service_started_at=1_786_320_000,
        )
        reconcile_runtime_observations([instance], {'27960': observation})
        assert len(list_pending_changes(instance.id)) == 1


@pytest.mark.parametrize('restart, cleared', [(True, True), (False, False)])
def test_apply_config_clears_records_only_with_restart(monkeypatch, app, restart, cleared):
    from ui.task_logic import ansible_instance_mgmt, service_runtime
    from ui.task_logic.ansible_runner import SimpleAnsibleResult

    ctx = app.app_context()
    ctx.push()
    instance = MagicMock(spec=QLInstance)
    instance.id = 12
    instance.port = 27960
    instance.status = InstanceStatus.RUNNING
    instance.host = MagicMock()
    instance.lan_rate_enabled = False
    session = MagicMock()
    session.get.return_value = instance
    monkeypatch.setattr(ansible_instance_mgmt.db, 'session', session)
    monkeypatch.setattr(ansible_instance_mgmt, 'get_current_job', MagicMock(return_value=None))
    monkeypatch.setattr(ansible_instance_mgmt, 'append_log', MagicMock())
    monkeypatch.setattr(ansible_instance_mgmt, '_prepare_instance_zmq', MagicMock())
    monkeypatch.setattr(ansible_instance_mgmt, 'ensure_instance_cpu_affinity', MagicMock(return_value=None))
    monkeypatch.setattr(ansible_instance_mgmt, '_build_qlds_args_string', MagicMock(return_value='args'))
    monkeypatch.setattr(ansible_instance_mgmt, '_build_ld_preload_paths', MagicMock(return_value=''))
    monkeypatch.setattr(ansible_instance_mgmt, 'with_self_host_network_extravars', lambda _i, extra: extra)
    monkeypatch.setattr(ansible_instance_mgmt, 'runtime_extravars', MagicMock(return_value={}))
    monkeypatch.setattr(ansible_instance_mgmt, '_addon_contributions', MagicMock())
    monkeypatch.setattr(
        ansible_instance_mgmt, '_run_ansible_playbook',
        MagicMock(return_value=(SimpleAnsibleResult(0, 'ok', ''), None)),
    )
    monkeypatch.setattr(service_runtime, 'probe_instance_invocation_id', MagicMock(return_value='b' * 32))
    monkeypatch.setattr('ui.task_logic.access_permission_sync.write_and_report_admin_levels', MagicMock())
    clear = MagicMock()
    monkeypatch.setattr(ansible_instance_mgmt, 'clear_pending_changes', clear)

    try:
        ansible_instance_mgmt.apply_instance_config_logic(12, restart=restart)
    finally:
        monkeypatch.undo()
        ctx.pop()

    assert clear.called is cleared


def test_restart_clears_records(monkeypatch, app):
    from ui.task_logic import ansible_instance_mgmt
    from ui.task_logic.ansible_runner import SimpleAnsibleResult

    ctx = app.app_context()
    ctx.push()
    instance = MagicMock(spec=QLInstance)
    instance.id = 12
    instance.port = 27960
    instance.status = InstanceStatus.UPDATED
    instance.host = MagicMock()
    session = MagicMock()
    session.get.return_value = instance
    monkeypatch.setattr(ansible_instance_mgmt.db, 'session', session)
    monkeypatch.setattr(ansible_instance_mgmt, 'get_current_job', MagicMock(return_value=MagicMock(id='j')))
    monkeypatch.setattr(ansible_instance_mgmt, 'append_log', MagicMock())
    monkeypatch.setattr(ansible_instance_mgmt, '_prepare_instance_zmq', MagicMock())
    monkeypatch.setattr(ansible_instance_mgmt, 'ensure_instance_cpu_affinity', MagicMock(return_value=None))
    monkeypatch.setattr(ansible_instance_mgmt, '_build_qlds_args_string', MagicMock(return_value='args'))
    monkeypatch.setattr(ansible_instance_mgmt, '_build_ld_preload_paths', MagicMock(return_value=''))
    monkeypatch.setattr(ansible_instance_mgmt, 'with_self_host_network_extravars', lambda _i, extra: extra)
    monkeypatch.setattr(ansible_instance_mgmt, 'runtime_extravars', MagicMock(return_value={}))
    monkeypatch.setattr(
        ansible_instance_mgmt, '_run_ansible_playbook',
        MagicMock(return_value=(SimpleAnsibleResult(0, 'ok', ''), None)),
    )
    clear = MagicMock()
    monkeypatch.setattr(ansible_instance_mgmt, 'clear_pending_changes', clear)

    try:
        ansible_instance_mgmt.restart_instance_logic(12)
    finally:
        monkeypatch.undo()
        ctx.pop()

    clear.assert_called_once_with(12)
    assert instance.status is InstanceStatus.RUNNING


def test_clear_pending_changes_only_touches_one_instance(app, running_instance):
    with app.app_context():
        other_host = create_host(name='other-host', provider='vultr', status=HostStatus.ACTIVE)
        other = create_instance(name='other-inst', host_id=other_host.id, port=27961, hostname='Other')
        record_pending_change(running_instance.id, SOURCE_CONFIG_SAVE, [{'path': 'a.cfg'}])
        record_pending_change(other.id, SOURCE_CONFIG_SAVE, [{'path': 'b.cfg'}])
        db.session.commit()

        clear_pending_changes(running_instance.id)
        db.session.commit()

        assert list_pending_changes(running_instance.id) == []
        assert len(list_pending_changes(other.id)) == 1


# --- plugin update without restart ----------------------------------------

def test_plugin_update_without_restart_records_and_syncs(app, tmp_path, monkeypatch, running_instance):
    from ui.task_logic.ansible_plugin_update import apply_plugin_updates_logic

    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    pool.mkdir(parents=True)
    (pool / 'sample_plugin.py').write_text('VERSION = 2\n')
    scripts = tmp_path / 'configs' / running_instance.host_name / str(running_instance.id) / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'sample_plugin.py').write_text('VERSION = 1\n')

    with app.app_context():
        host_id = db.session.get(QLInstance, running_instance.id).host_id
        with patch('ui.task_logic.ansible_plugin_update.get_current_job'), \
             patch('ui.task_logic.ansible_plugin_update.acquire_lock', return_value=True), \
             patch('ui.tasks.enqueue_task') as enqueue, \
             patch('ui.tasks.restart_instance.queue') as restart_queue:
            assert apply_plugin_updates_logic(
                host_id, False, {running_instance.id: ['sample_plugin.py']}, []
            ) is True

        restart_queue.assert_not_called()
        enqueue.assert_called_once()
        assert enqueue.call_args.kwargs['restart'] is False

        [entry] = list_pending_changes(running_instance.id)
        [change] = entry['files']
        assert entry['source'] == 'plugin_update'
        assert change['path'] == 'scripts/sample_plugin.py'
        assert '+VERSION = 2' in change['diff']


def test_plugin_update_with_restart_records_nothing(app, tmp_path, monkeypatch, running_instance):
    from ui.task_logic.ansible_plugin_update import apply_plugin_updates_logic

    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    pool.mkdir(parents=True)
    (pool / 'sample_plugin.py').write_text('VERSION = 2\n')

    with app.app_context():
        host_id = db.session.get(QLInstance, running_instance.id).host_id
        with patch('ui.task_logic.ansible_plugin_update.get_current_job'), \
             patch('ui.tasks.enqueue_task') as enqueue, \
             patch('ui.tasks.restart_instance.queue'):
            apply_plugin_updates_logic(
                host_id, False, {running_instance.id: ['sample_plugin.py']}, [running_instance.id]
            )
        enqueue.assert_not_called()
        assert list_pending_changes(running_instance.id) == []


# --- defer-restarts setting -------------------------------------------------

def test_defer_restarts_defaults_off_and_round_trips(client, headers):
    response = client.get('/api/settings/defer-restarts', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data'] == {'enabled': False}

    response = client.put('/api/settings/defer-restarts', json={'enabled': True}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data'] == {'enabled': True}
    assert client.get('/api/settings/defer-restarts', headers=headers).get_json()['data'] == {'enabled': True}


def test_defer_restarts_rejects_non_boolean(client, headers):
    response = client.put('/api/settings/defer-restarts', json={'enabled': 'yes'}, headers=headers)
    assert response.status_code == 400


def test_defer_restarts_requires_auth(client):
    assert client.get('/api/settings/defer-restarts').status_code == 401


def test_plugin_update_with_identical_file_neither_records_nor_syncs(app, tmp_path, monkeypatch, running_instance):
    from ui.task_logic.ansible_plugin_update import apply_plugin_updates_logic

    monkeypatch.chdir(tmp_path)
    pool = tmp_path / 'ql-assets' / 'data' / 'minqlx-plugins'
    pool.mkdir(parents=True)
    (pool / 'sample_plugin.py').write_text('VERSION = 2\n')
    scripts = tmp_path / 'configs' / running_instance.host_name / str(running_instance.id) / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'sample_plugin.py').write_text('VERSION = 2\n')

    with app.app_context():
        host_id = db.session.get(QLInstance, running_instance.id).host_id
        with patch('ui.task_logic.ansible_plugin_update.get_current_job'), \
             patch('ui.task_logic.ansible_plugin_update.acquire_lock', return_value=True), \
             patch('ui.tasks.enqueue_task') as enqueue, \
             patch('ui.tasks.restart_instance.queue'):
            apply_plugin_updates_logic(host_id, False, {running_instance.id: ['sample_plugin.py']}, [])
        enqueue.assert_not_called()
        assert list_pending_changes(running_instance.id) == []
