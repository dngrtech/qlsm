"""The runtime-upgrade reservation: every host/instance mutation entry point
refuses with 409 while a nonterminal operation exists; terminal rows never
block; status polling skips the host."""
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import auth_headers
from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.runtime_upgrade_guard import (
    RuntimeUpgradeReserved,
    active_runtime_upgrade,
    ensure_no_runtime_upgrade,
    reserved_host_ids,
)

BLOCKED = 'Host gh is being upgraded to minqlxtended; changes are blocked until it finishes.'


@pytest.fixture
def headers(app):
    return auth_headers(app, 'u')


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # configs/ lookups land in tmp_path
    with app.app_context():
        host = Host(name='gh', provider='vultr', ip_address='1.1.1.1', status=HostStatus.ERROR,
                    runtime='minqlx', os_type='ubuntu', os_version='24.04')
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(name='gi', port=27960, hostname='h', host_id=host.id, qlx_plugins='',
                          status=InstanceStatus.STOPPED, zmq_rcon_port=28888, zmq_rcon_password='r',
                          zmq_stats_port=29999, zmq_stats_password='s')
        db.session.add(inst)
        db.session.commit()
        yield host.id, inst.id


def _reserve(host_id, state='recovery_required'):
    op = HostRuntimeUpgradeOperation(host_id=host_id, state=state)
    db.session.add(op)
    db.session.commit()
    return op


HOST_ROUTES = [
    ('DELETE', '/api/hosts/{h}', None),
    ('PUT', '/api/hosts/{h}', {'name': 'renamed'}),
    ('POST', '/api/hosts/{h}/qlfilter/install', None),
    ('POST', '/api/hosts/{h}/qlfilter/uninstall', None),
    ('POST', '/api/hosts/{h}/qlfilter/refresh-status', None),
    ('POST', '/api/hosts/{h}/restart', None),
    ('POST', '/api/hosts/{h}/resize', {'plan': 'vc2-2c-4gb'}),
    ('POST', '/api/hosts/{h}/rerun-setup', None),
    ('POST', '/api/hosts/{h}/update-workshop', {'workshop_id': '123'}),
    ('POST', '/api/hosts/{h}/plugin-updates/apply', {'apply_common_pool': True}),
    ('POST', '/api/hosts/{h}/auto-restart', {'schedule_cron': ''}),
    ('POST', '/api/hosts/{h}/watchdog', {'enabled': False}),
]

INSTANCE_ROUTES = [
    ('POST', '/api/instances/', {'name': 'new', 'host_id': '{h}', 'port': 27961, 'hostname': 'x'}),
    ('PUT', '/api/instances/{i}', {'name': 'renamed'}),
    ('DELETE', '/api/instances/{i}', None),
    ('POST', '/api/instances/{i}/restart', None),
    ('POST', '/api/instances/{i}/stop', None),
    ('POST', '/api/instances/{i}/start', None),
    ('PUT', '/api/instances/{i}/lan-rate', {'lan_rate_enabled': True}),
    ('PUT', '/api/instances/{i}/config', {'configs': {'server.cfg': 'x'}}),
    ('POST', '/api/instances/{i}/hooks/files', None),
    ('PUT', '/api/instances/{i}/hooks/files/a.so', None),
    ('PATCH', '/api/instances/{i}/hooks/files/a.so', {'new_name': 'b.so'}),
    ('DELETE', '/api/instances/{i}/hooks/files/a.so', None),
    ('PATCH', '/api/instances/{i}/hooks/files/a.so/description', {'description': 'x'}),
    ('PUT', '/api/scripts/content', {'host': 'gh', 'instance_id': '{i}', 'path': 'a.py', 'content': 'x'}),
]


def _fill(value, host_id, instance_id):
    if isinstance(value, str):
        return value.replace('{h}', str(host_id)).replace('{i}', str(instance_id))
    if isinstance(value, dict):
        return {k: _fill(v, host_id, instance_id) for k, v in value.items()}
    return value


def _call(client, headers, method, url, body, host_id, instance_id):
    url = _fill(url, host_id, instance_id)
    body = _fill(body, host_id, instance_id)
    if body is None:
        return client.open(url, method=method, headers=headers)
    if 'host_id' in body:
        body['host_id'] = int(body['host_id'])
    return client.open(url, method=method, headers=headers, json=body)


@pytest.mark.parametrize('method,url,body', HOST_ROUTES + INSTANCE_ROUTES)
def test_mutation_routes_refuse_while_reserved(app, client, headers, world, method, url, body):
    host_id, instance_id = world
    with app.app_context():
        _reserve(host_id)
    response = _call(client, headers, method, url, body, host_id, instance_id)
    assert response.status_code == 409, response.get_json()
    assert response.get_json() == {'error': {'message': BLOCKED}}


