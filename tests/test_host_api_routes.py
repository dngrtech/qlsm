import pytest
from unittest.mock import patch, MagicMock
from tests.helpers import make_user, auth_headers
from ui.models import Host, HostStatus, QLFilterStatus, QLInstance, InstanceStatus
from ui import db
from ui.database import create_host, get_host, update_host

DEFAULT_USER = 'hostadmin'
DEFAULT_PASS = 'hostadminp1'


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


# --- GET /api/hosts/ ---

def test_list_hosts_empty(client, app):
    """No hosts returns empty data list."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/hosts/', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data'] == []


def test_list_hosts_with_data(client, app):
    """Returns all hosts."""
    with app.app_context():
        create_host(name='host-a', provider='vultr', status=HostStatus.ACTIVE)
        create_host(name='host-b', provider='vultr', status=HostStatus.PENDING)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/hosts/', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    names = [h['name'] for h in data]
    assert 'host-a' in names
    assert 'host-b' in names


def test_list_hosts_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/hosts/')
    assert response.status_code == 401


# --- POST /api/hosts/ (cloud) ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_create_cloud_host_success(mock_lock, mock_enqueue, client, app):
    """Valid cloud host data creates host and queues provision task."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'cloud-host',
        'provider': 'vultr',
        'region': 'ewr',
        'machine_size': 'vc2-1c-1gb'
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['data']['name'] == 'cloud-host'
    assert 'provisioning task queued' in data['message']
    mock_enqueue.assert_called_once()


def test_create_host_missing_name(client, app):
    """Missing name returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'provider': 'vultr',
        'region': 'ewr',
        'machine_size': 'vc2-1c-1gb'
    })
    assert response.status_code == 400


def test_create_host_missing_provider(client, app):
    """Missing provider returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'no-provider',
        'region': 'ewr',
        'machine_size': 'vc2-1c-1gb'
    })
    assert response.status_code == 400


def test_create_host_invalid_name_chars(client, app):
    """Host name with uppercase/special chars is normalized or rejected."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'UPPERCASE-HOST!',
        'provider': 'vultr',
        'region': 'ewr',
        'machine_size': 'vc2-1c-1gb'
    })
    # Either normalized (201) or rejected (400) - invalid chars should not pass
    assert response.status_code in (201, 400)
    if response.status_code == 400:
        assert 'error' in response.get_json()


def test_create_host_name_too_long(client, app):
    """Host name exceeding 20 chars returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'a' * 21,
        'provider': 'vultr',
        'region': 'ewr',
        'machine_size': 'vc2-1c-1gb'
    })
    assert response.status_code == 400


def test_create_host_duplicate_name(client, app):
    """Duplicate host name returns 409."""
    with app.app_context():
        create_host(name='dup-host', provider='vultr', status=HostStatus.ACTIVE)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'dup-host',
        'provider': 'vultr',
        'region': 'ewr',
        'machine_size': 'vc2-1c-1gb'
    })
    assert response.status_code == 409


def test_create_host_cloud_missing_region(client, app):
    """Cloud host without region returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'no-region',
        'provider': 'vultr',
        'machine_size': 'vc2-1c-1gb'
    })
    assert response.status_code == 400


def test_create_host_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.post('/api/hosts/', json={
        'name': 'ghost-host',
        'provider': 'vultr',
        'region': 'ewr',
        'machine_size': 'vc2-1c-1gb'
    })
    assert response.status_code == 401


def test_create_host_no_body(client, app):
    """No valid JSON body returns 4xx error."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers,
                           data='not json', content_type='text/plain')
    assert response.status_code in (400, 415)


# --- POST /api/hosts/ (standalone) ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
@patch('ui.routes.host_routes.os.makedirs')
@patch('ui.routes.host_routes.os.chmod')
@patch('builtins.open', create=True)
def test_create_standalone_host_success(mock_open, mock_chmod, mock_makedirs, mock_lock, mock_enqueue, client, app):
    """Valid standalone host data creates host and queues setup task."""
    mock_open.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_open.return_value.__exit__ = MagicMock(return_value=False)

    with patch('ui.routes.host_routes.os.path.abspath', return_value='/tmp/ssh-keys'):
        headers = auth_headers(app, DEFAULT_USER)
        response = client.post('/api/hosts/', headers=headers, json={
            'name': 'standalone-h',
            'provider': 'standalone',
            'ip_address': '192.168.1.100',
            'ssh_key': '-----BEGIN RSA PRIVATE KEY-----\nfakekey\n-----END RSA PRIVATE KEY-----',
            'ssh_user': 'root',
            'ssh_port': 22,
            'os_type': 'debian12',
            'timezone': 'America/New_York'
        })

    assert response.status_code == 201
    data = response.get_json()
    assert data['data']['name'] == 'standalone-h'
    assert mock_lock.call_args.kwargs['ttl'] == 1260


