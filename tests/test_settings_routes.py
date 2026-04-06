import pytest
from tests.helpers import make_user, auth_headers
from ui import db
from ui.models import ApiKey


# --- GET /api/settings/api-key ---

def test_get_api_key_empty(client, app):
    """No key exists returns data: null."""
    make_user(app, 'admin', 'password1')
    headers = auth_headers(app, 'admin')
    resp = client.get('/api/settings/api-key', headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()['data'] is None


def test_get_api_key_exists(client, app):
    """Returns key when one exists."""
    make_user(app, 'admin', 'password1')
    headers = auth_headers(app, 'admin')
    # Generate a key first
    client.post('/api/settings/api-key', headers=headers)
    resp = client.get('/api/settings/api-key', headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['key'] is not None
    assert len(data['key']) > 0
    assert 'created_at' in data


def test_get_api_key_unauthorized(client):
    """Unauthenticated request returns 401."""
    resp = client.get('/api/settings/api-key')
    assert resp.status_code == 401


# --- POST /api/settings/api-key ---

def test_generate_api_key(client, app):
    """Generates a new API key."""
    make_user(app, 'admin', 'password1')
    headers = auth_headers(app, 'admin')
    resp = client.post('/api/settings/api-key', headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['data']['key'] is not None
    assert 'message' in data


def test_regenerate_replaces_old_key(client, app):
    """Regenerating replaces the previous key."""
    make_user(app, 'admin', 'password1')
    headers = auth_headers(app, 'admin')
    resp1 = client.post('/api/settings/api-key', headers=headers)
    key1 = resp1.get_json()['data']['key']
    resp2 = client.post('/api/settings/api-key', headers=headers)
    key2 = resp2.get_json()['data']['key']
    assert key1 != key2
    # Only one key in DB
    with app.app_context():
        assert ApiKey.query.count() == 1


# --- DELETE /api/settings/api-key ---

def test_revoke_api_key(client, app):
    """Revoking deletes the key."""
    make_user(app, 'admin', 'password1')
    headers = auth_headers(app, 'admin')
    client.post('/api/settings/api-key', headers=headers)
    resp = client.delete('/api/settings/api-key', headers=headers)
    assert resp.status_code == 200
    assert 'revoked' in resp.get_json()['message'].lower()
    with app.app_context():
        assert ApiKey.query.count() == 0


def test_revoke_no_key(client, app):
    """Revoking when no key exists returns 404."""
    make_user(app, 'admin', 'password1')
    headers = auth_headers(app, 'admin')
    resp = client.delete('/api/settings/api-key', headers=headers)
    assert resp.status_code == 404
