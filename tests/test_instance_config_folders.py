"""Tests for nested-path validation and .ent extension on instance configs."""

import pytest
from ui.routes.instance_routes import (
    _validate_path_segment,
    _validate_relative_path,
    _validate_configs_map,
    ALLOWED_CONFIG_EXTENSIONS,
    RESERVED_CONFIG_FOLDER_NAMES,
)


class TestValidatePathSegment:
    def test_accepts_safe_name(self):
        assert _validate_path_segment("foo.cfg", ALLOWED_CONFIG_EXTENSIONS) is None

    def test_rejects_slash(self):
        assert _validate_path_segment("a/b", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_rejects_dotdot(self):
        assert _validate_path_segment("..", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_rejects_leading_dot(self):
        assert _validate_path_segment(".hidden", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_segment_only_skips_extension_check(self):
        # When allowed_extensions is None, segment is treated as folder name (no extension required)
        assert _validate_path_segment("custom_entities", None) is None


class TestValidateRelativePath:
    def test_accepts_flat_file(self):
        assert _validate_relative_path("server.cfg", ALLOWED_CONFIG_EXTENSIONS) is None

    def test_accepts_nested_file(self):
        assert _validate_relative_path("custom_entities/items.ent", ALLOWED_CONFIG_EXTENSIONS) is None

    def test_rejects_too_deep(self):
        err = _validate_relative_path("a/b/c.cfg", ALLOWED_CONFIG_EXTENSIONS, max_depth=2)
        assert err is not None

    def test_rejects_leading_slash(self):
        assert _validate_relative_path("/server.cfg", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_rejects_trailing_slash(self):
        assert _validate_relative_path("foo/", ALLOWED_CONFIG_EXTENSIONS) is not None


class TestEntExtension:
    def test_ent_is_allowed(self):
        assert ".ent" in ALLOWED_CONFIG_EXTENSIONS

    def test_ent_validates_in_configs_map(self):
        err, _ = _validate_configs_map({
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
            'custom_entities/items.ent': '// entity overrides',
        })
        assert err is None


class TestReservedFolders:
    def test_scripts_is_reserved(self):
        assert 'scripts' in RESERVED_CONFIG_FOLDER_NAMES

    def test_factories_is_reserved(self):
        assert 'factories' in RESERVED_CONFIG_FOLDER_NAMES


import os
import json
from unittest.mock import MagicMock, patch
from flask_jwt_extended import create_access_token
from types import SimpleNamespace
from ui import db
from ui.database import create_host, create_instance
from ui.models import HostStatus


@pytest.fixture
def auth_token(app):
    with app.app_context():
        return create_access_token(identity='testuser')


@pytest.fixture
def sample_instance(app):
    with app.app_context():
        host = create_host(name='folder-host', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(
            name='folder-inst',
            host_id=host.id,
            port=27960,
            hostname='folder.hostname',
        )
        return SimpleNamespace(id=instance.id, name=instance.name, host_name=host.name)


def _full_configs(**overrides):
    configs = {'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': ''}
    configs.update(overrides)
    return configs


def _put_config(client, instance_id, payload, auth_token):
    """Wrap PUT /config with the required RQ/lock patches."""
    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='fake-job')):
        return client.put(
            f'/api/instances/{instance_id}/config',
            json=payload,
            headers={'Authorization': f'Bearer {auth_token}'},
        )


class TestSyncConfigsWithFolders:
    def test_save_creates_nested_file(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        payload = {
            'configs': _full_configs(**{'custom_entities/items.ent': '// items'}),
            'config_folders': ['custom_entities'],
        }
        resp = _put_config(client, sample_instance.id, payload, auth_token)
        assert resp.status_code in (200, 202), resp.get_json()
        nested = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id) / 'custom_entities' / 'items.ent'
        assert nested.exists()
        assert nested.read_text() == '// items'

    def test_save_creates_empty_folder(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        payload = {
            'configs': _full_configs(),
            'config_folders': ['custom_entities'],
        }
        resp = _put_config(client, sample_instance.id, payload, auth_token)
        assert resp.status_code in (200, 202)
        folder = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id) / 'custom_entities'
        assert folder.exists() and folder.is_dir()

    def test_save_removes_orphan_nested_file(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        instance_dir = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id)
        (instance_dir / 'custom_entities').mkdir(parents=True)
        (instance_dir / 'custom_entities' / 'old.ent').write_text('// old')
        payload = {
            'configs': _full_configs(**{'custom_entities/new.ent': '// new'}),
            'config_folders': ['custom_entities'],
        }
        resp = _put_config(client, sample_instance.id, payload, auth_token)
        assert resp.status_code in (200, 202)
        assert not (instance_dir / 'custom_entities' / 'old.ent').exists()
        assert (instance_dir / 'custom_entities' / 'new.ent').exists()

    def test_save_removes_orphan_empty_folder(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        instance_dir = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id)
        (instance_dir / 'gone').mkdir(parents=True)
        payload = {
            'configs': _full_configs(),
            'config_folders': [],
        }
        resp = _put_config(client, sample_instance.id, payload, auth_token)
        assert resp.status_code in (200, 202)
        assert not (instance_dir / 'gone').exists()

    def test_legacy_payload_without_config_folders_preserves_existing(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        """Regression for accepted finding #3: an old client that POSTs `configs`
        WITHOUT `config_folders` must NOT delete pre-existing top-level folders."""
        monkeypatch.chdir(tmp_path)
        instance_dir = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id)
        (instance_dir / 'preserve_me').mkdir(parents=True)
        (instance_dir / 'preserve_me' / 'old.ent').write_text('// legacy')
        payload = {'configs': _full_configs()}
        resp = _put_config(client, sample_instance.id, payload, auth_token)
        assert resp.status_code in (200, 202)
        assert (instance_dir / 'preserve_me').exists()

    def test_orphan_folder_with_unmanaged_content_is_preserved(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        """When pruning is requested but a folder contains unmanaged files, skip rather than destroy."""
        monkeypatch.chdir(tmp_path)
        instance_dir = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id)
        (instance_dir / 'mystery').mkdir(parents=True)
        (instance_dir / 'mystery' / 'README').write_text('not a managed extension')
        payload = {'configs': _full_configs(), 'config_folders': []}
        resp = _put_config(client, sample_instance.id, payload, auth_token)
        assert resp.status_code in (200, 202)
        assert (instance_dir / 'mystery' / 'README').exists()

    def test_save_preserves_scripts_and_factories(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        instance_dir = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id)
        (instance_dir / 'scripts').mkdir(parents=True)
        (instance_dir / 'scripts' / 'plugin.py').write_text('class p: pass')
        (instance_dir / 'factories').mkdir(parents=True)
        (instance_dir / 'factories' / 'duel.factories').write_text('{}')
        payload = {
            'configs': _full_configs(),
            'config_folders': [],
        }
        resp = _put_config(client, sample_instance.id, payload, auth_token)
        assert resp.status_code in (200, 202)
        assert (instance_dir / 'scripts' / 'plugin.py').exists()
        assert (instance_dir / 'factories' / 'duel.factories').exists()

    def test_get_returns_nested_files_and_folders(self, client, app, sample_instance, auth_token, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        instance_dir = tmp_path / 'configs' / sample_instance.host_name / str(sample_instance.id)
        instance_dir.mkdir(parents=True)
        (instance_dir / 'server.cfg').write_text('// hi')
        (instance_dir / 'mappool.txt').write_text('')
        (instance_dir / 'access.txt').write_text('')
        (instance_dir / 'workshop.txt').write_text('')
        (instance_dir / 'custom_entities').mkdir()
        (instance_dir / 'custom_entities' / 'a.ent').write_text('// a')
        (instance_dir / 'empty_dir').mkdir()
        resp = client.get(
            f'/api/instances/{sample_instance.id}/config',
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'custom_entities/a.ent' in data
        assert data['custom_entities/a.ent'] == '// a'
        assert 'config_folders' in data
        assert set(data['config_folders']) >= {'custom_entities', 'empty_dir'}


class TestRejectReservedAndDeep:
    def test_rejects_reserved_folder_name(self, client, app, sample_instance, auth_token):
        resp = client.put(
            f'/api/instances/{sample_instance.id}/config',
            json={'configs': _full_configs(), 'config_folders': ['scripts']},
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert resp.status_code == 400
        assert 'reserved' in resp.get_json()['error']['message'].lower()

    def test_rejects_deep_path(self, client, app, sample_instance, auth_token):
        resp = client.put(
            f'/api/instances/{sample_instance.id}/config',
            json={
                'configs': _full_configs(**{'a/b/c.cfg': ''}),
                'config_folders': [],
            },
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert resp.status_code == 400


# --- Additional tests appended in Task 14 ---