def test_create_standalone_host_missing_ip(client, app):
    """Standalone host without IP returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'no-ip',
        'provider': 'standalone',
        'ssh_key': 'fakekey',
        'ssh_user': 'root'
    })
    assert response.status_code == 400
    assert 'IP address is required' in response.get_json()['error']['message']


def test_create_standalone_host_invalid_ip(client, app):
    """Standalone host with invalid IP format returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'bad-ip',
        'provider': 'standalone',
        'ip_address': 'not.an.ip.address',
        'ssh_key': 'fakekey',
        'ssh_user': 'root'
    })
    assert response.status_code == 400


def test_create_standalone_host_invalid_port(client, app):
    """Standalone host with port out of range returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'bad-port',
        'provider': 'standalone',
        'ip_address': '10.0.0.1',
        'ssh_key': 'fakekey',
        'ssh_user': 'root',
        'ssh_port': 99999
    })
    assert response.status_code == 400


def test_create_standalone_host_invalid_os_type(client, app):
    """Standalone host with unsupported OS type returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/', headers=headers, json={
        'name': 'bad-os',
        'provider': 'standalone',
        'ip_address': '10.0.0.2',
        'ssh_key': 'fakekey',
        'ssh_user': 'root',
        'os_type': 'windows10'
    })
    assert response.status_code == 400


# --- GET /api/hosts/<id> ---

def test_get_host_success(client, app):
    """Returns host data for existing host."""
    with app.app_context():
        host = create_host(name='view-h', provider='vultr',
                           ip_address='5.5.5.5', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/hosts/{host_id}', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['name'] == 'view-h'
    assert data['ip_address'] == '5.5.5.5'


def test_get_host_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/hosts/99999', headers=headers)
    assert response.status_code == 404


def test_get_host_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/hosts/1')
    assert response.status_code == 401


# --- DELETE /api/hosts/<id> ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_delete_host_success(mock_lock, mock_enqueue, client, app):
    """Deletes cloud host and queues destroy task."""
    with app.app_context():
        host = create_host(name='del-h', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete(f'/api/hosts/{host_id}', headers=headers)
    assert response.status_code == 202
    assert 'deletion task queued' in response.get_json()['message']
    mock_enqueue.assert_called_once()


def test_delete_host_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete('/api/hosts/99999', headers=headers)
    assert response.status_code == 404


def test_delete_host_with_instances_blocked(client, app):
    """Host with active instances returns 409."""
    with app.app_context():
        host = create_host(name='busy-h', provider='vultr', status=HostStatus.ACTIVE)
        instance = QLInstance(name='inst-1', port=27960, hostname='server.example.com', host_id=host.id)
        db.session.add(instance)
        db.session.commit()
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete(f'/api/hosts/{host_id}', headers=headers)
    assert response.status_code == 409
    assert 'associated active' in response.get_json()['error']['message']


@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_delete_host_with_deleting_instances_allowed(mock_lock, mock_enqueue, client, app):
    """Host whose only instances are DELETING can be deleted."""
    with app.app_context():
        host = create_host(name='del-ok', provider='vultr', status=HostStatus.ACTIVE)
        instance = QLInstance(name='inst-del', port=27960, hostname='server.example.com',
                              host_id=host.id, status=InstanceStatus.DELETING)
        db.session.add(instance)
        db.session.commit()
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete(f'/api/hosts/{host_id}', headers=headers)
    assert response.status_code == 202
    mock_enqueue.assert_called_once()


def test_delete_host_with_mixed_instances_blocked(client, app):
    """Host with one DELETING and one RUNNING instance returns 409."""
    with app.app_context():
        host = create_host(name='mixed-h', provider='vultr', status=HostStatus.ACTIVE)
        inst_deleting = QLInstance(name='inst-d', port=27960, hostname='s1.example.com',
                                   host_id=host.id, status=InstanceStatus.DELETING)
        inst_running = QLInstance(name='inst-r', port=27961, hostname='s2.example.com',
                                  host_id=host.id, status=InstanceStatus.RUNNING)
        db.session.add_all([inst_deleting, inst_running])
        db.session.commit()
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete(f'/api/hosts/{host_id}', headers=headers)
    assert response.status_code == 409
    assert 'associated active' in response.get_json()['error']['message']


def test_delete_host_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.delete('/api/hosts/1')
    assert response.status_code == 401


# --- PUT /api/hosts/<id> ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_update_host_name_success(mock_lock, mock_enqueue, client, app):
    """Valid name update renames host and queues rename task."""
    with app.app_context():
        host = create_host(name='old-name', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/hosts/{host_id}', headers=headers, json={
        'name': 'new-name'
    })
    assert response.status_code == 200
    assert response.get_json()['data']['name'] == 'new-name'
    mock_enqueue.assert_called_once()


@patch('ui.routes.host_routes.enqueue_task')
def test_update_host_same_name(mock_enqueue, client, app):
    """Updating to the same name succeeds without queuing rename task."""
    with app.app_context():
        host = create_host(name='same-host', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/hosts/{host_id}', headers=headers, json={
        'name': 'same-host'
    })
    assert response.status_code == 200
    mock_enqueue.assert_not_called()


