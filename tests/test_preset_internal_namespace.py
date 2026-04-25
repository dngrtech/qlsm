import os

import pytest

from tests.helpers import auth_headers, make_user
from ui.database import create_preset


DEFAULT_USER = 'presetnamespaceadmin'
DEFAULT_PASS = 'presetnamespacepass1'


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


@pytest.fixture(autouse=True)
def isolate_preset_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_validate_preset_name_internal_namespace_reserved(client, app):
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/validate-name?name=_builtin', headers=headers)

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['is_valid'] is False
    assert 'reserved for internal preset storage' in data['error']


def test_create_preset_internal_namespace_rejected(client, app):
    headers = auth_headers(app, DEFAULT_USER)

    response = client.post('/api/presets/', headers=headers, json={
        'name': '_builtin',
        'description': ''
    })

    assert response.status_code == 409
    assert 'reserved for internal preset storage' in response.get_json()['error']['message']
    assert not os.path.exists(os.path.join('configs', 'presets', '_builtin'))


def test_rename_user_preset_to_internal_namespace_rejected(client, app):
    with app.app_context():
        user_path = os.path.join('configs', 'presets', 'custom')
        os.makedirs(user_path, exist_ok=True)
        user = create_preset(name='custom', description='', path=user_path)
        user_id = user.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{user_id}', headers=headers, json={'name': '_builtin'})

    assert response.status_code == 409
    assert 'reserved for internal preset storage' in response.get_json()['error']['message']
    assert os.path.exists(user_path)
    assert not os.path.exists(os.path.join('configs', 'presets', '_builtin'))


def test_delete_internal_namespace_preset_prevented(client, app):
    """Legacy/malformed _builtin rows must not delete the built-in root."""
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin')
        os.makedirs(os.path.join(preset_path, 'default'), exist_ok=True)
        marker = os.path.join(preset_path, 'default', 'server.cfg')
        with open(marker, 'w') as handle:
            handle.write('set sv_hostname "default"\n')
        preset = create_preset(name='_builtin', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete(f'/api/presets/{preset_id}', headers=headers)

    assert response.status_code == 403
    assert 'internal preset namespace' in response.get_json()['error']['message']
    assert os.path.exists(marker)
