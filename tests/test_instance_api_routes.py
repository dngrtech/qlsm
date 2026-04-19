import pytest
from unittest.mock import patch
from flask_jwt_extended import create_access_token
from ui.models import QLInstance, Host, HostStatus, InstanceStatus
from ui import db
from ui.database import create_instance, create_host

def test_update_instance_hostname(client, app):
    """
    GIVEN an existing instance
    WHEN PUT /api/instances/<id> is called with a new hostname
    THEN the instance hostname is updated in the database
    """
    # Create test data
    with app.app_context():
        host = create_host(name='api-test-host', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(name='api-test-inst', host_id=host.id, port=27960, hostname='old.hostname.com')
        db.session.commit()
        instance_id = instance.id

        # Generate Token
        token = create_access_token(identity='testuser')

    # Make Request
    headers = {'Authorization': f'Bearer {token}'}
    data = {'hostname': 'new.hostname.com'}
    
    # Note: URL is /api/instances/<id> because of blueprint registration
    response = client.put(f'/api/instances/{instance_id}', json=data, headers=headers)

    # Debug failure if any
    if response.status_code != 200:
        print(f"Response Body: {response.data}")

    assert response.status_code == 200
    assert response.json['message'] == 'Instance details updated successfully.'
    assert response.json['data']['hostname'] == 'new.hostname.com'

    # Verify DB
    with app.app_context():
        updated = db.session.get(QLInstance, instance_id)
        assert updated.hostname == 'new.hostname.com'

def test_update_instance_name_and_hostname(client, app):
    """
    GIVEN an existing instance
    WHEN PUT /api/instances/<id> is called with a new name AND hostname
    THEN both are updated
    """
    # Create test data
    with app.app_context():
        host = create_host(name='api-test-host-2', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(name='api-test-inst-2', host_id=host.id, port=27961, hostname='old.hostname.com')
        db.session.commit()
        instance_id = instance.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {'name': 'renamed-inst', 'hostname': 'renamed.hostname.com'}

    response = client.put(f'/api/instances/{instance_id}', json=data, headers=headers)

    assert response.status_code == 200
    assert response.json['data']['name'] == 'renamed-inst'
    assert response.json['data']['hostname'] == 'renamed.hostname.com'

    with app.app_context():
        updated = db.session.get(QLInstance, instance_id)
        assert updated.name == 'renamed-inst'
        assert updated.hostname == 'renamed.hostname.com'


def test_view_instance_includes_host_os_type(client, app):
    """GET /api/instances/<id> should include host_os_type in the payload."""
    with app.app_context():
        host = create_host(
            name='ubuntu-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
        )
        instance = create_instance(
            name='inst-os',
            host_id=host.id,
            port=27960,
            hostname='test.hostname',
        )
        db.session.commit()
        instance_id = instance.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    response = client.get(f'/api/instances/{instance_id}', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data']['host_os_type'] == 'ubuntu'


@patch('ui.routes.instance_routes.enqueue_task')
def test_add_instance_rejects_when_host_has_4_instances(mock_enqueue, client, app, tmp_path, monkeypatch):
    """POST /api/instances must return 400 when the host already has 4 instances."""
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        host = create_host(name='full-host', provider='vultr', status=HostStatus.ACTIVE)
        for port in [27960, 27961, 27962, 27963]:
            create_instance(name=f'inst-{port}', host_id=host.id, port=port, hostname='test.host')
        db.session.commit()
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'name': 'fifth-instance',
        'host_id': host_id,
        'port': 27964,
        'hostname': 'test.host',
        'configs': {'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': ''},
    }

    response = client.post('/api/instances/', json=payload, headers=headers)

    assert response.status_code == 400
    assert 'maximum of 4 instances' in response.get_json()['error']['message']
    mock_enqueue.assert_not_called()


@patch('ui.routes.instance_routes.enqueue_task')
def test_add_instance_rejects_invalid_checked_plugins_before_creating_side_effects(
    mock_enqueue, client, app, tmp_path, monkeypatch
):
    """POST /api/instances must fail before creating rows/files when checked_plugins is invalid."""
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        host = create_host(name='api-create-host', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'name': 'new-instance',
        'host_id': host_id,
        'port': 27970,
        'hostname': 'test.hostname',
        'configs': {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
        },
        'checked_plugins': ['my-plugin'],
    }

    response = client.post('/api/instances/', json=payload, headers=headers)

    assert response.status_code == 400
    assert 'qlx_plugins contains invalid characters' in response.get_json()['error']['message']
    mock_enqueue.assert_not_called()

    with app.app_context():
        assert QLInstance.query.count() == 0

    assert not (tmp_path / 'configs' / 'api-create-host').exists()