def test_update_host_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.put('/api/hosts/99999', headers=headers, json={'name': 'x'})
    assert response.status_code == 404


def test_update_host_empty_name(client, app):
    """Empty name returns 400."""
    with app.app_context():
        host = create_host(name='empty-nm', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/hosts/{host_id}', headers=headers, json={'name': ''})
    assert response.status_code == 400


def test_update_host_duplicate_name(client, app):
    """Name already taken by another host returns 409."""
    with app.app_context():
        create_host(name='taken-nm', provider='vultr', status=HostStatus.ACTIVE)
        host2 = create_host(name='to-rename', provider='vultr', status=HostStatus.ACTIVE)
        host2_id = host2.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/hosts/{host2_id}', headers=headers, json={
        'name': 'taken-nm'
    })
    assert response.status_code == 409


def test_update_host_no_valid_fields(client, app):
    """No valid fields to update returns 400."""
    with app.app_context():
        host = create_host(name='no-field', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/hosts/{host_id}', headers=headers, json={
        'unknown_field': 'value'
    })
    assert response.status_code == 400


def test_update_host_no_body(client, app):
    """No valid JSON body returns 4xx error."""
    with app.app_context():
        host = create_host(name='no-body', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/hosts/{host_id}', headers=headers,
                          data='not json', content_type='text/plain')
    assert response.status_code in (400, 415)


def test_update_host_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.put('/api/hosts/1', json={'name': 'x'})
    assert response.status_code == 401


# --- GET /api/hosts/<id>/logs ---

def test_get_host_logs_success(client, app):
    """Returns host logs."""
    log_content = 'Provisioning started...\nDone!'
    with app.app_context():
        host = create_host(name='log-host', provider='vultr',
                           status=HostStatus.ACTIVE, logs=log_content)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/hosts/{host_id}/logs', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data']['logs'] == log_content


def test_get_host_logs_empty(client, app):
    """Host with no logs returns empty string."""
    with app.app_context():
        host = create_host(name='nolog-h', provider='vultr',
                           status=HostStatus.ACTIVE, logs=None)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/hosts/{host_id}/logs', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data']['logs'] == ''


def test_get_host_logs_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/hosts/99999/logs', headers=headers)
    assert response.status_code == 404


def test_get_host_logs_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/hosts/1/logs')
    assert response.status_code == 401


# --- GET /api/hosts/<id>/available-ports ---

