import pytest
from unittest.mock import patch, MagicMock
from tests.helpers import make_user, auth_headers
from ui.models import Host, HostStatus
from ui import db
from ui.database import create_host

DEFAULT_USER = 'setupadmin'
DEFAULT_PASS = 'setupadminp1'


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_rerun_setup_cloud_host_success(mock_lock, mock_enqueue, client, app):
    with app.app_context():
        host = create_host(name='rerun-cloud', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/rerun-setup', headers=headers)

    assert response.status_code == 202
    data = response.get_json()
    assert data['data']['status'] == 'configuring'
    mock_enqueue.assert_called_once()

    with app.app_context():
        h = db.session.get(Host, host_id)
        assert h.status == HostStatus.CONFIGURING


@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_rerun_setup_standalone_host_success(mock_lock, mock_enqueue, client, app):
    with app.app_context():
        host = create_host(name='rerun-sa', provider='standalone', status=HostStatus.ACTIVE,
                           is_standalone=True)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/rerun-setup', headers=headers)

    assert response.status_code == 202
    mock_enqueue.assert_called_once()


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
@patch('ui.routes.host_routes.enqueue_task', side_effect=RuntimeError('redis down'))
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_rerun_setup_reverts_status_on_enqueue_failure(mock_lock, mock_enqueue, mock_release, client, app):
    """On enqueue failure the host must revert from CONFIGURING back to ACTIVE
    so it isn't stuck waiting for the lock TTL."""
    with app.app_context():
        host = create_host(name='rerun-fail', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/rerun-setup', headers=headers)

    assert response.status_code == 500
    with app.app_context():
        h = db.session.get(Host, host_id)
        assert h.status == HostStatus.ACTIVE