def test_script_upload_refuses_while_reserved(app, client, headers, world):
    import io
    host_id, instance_id = world
    with app.app_context():
        _reserve(host_id)
    response = client.post('/api/scripts/upload', headers=headers, content_type='multipart/form-data',
                           data={'host': 'gh', 'instance_id': str(instance_id),
                                 'file': (io.BytesIO(b'x = 1\n'), 'a.py')})
    assert response.status_code == 409
    assert response.get_json() == {'error': {'message': BLOCKED}}


def test_draft_commit_to_instance_refuses_while_reserved(app, client, headers, world):
    host_id, instance_id = world
    with app.app_context():
        _reserve(host_id)
    draft = client.post('/api/drafts/', headers=headers, json={'source': 'instance', 'host': 'gh', 'instance_id': instance_id})
    draft_id = (draft.get_json() or {}).get('data', {}).get('draft_id')
    assert draft_id, draft.get_json()
    response = client.post(f'/api/drafts/{draft_id}/commit', headers=headers,
                           json={'target': 'instance', 'host': 'gh', 'instance_id': instance_id})
    assert response.status_code == 409
    assert response.get_json() == {'error': {'message': BLOCKED}}


@pytest.mark.parametrize('method,url,body', [
    ('POST', '/api/instances/{i}/stop', None),
    ('DELETE', '/api/hosts/{h}', None),
])
def test_terminal_operations_never_block(app, client, headers, world, method, url, body):
    host_id, instance_id = world
    with app.app_context():
        for state in ('succeeded', 'rolled_back', 'failed_preparation'):
            _reserve(host_id, state=state)
    response = _call(client, headers, method, url, body, host_id, instance_id)
    assert (response.get_json() or {}).get('error', {}).get('message') != BLOCKED


def test_status_reads_stay_allowed(app, client, headers, world):
    host_id, instance_id = world
    with app.app_context():
        _reserve(host_id)
    assert client.get(f'/api/hosts/{host_id}', headers=headers).status_code == 200
    assert client.get(f'/api/instances/{instance_id}', headers=headers).status_code == 200


def test_reservation_survives_lock_expiry(app, world):
    """The DB row is the reservation: no Redis lock is consulted."""
    host_id, _ = world
    with app.app_context():
        op = _reserve(host_id, state='configuring')
        assert active_runtime_upgrade(host_id).id == op.id
        assert reserved_host_ids() == {host_id}
        with pytest.raises(RuntimeUpgradeReserved):
            ensure_no_runtime_upgrade(host_id)


def test_terminal_row_for_reused_host_id_does_not_reserve(app, world):
    host_id, _ = world
    with app.app_context():
        _reserve(host_id, state='rolled_back')
        assert active_runtime_upgrade(host_id) is None
        assert reserved_host_ids() == set()
        ensure_no_runtime_upgrade(host_id)


def test_plugin_push_skips_reserved_host(app, world):
    from ui import plugin_push

    host_id, _ = world
    with app.app_context():
        host = db.session.get(Host, host_id)
        host.status = HostStatus.ACTIVE
        _reserve(host_id)
        with patch.object(plugin_push, 'acquire_lock') as lock, \
                patch.object(plugin_push, 'enqueue_task') as enqueue:
            result = plugin_push.push_pool_to_hosts(['minqlx'])
    assert result == {'queued': [], 'skipped': [
        {'id': host_id, 'name': 'gh', 'reason': 'runtime upgrade in progress'}]}
    lock.assert_not_called()
    enqueue.assert_not_called()


def test_addon_playbook_and_task_refused_on_reserved_host(app, world, tmp_path):
    from ui.addons.context import AddonContext

    host_id, instance_id = world
    with app.app_context():
        _reserve(host_id)
        ctx = AddonContext('demo', {}, str(tmp_path))
        host = db.session.get(Host, host_id)
        with patch('ui.task_logic.ansible_runner._run_host_ansible_playbook') as run:
            ok, _out, err = ctx.run_playbook(host, 'x.yml')
        assert ok is False and err == BLOCKED
        run.assert_not_called()

        calls = []

        @ctx.task(lock_scope='instance')
        def touch(instance_id_arg):
            calls.append(instance_id_arg)
            return True

        with patch('ui.task_lock.release_lock'):
            result = touch.helper.wrapped.__wrapped__(instance_id, lock_token='t')
    assert result == BLOCKED
    assert calls == []


def test_poller_skips_reserved_host(app, world):
    from ui.task_logic import server_status_poll

    host_id, instance_id = world
    with app.app_context():
        host = db.session.get(Host, host_id)
        host.ssh_key_path = '/k'
        db.session.get(QLInstance, instance_id).status = InstanceStatus.RUNNING
        db.session.commit()
        _reserve(host_id, state='configuring')
        app.extensions['redis'] = MagicMock()
        with patch.object(server_status_poll, '_fetch_and_cache_host') as fetch:
            server_status_poll.poll_all_hosts()
        fetch.assert_not_called()
        assert db.session.get(Host, host_id).status == HostStatus.ERROR