def test_get_available_ports_all_free(client, app):
    """Returns all standard ports when no instances exist."""
    with app.app_context():
        host = create_host(name='port-h', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/hosts/{host_id}/available-ports', headers=headers)
    assert response.status_code == 200
    ports = response.get_json()['data']['available_ports']
    assert isinstance(ports, list)
    assert len(ports) > 0


def test_get_available_ports_some_used(client, app):
    """Used ports are excluded from available ports."""
    with app.app_context():
        host = create_host(name='port-h2', provider='vultr', status=HostStatus.ACTIVE)
        instance = QLInstance(name='taken-inst', port=27960, hostname='server.example.com', host_id=host.id)
        db.session.add(instance)
        db.session.commit()
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/hosts/{host_id}/available-ports', headers=headers)
    assert response.status_code == 200
    ports = response.get_json()['data']['available_ports']
    assert 27960 not in ports


def test_get_available_ports_host_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/hosts/99999/available-ports', headers=headers)
    assert response.status_code == 404


def test_get_available_ports_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/hosts/1/available-ports')
    assert response.status_code == 401


# --- POST /api/hosts/<id>/restart ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_restart_host_success(mock_lock, mock_enqueue, client, app):
    """ACTIVE host restart queues restart task."""
    with app.app_context():
        host = create_host(name='restart-h', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/restart', headers=headers)
    assert response.status_code == 202
    assert 'restart process initiated' in response.get_json()['message']
    mock_enqueue.assert_called_once()


def test_restart_host_not_active(client, app):
    """Non-ACTIVE host returns 400."""
    with app.app_context():
        host = create_host(name='err-restart', provider='vultr', status=HostStatus.ERROR)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/restart', headers=headers)
    assert response.status_code == 400
    assert 'ACTIVE state' in response.get_json()['error']['message']


def test_restart_host_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/99999/restart', headers=headers)
    assert response.status_code == 404


def test_restart_host_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.post('/api/hosts/1/restart')
    assert response.status_code == 401


# --- GET /api/hosts/<id>/qlfilter/status ---

def test_get_qlfilter_status_success(client, app):
    """Returns QLFilter status for existing host."""
    with app.app_context():
        host = create_host(name='qlf-status', provider='vultr',
                           status=HostStatus.ACTIVE,
                           qlfilter_status=QLFilterStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/hosts/{host_id}/qlfilter/status', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data']['qlfilter_status'] == 'active'


def test_get_qlfilter_status_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/hosts/99999/qlfilter/status', headers=headers)
    assert response.status_code == 404


def test_get_qlfilter_status_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/hosts/1/qlfilter/status')
    assert response.status_code == 401


# --- POST /api/hosts/<id>/qlfilter/install ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_install_qlfilter_success(mock_lock, mock_enqueue, client, app):
    """Queues QLFilter install task on active host."""
    with app.app_context():
        host = create_host(name='qlf-install', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/qlfilter/install', headers=headers)
    assert response.status_code == 202
    mock_enqueue.assert_called_once()


def test_install_qlfilter_host_not_active(client, app):
    """Non-ACTIVE host returns 409."""
    with app.app_context():
        host = create_host(name='qlf-notactive', provider='vultr', status=HostStatus.PENDING)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/qlfilter/install', headers=headers)
    assert response.status_code == 409


def test_install_qlfilter_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/99999/qlfilter/install', headers=headers)
    assert response.status_code == 404


# --- POST /api/hosts/<id>/qlfilter/uninstall ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_uninstall_qlfilter_success(mock_lock, mock_enqueue, client, app):
    """Queues QLFilter uninstall task."""
    with app.app_context():
        host = create_host(name='qlf-uninst', provider='vultr', status=HostStatus.ACTIVE,
                           qlfilter_status=QLFilterStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/qlfilter/uninstall', headers=headers)
    assert response.status_code == 202
    mock_enqueue.assert_called_once()


def test_uninstall_qlfilter_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/99999/qlfilter/uninstall', headers=headers)
    assert response.status_code == 404


# --- POST /api/hosts/<id>/qlfilter/refresh-status ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_refresh_qlfilter_status_success(mock_lock, mock_enqueue, client, app):
    """Queues status refresh task."""
    with app.app_context():
        host = create_host(name='qlf-refresh', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/qlfilter/refresh-status', headers=headers)
    assert response.status_code == 202
    mock_enqueue.assert_called_once()


def test_refresh_qlfilter_status_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/99999/qlfilter/refresh-status', headers=headers)
    assert response.status_code == 404

# --- POST /api/hosts/<id>/update-workshop ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_force_update_workshop_success(mock_lock, mock_enqueue, client, app):
    """Queues workshop update task on active host."""
    with app.app_context():
        host = create_host(name='workshop-update-host', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/update-workshop', headers=headers, json={
        'workshop_id': '123456789',
        'restart_instances': [1, 2]
    })
    assert response.status_code == 202
    assert 'process initiated' in response.get_json()['message']
    mock_enqueue.assert_called_once()

def test_force_update_workshop_missing_workshop_id(client, app):
    """Missing workshop_id returns 400."""
    with app.app_context():
        host = create_host(name='workshop-update-host-missing', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/update-workshop', headers=headers, json={
        'restart_instances': [1, 2]
    })
    assert response.status_code == 400

def test_force_update_workshop_host_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/99999/update-workshop', headers=headers, json={
        'workshop_id': '123456789'
    })
    assert response.status_code == 404

def test_force_update_workshop_host_not_active(client, app):
    """Non-ACTIVE host returns 400."""
    with app.app_context():
        host = create_host(name='workshop-update-notactive', provider='vultr', status=HostStatus.ERROR)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/update-workshop', headers=headers, json={
        'workshop_id': '123456789'
    })
    assert response.status_code == 400


