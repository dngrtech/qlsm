import pytest
from unittest.mock import patch, MagicMock
from tests.helpers import make_user, auth_headers
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui import db
from ui.database import create_host

DEFAULT_USER = 'setupadmin'
DEFAULT_PASS = 'setupadminp1'


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


def _add_instances(host_id, host_name, count=2):
    instances = [
        QLInstance(
            name=f'{host_name}-instance-{index}',
            hostname=f'{host_name} server {index}',
            port=27960 + index,
            host_id=host_id,
            status=InstanceStatus.RUNNING,
        )
        for index in range(count)
    ]
    db.session.add_all(instances)
    db.session.commit()
    return [instance.id for instance in instances]


@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_locks', return_value=True)
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_rerun_setup_cloud_host_success(
    mock_lock, mock_locks, mock_enqueue, client, app
):
    with app.app_context():
        host = create_host(name='rerun-cloud', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id
        instance_ids = _add_instances(host_id, host.name)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/rerun-setup', headers=headers)

    assert response.status_code == 202
    data = response.get_json()
    assert data['data']['status'] == 'configuring'
    mock_enqueue.assert_called_once()
    lock_token = mock_lock.call_args.args[2]
    mock_lock.assert_called_once_with('host', host_id, lock_token, ttl=3660)
    mock_locks.assert_called_once_with(
        'instance', instance_ids, lock_token, 3660,
    )
    enqueue_args, enqueue_kwargs = mock_enqueue.call_args
    assert enqueue_args[0].__name__ == 'rerun_host_setup_ansible'
    assert enqueue_kwargs['lock_token'] == lock_token
    assert enqueue_kwargs['locked_instance_ids'] == instance_ids

    with app.app_context():
        h = db.session.get(Host, host_id)
        assert h.status == HostStatus.CONFIGURING


@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_locks', return_value=True)
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_rerun_setup_standalone_host_success(
    mock_lock, mock_locks, mock_enqueue, client, app
):
    with app.app_context():
        host = create_host(name='rerun-sa', provider='standalone', status=HostStatus.ACTIVE,
                           is_standalone=True)
        host_id = host.id
        instance_ids = _add_instances(host_id, host.name)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/rerun-setup', headers=headers)

    assert response.status_code == 202
    mock_enqueue.assert_called_once()
    lock_token = mock_lock.call_args.args[2]
    mock_lock.assert_called_once_with('host', host_id, lock_token, ttl=1260)
    mock_locks.assert_called_once_with(
        'instance', instance_ids, lock_token, 1260,
    )
    enqueue_args, enqueue_kwargs = mock_enqueue.call_args
    assert enqueue_args[0].__name__ == 'rerun_standalone_host_setup'
    assert enqueue_kwargs['lock_token'] == lock_token
    assert enqueue_kwargs['locked_instance_ids'] == instance_ids


def test_rerun_setup_rejects_non_active_host(client, app):
    with app.app_context():
        host = create_host(name='rerun-busy', provider='vultr', status=HostStatus.CONFIGURING)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/rerun-setup', headers=headers)

    assert response.status_code == 409
    assert 'ACTIVE' in response.get_json()['error']['message']


def test_rerun_setup_rejects_unauthenticated(client, app):
    with app.app_context():
        host = create_host(name='rerun-unauth', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    response = client.post(f'/api/hosts/{host_id}/rerun-setup')
    assert response.status_code == 401


def test_rerun_setup_404_for_missing_host(client, app):
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/99999/rerun-setup', headers=headers)
    assert response.status_code == 404


@patch('ui.routes.host_routes.release_lock')
@patch('ui.routes.host_routes.release_locks')
@patch('ui.routes.host_routes.enqueue_task', side_effect=RuntimeError('redis down'))
@patch('ui.routes.host_routes.acquire_locks', return_value=True)
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_rerun_setup_reverts_status_on_enqueue_failure(
    mock_lock,
    mock_locks,
    mock_enqueue,
    mock_release_locks,
    mock_release,
    client,
    app,
):
    """On enqueue failure the host must revert from CONFIGURING back to ACTIVE
    so it isn't stuck waiting for the lock TTL."""
    with app.app_context():
        host = create_host(name='rerun-fail', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id
        instance_ids = _add_instances(host_id, host.name, count=1)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/rerun-setup', headers=headers)

    assert response.status_code == 500
    with app.app_context():
        h = db.session.get(Host, host_id)
        assert h.status == HostStatus.ACTIVE
    lock_token = mock_lock.call_args.args[2]
    mock_locks.assert_called_once_with(
        'instance', instance_ids, lock_token, 3660,
    )
    mock_release_locks.assert_called_once_with(
        'instance', instance_ids, lock_token,
    )
    mock_release.assert_called_once_with('host', host_id, lock_token)


@pytest.mark.parametrize('original_status', [HostStatus.ACTIVE, HostStatus.ERROR])
def test_rerun_setup_restores_status_when_an_instance_lock_is_busy(
    original_status, client, app
):
    with app.app_context():
        host = create_host(
            name='rerun-instance-busy',
            provider='vultr',
            status=original_status,
        )
        host_id = host.id
        instance_ids = _add_instances(host_id, host.name, count=2)

    headers = auth_headers(app, DEFAULT_USER)
    with patch('ui.routes.host_routes.enqueue_task') as mock_enqueue, \
         patch('ui.routes.host_routes.release_lock') as mock_release, \
         patch('ui.routes.host_routes.release_locks') as mock_release_locks, \
         patch('ui.routes.host_routes.acquire_locks', return_value=False) as mock_locks, \
         patch('ui.routes.host_routes.acquire_lock', return_value=True) as mock_lock:
        response = client.post(
            f'/api/hosts/{host_id}/rerun-setup',
            headers=headers,
        )

    assert response.status_code == 409
    assert response.get_json() == {
        'error': {
            'message': (
                'One or more instances are busy. Wait for active instance '
                'operations to finish before re-running host setup.'
            ),
        },
    }
    with app.app_context():
        assert db.session.get(Host, host_id).status == original_status

    lock_token = mock_lock.call_args.args[2]
    mock_locks.assert_called_once_with(
        'instance', instance_ids, lock_token, 3660,
    )
    mock_release_locks.assert_called_once_with(
        'instance', instance_ids, lock_token,
    )
    mock_release.assert_called_once_with('host', host_id, lock_token)
    mock_enqueue.assert_not_called()
