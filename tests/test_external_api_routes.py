import pytest
from tests.helpers import make_user, auth_headers
from ui import db
from ui.models import ApiKey, Host, HostStatus
from ui.database import create_host, create_instance


def _generate_key(client, app):
    """Helper: generate an API key and return the plaintext."""
    make_user(app, 'admin', 'password1')
    headers = auth_headers(app, 'admin')
    resp = client.post('/api/settings/api-key', headers=headers)
    return resp.get_json()['data']['key']


def _create_test_instance(app):
    """Helper: create a host with one instance, return instance id."""
    with app.app_context():
        host = create_host(name='ext-test-host', provider='vultr',
                           status=HostStatus.ACTIVE, ip_address='10.0.0.1')
        inst = create_instance(name='ext-test-inst', host_id=host.id,
                               port=27960, hostname='test.server.com')
        inst.zmq_stats_port = 29999
        inst.zmq_stats_password = 'stats_secret'
        inst.zmq_rcon_port = 28888
        inst.zmq_rcon_password = 'rcon_secret'
        db.session.commit()
        return inst.id


# --- Authentication ---

def test_external_api_no_auth(client):
    """Missing Authorization header returns 401."""
    resp = client.get('/api/v1/instances')
    assert resp.status_code == 401
    assert 'Missing' in resp.get_json()['error']['message']


def test_external_api_invalid_key(client, app):
    """Invalid Bearer token returns 401."""
    _generate_key(client, app)
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': 'Bearer bad-key'})
    assert resp.status_code == 401
    assert 'Invalid' in resp.get_json()['error']['message']


def test_external_api_valid_key(client, app):
    """Valid Bearer token returns 200 with instance data."""
    key = _generate_key(client, app)
    _create_test_instance(app)
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {key}'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['name'] == 'ext-test-inst'


def test_external_api_revoked_key(client, app):
    """Revoked key returns 401."""
    key = _generate_key(client, app)
    jwt_headers = auth_headers(app, 'admin')
    client.delete('/api/settings/api-key', headers=jwt_headers)
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {key}'})
    assert resp.status_code == 401


def test_external_api_regenerated_old_key_fails(client, app):
    """After regeneration, old key no longer works."""
    old_key = _generate_key(client, app)
    jwt_headers = auth_headers(app, 'admin')
    resp = client.post('/api/settings/api-key', headers=jwt_headers)
    new_key = resp.get_json()['data']['key']
    assert old_key != new_key
    # Old key should fail
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {old_key}'})
    assert resp.status_code == 401
    # New key should work
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {new_key}'})
    assert resp.status_code == 200


# --- Response field exclusion ---

def test_excludes_rcon_fields(client, app):
    """Response must not contain zmq_rcon_port or zmq_rcon_password."""
    key = _generate_key(client, app)
    _create_test_instance(app)
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {key}'})
    inst = resp.get_json()['data'][0]
    assert 'zmq_rcon_port' not in inst
    assert 'zmq_rcon_password' not in inst


def test_excludes_logs_and_config(client, app):
    """Response must not contain logs or config."""
    key = _generate_key(client, app)
    _create_test_instance(app)
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {key}'})
    inst = resp.get_json()['data'][0]
    assert 'logs' not in inst
    assert 'config' not in inst


def test_includes_zmq_stats_fields(client, app):
    """Response includes zmq_stats_port and zmq_stats_password."""
    key = _generate_key(client, app)
    _create_test_instance(app)
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {key}'})
    inst = resp.get_json()['data'][0]
    assert inst['zmq_stats_port'] == 29999
    assert inst['zmq_stats_password'] == 'stats_secret'


def test_includes_host_details(client, app):
    """Response includes host_name and host_ip_address."""
    key = _generate_key(client, app)
    _create_test_instance(app)
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {key}'})
    inst = resp.get_json()['data'][0]
    assert inst['host_name'] == 'ext-test-host'
    assert inst['host_ip_address'] == '10.0.0.1'
    assert inst['port'] == 27960


def test_returns_all_instances(client, app):
    """Returns all instances regardless of status."""
    key = _generate_key(client, app)
    with app.app_context():
        host = create_host(name='multi-host', provider='vultr',
                           status=HostStatus.ACTIVE, ip_address='10.0.0.2')
        create_instance(name='inst-a', host_id=host.id, port=27960,
                        hostname='a.test.com')
        create_instance(name='inst-b', host_id=host.id, port=27961,
                        hostname='b.test.com')
        create_instance(name='inst-c', host_id=host.id, port=27962,
                        hostname='c.test.com')
        db.session.commit()
    resp = client.get('/api/v1/instances',
                      headers={'Authorization': f'Bearer {key}'})
    assert resp.status_code == 200
    assert len(resp.get_json()['data']) == 3