def test_force_update_workshop_invalid_workshop_id(client, app):
    """Non-numeric workshop_id returns 400."""
    with app.app_context():
        host = create_host(name='workshop-update-badid', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/update-workshop', headers=headers, json={
        'workshop_id': 'abc-not-numeric'
    })
    assert response.status_code == 400
    assert 'numeric' in response.get_json()['error']['message']


def test_force_update_workshop_invalid_restart_instances(client, app):
    """Non-list restart_instances returns 400."""
    with app.app_context():
        host = create_host(name='workshop-update-badinst', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/update-workshop', headers=headers, json={
        'workshop_id': '123456789',
        'restart_instances': 'not-a-list'
    })
    assert response.status_code == 400
    assert 'list of integers' in response.get_json()['error']['message']


# --- POST /api/hosts/<id>/auto-restart ---

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_configure_auto_restart_api_success(mock_lock, mock_enqueue, client, app):
    """Valid schedule configures auto-restart."""
    with app.app_context():
        host = create_host(name='auto-restart-ok', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/auto-restart', headers=headers, json={
        'schedule': '*-*-* 04:00:00'
    })

    assert response.status_code == 202
    assert 'initiated' in response.get_json()['message']
    mock_enqueue.assert_called_once()

@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_configure_auto_restart_api_remove_schedule(mock_lock, mock_enqueue, client, app):
    """Empty schedule removes auto-restart."""
    with app.app_context():
        host = create_host(name='auto-restart-rm', provider='vultr', status=HostStatus.ACTIVE, auto_restart_schedule="*-*-* 04:00:00")
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/auto-restart', headers=headers, json={
        'schedule': ''
    })

    assert response.status_code == 202

def test_configure_auto_restart_api_not_found(client, app):
    """Non-existent host returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/hosts/99999/auto-restart', headers=headers, json={
        'schedule': '*-*-* 04:00:00'
    })
    assert response.status_code == 404

def test_configure_auto_restart_api_no_data(client, app):
    """Missing body returns 400."""
    with app.app_context():
        host = create_host(name='auto-restart-nodata', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/auto-restart', headers=headers)
    assert response.status_code in (400, 415)


def test_configure_auto_restart_api_not_active(client, app):
    """Non-ACTIVE host returns 400."""
    with app.app_context():
        host = create_host(name='auto-restart-err', provider='vultr', status=HostStatus.ERROR)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/auto-restart', headers=headers, json={
        'schedule': '*-*-* 04:00:00'
    })
    assert response.status_code == 400
    assert 'ACTIVE state' in response.get_json()['error']['message']


def test_configure_auto_restart_api_invalid_schedule(client, app):
    """Invalid schedule format returns 400."""
    with app.app_context():
        host = create_host(name='auto-restart-bad', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post(f'/api/hosts/{host_id}/auto-restart', headers=headers, json={
        'schedule': 'invalid\nExecStart=/bin/evil'
    })
    assert response.status_code == 400
    assert 'Invalid schedule format' in response.get_json()['error']['message']
