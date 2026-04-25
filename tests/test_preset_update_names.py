import os

import pytest

from tests.helpers import auth_headers, make_user
from ui import db
from ui.database import create_preset
from ui.models import ConfigPreset


DEFAULT_USER = 'presetrenameadmin'
DEFAULT_PASS = 'presetrenamepass1'


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


@pytest.fixture(autouse=True)
def isolate_preset_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_update_preset_normalizes_same_name_without_persisting_whitespace(client, app):
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'custom')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='custom', description='old', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'name': ' custom ',
        'description': 'new',
    })

    assert response.status_code == 200
    assert response.get_json()['data']['name'] == 'custom'
    with app.app_context():
        preset = db.session.get(ConfigPreset, preset_id)
        assert preset.name == 'custom'
        assert preset.path == os.path.join('configs', 'presets', 'custom')


def test_update_builtin_same_name_with_whitespace_does_not_rename(client, app):
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin', 'default')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(
            name='default',
            description='Default',
            path=preset_path,
            is_builtin=True,
        )
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'name': ' default ',
        'server_cfg': 'set sv_hostname "Updated"\n',
    })

    assert response.status_code == 200
    assert response.get_json()['data']['name'] == 'default'
    with app.app_context():
        preset = db.session.get(ConfigPreset, preset_id)
        assert preset.name == 'default'
        assert preset.path == os.path.join('configs', 'presets', '_builtin', 'default')


def test_update_preset_rejects_blank_normalized_name(client, app):
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'custom')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='custom', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={'name': '   '})

    assert response.status_code == 400
    assert 'Preset name is required' in response.get_json()['error']['message']
