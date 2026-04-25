import os
import pytest
from tests.helpers import make_user, auth_headers
from ui import db
from ui.models import ConfigPreset

DEFAULT_USER = 'factoryadmin'
DEFAULT_PASS = 'factorypass1'


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


# --- GET /api/factories/tree ---

def test_get_factory_tree_empty_dir(client, app, tmp_path, monkeypatch):
    """Empty factories directory returns empty list."""
    monkeypatch.chdir(tmp_path)
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/tree?preset=default', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data'] == []


def test_get_factory_tree_with_files(client, app, tmp_path, monkeypatch):
    """Directory with .factories files returns them as list."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'presets' / 'default' / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'ca.factories').write_text('factory content 1')
    (factories_dir / 'duel.factories').write_text('factory content 2')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/tree?preset=default', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    names = [item['name'] for item in data]
    assert 'ca.factories' in names
    assert 'duel.factories' in names


def test_get_factory_tree_uses_builtin_default_db_path(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'presets' / '_builtin' / 'default' / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'builtin.factories').write_text('factory content')

    with app.app_context():
        db.session.add(ConfigPreset(
            name='default',
            description='Default',
            path='configs/presets/_builtin/default',
            is_builtin=True,
        ))
        db.session.commit()

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/tree?preset=default', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data'] == [{
        'name': 'builtin.factories',
        'type': 'file',
        'path': 'builtin.factories',
    }]


def test_get_factory_tree_ignores_non_factories_files(client, app, tmp_path, monkeypatch):
    """Non-.factories files are not included in the tree."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'presets' / 'default' / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'ca.factories').write_text('content')
    (factories_dir / 'readme.txt').write_text('ignored')
    (factories_dir / '.hidden').write_text('also ignored')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/tree?preset=default', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    names = [item['name'] for item in data]
    assert 'ca.factories' in names
    assert 'readme.txt' not in names
    assert '.hidden' not in names


def test_get_factory_tree_instance_context(client, app, tmp_path, monkeypatch):
    """Instance-level factories directory is resolved correctly."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'myhost' / '42' / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'ffa.factories').write_text('ffa content')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/tree?host=myhost&instance_id=42', headers=headers)
    assert response.status_code == 200
    names = [item['name'] for item in response.get_json()['data']]
    assert 'ffa.factories' in names


def test_get_factory_tree_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/factories/tree?preset=default')
    assert response.status_code == 401


def test_get_factory_tree_sorted(client, app, tmp_path, monkeypatch):
    """Factories are returned in sorted order."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'presets' / 'default' / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'zzz.factories').write_text('z')
    (factories_dir / 'aaa.factories').write_text('a')
    (factories_dir / 'mmm.factories').write_text('m')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/tree?preset=default', headers=headers)
    assert response.status_code == 200
    names = [item['name'] for item in response.get_json()['data']]
    assert names == sorted(names)


# --- GET /api/factories/content ---

def test_get_factory_content_success(client, app, tmp_path, monkeypatch):
    """Returns content of a valid .factories file."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'presets' / 'default' / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'ca.factories').write_text('ca factory data here')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/content?path=ca.factories&preset=default',
                          headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['path'] == 'ca.factories'
    assert data['content'] == 'ca factory data here'


def test_get_factory_content_missing_path_param(client, app):
    """Missing path parameter returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/content?preset=default', headers=headers)
    assert response.status_code == 400
    assert 'Path parameter is required' in response.get_json()['error']['message']


def test_get_factory_content_file_not_found(client, app, tmp_path, monkeypatch):
    """Non-existent file returns 404."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'presets' / 'default' / 'factories'
    factories_dir.mkdir(parents=True)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/content?path=missing.factories&preset=default',
                          headers=headers)
    assert response.status_code == 404


def test_get_factory_content_directory_traversal(client, app, tmp_path, monkeypatch):
    """Directory traversal attempt returns 400."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'presets' / 'default' / 'factories'
    factories_dir.mkdir(parents=True)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/factories/content?path=../../secret.txt&preset=default',
                          headers=headers)
    assert response.status_code == 400
    assert 'Invalid path' in response.get_json()['error']['message']


def test_get_factory_content_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/factories/content?path=ca.factories&preset=default')
    assert response.status_code == 401


def test_get_factory_content_instance_context(client, app, tmp_path, monkeypatch):
    """Reads content from instance-level factories directory."""
    monkeypatch.chdir(tmp_path)
    factories_dir = tmp_path / 'configs' / 'myhost' / '7' / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'ffa.factories').write_text('ffa instance data')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(
        '/api/factories/content?path=ffa.factories&host=myhost&instance_id=7',
        headers=headers
    )
    assert response.status_code == 200
    assert response.get_json()['data']['content'] == 'ffa instance data'
