from unittest.mock import MagicMock, patch

from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus, InstanceStatus, QLInstance
from tests.helpers import auth_headers


def _instance_payload(host_id, lan_rate_enabled):
    return {
        'name': 'lan-rate-instance',
        'host_id': host_id,
        'port': 27960,
        'hostname': 'test.hostname',
        'lan_rate_enabled': lan_rate_enabled,
        'configs': {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
        },
    }


@patch('ui.routes.instance_routes.enqueue_task')
def test_add_instance_rejects_ubuntu_lan_rate_enable(
    mock_enqueue, client, app, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        host = create_host(
            name='ubuntu-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
        )
        host_id = host.id

    response = client.post(
        '/api/instances/',
        json=_instance_payload(host_id, True),
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code == 400
    assert "99k LAN Rate currently requires Debian on this host" in response.get_json()['error']['message']
    mock_enqueue.assert_not_called()

    with app.app_context():
        assert QLInstance.query.count() == 0


@patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1'))
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
def test_add_instance_allows_debian_lan_rate_enable(
    mock_lock, mock_enqueue, client, app, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        host = create_host(
            name='debian-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='debian',
        )
        host_id = host.id

    response = client.post(
        '/api/instances/',
        json=_instance_payload(host_id, True),
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code == 201
    assert response.get_json()['data']['lan_rate_enabled'] is True
    mock_lock.assert_called_once()
    mock_enqueue.assert_called_once()


@patch('ui.routes.instance_routes.acquire_lock')
def test_update_instance_lan_rate_rejects_enabling_on_ubuntu(mock_lock, client, app):
    with app.app_context():
        host = create_host(
            name='ubuntu-toggle-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
        )
        instance = create_instance(
            name='ubuntu-toggle-inst',
            host_id=host.id,
            port=27961,
            hostname='toggle.host',
            lan_rate_enabled=False,
        )
        instance.status = InstanceStatus.RUNNING
        db.session.commit()
        instance_id = instance.id

    response = client.put(
        f'/api/instances/{instance_id}/lan-rate',
        json={'lan_rate_enabled': True},
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code == 400
    assert "99k LAN Rate currently requires Debian on this host" in response.get_json()['error']['message']
    mock_lock.assert_not_called()


@patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-2'))
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
def test_update_instance_lan_rate_allows_disabling_on_ubuntu(
    mock_lock, mock_enqueue, client, app
):
    with app.app_context():
        host = create_host(
            name='ubuntu-disable-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
        )
        instance = create_instance(
            name='ubuntu-disable-inst',
            host_id=host.id,
            port=27962,
            hostname='disable.host',
            lan_rate_enabled=True,
        )
        instance.status = InstanceStatus.RUNNING
        db.session.commit()
        instance_id = instance.id

    response = client.put(
        f'/api/instances/{instance_id}/lan-rate',
        json={'lan_rate_enabled': False},
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code == 202
    assert response.get_json()['data']['lan_rate_enabled'] is False
    mock_lock.assert_called_once()
    mock_enqueue.assert_called_once()


@patch('ui.routes.instance_routes.acquire_lock')
def test_manage_instance_config_rejects_enabling_lan_rate_on_ubuntu(
    mock_lock, client, app, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        host = create_host(
            name='ubuntu-config-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
        )
        instance = create_instance(
            name='ubuntu-config-inst',
            host_id=host.id,
            port=27963,
            hostname='config.host',
            lan_rate_enabled=False,
        )
        db.session.commit()
        instance_id = instance.id

    response = client.put(
        f'/api/instances/{instance_id}/config',
        json={'configs': {'server.cfg': 'updated'}, 'lan_rate_enabled': True, 'restart': True},
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code == 400
    assert "99k LAN Rate currently requires Debian on this host" in response.get_json()['error']['message']
    mock_lock.assert_not_called()


# ---------------------------------------------------------------------------
# Migrated-host tests (lan_rate_uses_hook=True bypasses OS restriction)
# ---------------------------------------------------------------------------

@patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-m1'))
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
def test_add_instance_allows_lan_rate_on_migrated_ubuntu_host(
    mock_lock, mock_enqueue, client, app, tmp_path, monkeypatch
):
    """Migrated Ubuntu host: POST /api/instances/ with lan_rate_enabled=True should succeed."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        host = create_host(
            name='migrated-ubuntu-add',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
            lan_rate_uses_hook=True,
        )
        host_id = host.id

    response = client.post(
        '/api/instances/',
        json=_instance_payload(host_id, True),
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code == 201, response.get_json()
    assert response.get_json()['data']['lan_rate_enabled'] is True
    mock_lock.assert_called_once()
    mock_enqueue.assert_called_once()


@patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-m2'))
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
def test_toggle_lan_rate_allowed_on_migrated_ubuntu_host(
    mock_lock, mock_enqueue, client, app
):
    """Migrated Ubuntu host: PUT /api/instances/<id>/lan-rate enable should succeed."""
    with app.app_context():
        host = create_host(
            name='migrated-ubuntu-toggle',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
            lan_rate_uses_hook=True,
        )
        instance = create_instance(
            name='migrated-toggle-inst',
            host_id=host.id,
            port=27964,
            hostname='migrated-toggle.host',
            lan_rate_enabled=False,
        )
        instance.status = InstanceStatus.RUNNING
        db.session.commit()
        instance_id = instance.id

    response = client.put(
        f'/api/instances/{instance_id}/lan-rate',
        json={'lan_rate_enabled': True},
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code == 202, response.get_json()
    assert response.get_json()['data']['lan_rate_enabled'] is True
    mock_lock.assert_called_once()
    mock_enqueue.assert_called_once()


@patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-m3'))
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
def test_manage_config_allows_lan_rate_on_migrated_ubuntu_host(
    mock_lock, mock_enqueue, client, app, tmp_path, monkeypatch
):
    """Migrated Ubuntu host: PUT /api/instances/<id>/config enabling lan_rate should succeed."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        host = create_host(
            name='migrated-ubuntu-config',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
            lan_rate_uses_hook=True,
        )
        instance = create_instance(
            name='migrated-config-inst',
            host_id=host.id,
            port=27965,
            hostname='migrated-config.host',
            lan_rate_enabled=False,
        )
        db.session.commit()
        instance_id = instance.id

    response = client.put(
        f'/api/instances/{instance_id}/config',
        json={
            'configs': {
                'server.cfg': 'updated',
                'mappool.txt': '',
                'access.txt': '',
                'workshop.txt': '',
            },
            'lan_rate_enabled': True,
            'restart': True,
        },
        headers=auth_headers(app, 'testuser'),
    )

    assert response.status_code in (200, 202), response.get_json()
    mock_lock.assert_called_once()
    mock_enqueue.assert_called_once()
