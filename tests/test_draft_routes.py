"""Tests for draft workspace API routes."""

import pytest
import io
import os
import uuid
import time
from flask_jwt_extended import create_access_token
from ui import db
from ui.models import ConfigPreset

@pytest.fixture
def drafts_base(app):
    """Return the per-test isolated drafts base directory from app config."""
    return app.config['DRAFTS_BASE']


@pytest.fixture
def auth_headers(app):
    """Generate JWT auth headers for testing."""
    with app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def preset_with_scripts(tmp_path):
    """Create a temporary preset directory with test scripts."""
    scripts_dir = tmp_path / 'configs' / 'presets' / 'default' / 'scripts'
    scripts_dir.mkdir(parents=True)
    (scripts_dir / 'balance.py').write_text('# balance plugin\nclass balance: pass\n')
    (scripts_dir / 'ban.py').write_text('# ban plugin\nclass ban: pass\n')
    (scripts_dir / 'readme.txt').write_text('Plugin readme\n')
    return tmp_path


class TestCreateDraft:
    """Tests for POST /api/drafts/ endpoint."""

    def test_create_draft_from_default_preset(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        response = client.post('/api/drafts/', json={
            'source': 'preset',
            'preset': 'default'
        }, headers=auth_headers)
        assert response.status_code == 201
        data = response.get_json()['data']
        assert 'draft_id' in data
        # Verify draft directory was created and seeded
        draft_dir = os.path.join(drafts_base, data['draft_id'], 'scripts')
        assert os.path.exists(draft_dir)
        assert os.path.exists(os.path.join(draft_dir, 'balance.py'))
        assert os.path.exists(os.path.join(draft_dir, 'ban.py'))
        assert os.path.exists(os.path.join(draft_dir, 'readme.txt'))

    def test_create_draft_from_builtin_default_preset(self, client, app, auth_headers, tmp_path, monkeypatch, drafts_base):
        configs_base = tmp_path / 'configs'
        scripts_dir = configs_base / 'presets' / '_builtin' / 'default' / 'scripts'
        scripts_dir.mkdir(parents=True)
        (scripts_dir / 'balance.py').write_text('# builtin balance\n')
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(configs_base))

        with app.app_context():
            db.session.add(ConfigPreset(
                name='default',
                description='Default',
                path=str(configs_base / 'presets' / '_builtin' / 'default'),
                is_builtin=True,
            ))
            db.session.commit()

        response = client.post('/api/drafts/', json={
            'source': 'preset',
            'preset': 'default'
        }, headers=auth_headers)

        assert response.status_code == 201
        draft_dir = os.path.join(drafts_base, response.get_json()['data']['draft_id'], 'scripts')
        assert os.path.exists(os.path.join(draft_dir, 'balance.py'))

    def test_create_draft_returns_uuid(self, client, auth_headers, preset_with_scripts, monkeypatch):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        response = client.post('/api/drafts/', json={
            'source': 'preset',
            'preset': 'default'
        }, headers=auth_headers)
        draft_id = response.get_json()['data']['draft_id']
        # Validate it's a valid UUID4
        uuid.UUID(draft_id, version=4)

    def test_create_draft_missing_source(self, client, auth_headers):
        response = client.post('/api/drafts/', json={}, headers=auth_headers)
        assert response.status_code == 400

    def test_create_draft_path_traversal_in_preset_rejected(self, client, auth_headers):
        response = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': '../../etc'
        }, headers=auth_headers)
        assert response.status_code == 400

    def test_create_draft_path_traversal_in_host_rejected(self, client, auth_headers):
        response = client.post('/api/drafts/', json={
            'source': 'instance', 'host': '../../etc', 'instance_id': '1'
        }, headers=auth_headers)
        assert response.status_code == 400

    def test_create_draft_sibling_prefix_escape_rejected(self, client, auth_headers):
        """Preset name that is a sibling prefix of the presets dir should be rejected."""
        response = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': '../presets-evil'
        }, headers=auth_headers)
        assert response.status_code == 400

    def test_create_draft_cross_subtree_via_instance_rejected(self, client, auth_headers):
        """Instance mode with host='presets' must not reach preset subtree."""
        response = client.post('/api/drafts/', json={
            'source': 'instance', 'host': 'presets', 'instance_id': 'default'
        }, headers=auth_headers)
        assert response.status_code == 400


class TestDiscardDraft:
    """Tests for DELETE /api/drafts/<draft_id> endpoint."""

    def test_discard_removes_directory(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        # Create a draft first
        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        draft_id = resp.get_json()['data']['draft_id']
        draft_path = os.path.join(drafts_base, draft_id)
        assert os.path.exists(draft_path)

        # Discard it
        response = client.delete(f'/api/drafts/{draft_id}', headers=auth_headers)
        assert response.status_code == 200
        assert not os.path.exists(draft_path)

    def test_discard_nonexistent_draft_returns_404(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        response = client.delete(f'/api/drafts/{fake_id}', headers=auth_headers)
        assert response.status_code == 404


class TestDraftCleanup:
    """Tests for stale draft cleanup on create."""

    def test_stale_drafts_cleaned_on_create(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        # Create a stale draft manually with old mtime
        stale_id = str(uuid.uuid4())
        stale_path = os.path.join(drafts_base, stale_id)
        os.makedirs(stale_path)
        # Set mtime to 2 hours ago
        old_time = time.time() - 7200
        os.utime(stale_path, (old_time, old_time))

        # Create a new draft — should trigger cleanup
        client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)

        assert not os.path.exists(stale_path)

    def test_fresh_drafts_not_cleaned(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        # Create a fresh draft manually
        fresh_id = str(uuid.uuid4())
        fresh_path = os.path.join(drafts_base, fresh_id, 'scripts')
        os.makedirs(fresh_path)

        # Create another draft — should NOT clean up the fresh one
        client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)

        assert os.path.exists(os.path.join(drafts_base, fresh_id))


class TestTouchDraft:
    """Tests for POST /api/drafts/<draft_id>/touch endpoint."""

    def test_touch_updates_mtime(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        # Create draft
        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        draft_id = resp.get_json()['data']['draft_id']
        draft_path = os.path.join(drafts_base, draft_id)

        # Set mtime to 30 minutes ago
        old_time = time.time() - 1800
        os.utime(draft_path, (old_time, old_time))
        old_mtime = os.path.getmtime(draft_path)

        # Touch
        response = client.post(f'/api/drafts/{draft_id}/touch', headers=auth_headers)
        assert response.status_code == 200
        new_mtime = os.path.getmtime(draft_path)
        assert new_mtime > old_mtime

    def test_touch_nonexistent_draft_returns_404(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        response = client.post(f'/api/drafts/{fake_id}/touch', headers=auth_headers)
        assert response.status_code == 404


class TestDraftTree:
    """Tests for GET /api/drafts/<draft_id>/tree endpoint."""

    def test_tree_returns_all_file_types(self, client, auth_headers, preset_with_scripts, monkeypatch):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        # Add a .so file to the preset so the draft picks it up
        scripts_dir = preset_with_scripts / 'configs' / 'presets' / 'default' / 'scripts'
        (scripts_dir / 'hook.so').write_bytes(b'\x7fELF' + b'\x00' * 100)

        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        draft_id = resp.get_json()['data']['draft_id']

        response = client.get(f'/api/drafts/{draft_id}/tree', headers=auth_headers)
        assert response.status_code == 200
        tree = response.get_json()['data']
        names = [f['name'] for f in tree]
        assert 'balance.py' in names
        assert 'readme.txt' in names
        assert 'hook.so' in names

    def test_tree_includes_file_type_metadata(self, client, auth_headers, preset_with_scripts, monkeypatch):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        scripts_dir = preset_with_scripts / 'configs' / 'presets' / 'default' / 'scripts'
        (scripts_dir / 'hook.so').write_bytes(b'\x7fELF' + b'\x00' * 100)

        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        draft_id = resp.get_json()['data']['draft_id']

        response = client.get(f'/api/drafts/{draft_id}/tree', headers=auth_headers)
        tree = response.get_json()['data']

        py_file = next(f for f in tree if f['name'] == 'balance.py')
        assert py_file['file_type'] == 'python'
        assert 'size' in py_file

        txt_file = next(f for f in tree if f['name'] == 'readme.txt')
        assert txt_file['file_type'] == 'text'

        so_file = next(f for f in tree if f['name'] == 'hook.so')
        assert so_file['file_type'] == 'binary'

    def test_tree_nonexistent_draft_returns_404(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        response = client.get(f'/api/drafts/{fake_id}/tree', headers=auth_headers)
        assert response.status_code == 404


class TestDraftContent:
    """Tests for GET/PUT /api/drafts/<draft_id>/content endpoint."""

    def _create_draft(self, client, auth_headers, monkeypatch, preset_with_scripts):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        return resp.get_json()['data']['draft_id']

    def test_read_py_content(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.get(
            f'/api/drafts/{draft_id}/content?path=balance.py',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()['data']
        assert data['path'] == 'balance.py'
        assert 'balance plugin' in data['content']

    def test_read_txt_content(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.get(
            f'/api/drafts/{draft_id}/content?path=readme.txt',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert 'Plugin readme' in response.get_json()['data']['content']

    def test_read_so_returns_400(self, client, auth_headers, preset_with_scripts, monkeypatch):
        """Binary files cannot be read through content endpoint."""
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        scripts_dir = preset_with_scripts / 'configs' / 'presets' / 'default' / 'scripts'
        (scripts_dir / 'hook.so').write_bytes(b'\x7fELF' + b'\x00' * 100)
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.get(
            f'/api/drafts/{draft_id}/content?path=hook.so',
            headers=auth_headers
        )
        assert response.status_code == 400

    def test_write_py_content(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.put(f'/api/drafts/{draft_id}/content', json={
            'path': 'balance.py',
            'content': '# updated balance\nclass balance: pass\n'
        }, headers=auth_headers)
        assert response.status_code == 200

        # Verify content was written
        read_resp = client.get(
            f'/api/drafts/{draft_id}/content?path=balance.py',
            headers=auth_headers
        )
        assert 'updated balance' in read_resp.get_json()['data']['content']

    def test_write_txt_content(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.put(f'/api/drafts/{draft_id}/content', json={
            'path': 'readme.txt',
            'content': 'Updated readme content'
        }, headers=auth_headers)
        assert response.status_code == 200

    def test_write_so_returns_400(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.put(f'/api/drafts/{draft_id}/content', json={
            'path': 'hook.so',
            'content': 'not binary'
        }, headers=auth_headers)
        assert response.status_code == 400

    def test_write_creates_new_file(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.put(f'/api/drafts/{draft_id}/content', json={
            'path': 'new_plugin.py',
            'content': '# new plugin\n'
        }, headers=auth_headers)
        assert response.status_code == 200

    def test_path_traversal_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.get(
            f'/api/drafts/{draft_id}/content?path=../../etc/passwd',
            headers=auth_headers
        )
        assert response.status_code == 400





class TestDraftUpload:
    """Tests for POST /api/drafts/<draft_id>/upload endpoint."""

    def _create_draft(self, client, auth_headers, monkeypatch, preset_with_scripts):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        return resp.get_json()['data']['draft_id']

    def test_upload_py_file(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        data = {
            'file': (io.BytesIO(b'# new plugin\nclass Plugin: pass\n'), 'new_plugin.py')
        }
        response = client.post(
            f'/api/drafts/{draft_id}/upload',
            data=data, content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert os.path.exists(os.path.join(drafts_base, draft_id, 'scripts', 'new_plugin.py'))

    def test_upload_so_with_valid_elf(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        elf_content = b'\x7fELF' + b'\x00' * 100
        data = {
            'file': (io.BytesIO(elf_content), 'hook.so')
        }
        response = client.post(
            f'/api/drafts/{draft_id}/upload',
            data=data, content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 200
        saved = os.path.join(drafts_base, draft_id, 'scripts', 'hook.so')
        assert os.path.exists(saved)
        with open(saved, 'rb') as f:
            assert f.read() == elf_content

    def test_upload_so_with_invalid_elf_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        data = {
            'file': (io.BytesIO(b'not an elf binary'), 'bad.so')
        }
        response = client.post(
            f'/api/drafts/{draft_id}/upload',
            data=data, content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'ELF' in response.get_json()['error']['message']

    def test_upload_unsupported_extension_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        data = {
            'file': (io.BytesIO(b'data'), 'script.js')
        }
        response = client.post(
            f'/api/drafts/{draft_id}/upload',
            data=data, content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 400

    def test_upload_so_exceeding_10mb_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        # 10MB + 1 byte
        big_content = b'\x7fELF' + b'\x00' * (10 * 1024 * 1024 + 1)
        data = {
            'file': (io.BytesIO(big_content), 'huge.so')
        }
        response = client.post(
            f'/api/drafts/{draft_id}/upload',
            data=data, content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 400

    def test_upload_txt_exceeding_256kb_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        big_text = b'x' * (256 * 1024 + 1)
        data = {
            'file': (io.BytesIO(big_text), 'huge.txt')
        }
        response = client.post(
            f'/api/drafts/{draft_id}/upload',
            data=data, content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 400

    def test_upload_with_target_path(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        data = {
            'file': (io.BytesIO(b'# sub plugin\n'), 'sub.py'),
            'target_path': 'subfolder'
        }
        response = client.post(
            f'/api/drafts/{draft_id}/upload',
            data=data, content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert os.path.exists(os.path.join(drafts_base, draft_id, 'scripts', 'subfolder', 'sub.py'))


class TestDraftDeleteFile:
    """Tests for DELETE /api/drafts/<draft_id>/file endpoint."""

    def _create_draft(self, client, auth_headers, monkeypatch, preset_with_scripts):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        return resp.get_json()['data']['draft_id']

    def test_delete_file(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        file_path = os.path.join(drafts_base, draft_id, 'scripts', 'balance.py')
        assert os.path.exists(file_path)

        response = client.delete(
            f'/api/drafts/{draft_id}/file?path=balance.py',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert not os.path.exists(file_path)

    def test_delete_nonexistent_file_returns_404(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.delete(
            f'/api/drafts/{draft_id}/file?path=nope.py',
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_delete_path_traversal_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.delete(
            f'/api/drafts/{draft_id}/file?path=../../etc/passwd',
            headers=auth_headers
        )
        assert response.status_code == 400


class TestCommitDraft:
    """Tests for POST /api/drafts/<draft_id>/commit endpoint."""

    def _create_draft(self, client, auth_headers, monkeypatch, preset_with_scripts):
        monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(preset_with_scripts / 'configs'))
        resp = client.post('/api/drafts/', json={
            'source': 'preset', 'preset': 'default'
        }, headers=auth_headers)
        return resp.get_json()['data']['draft_id']

    def test_commit_to_instance_directory(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)

        # Modify a file in the draft
        client.put(f'/api/drafts/{draft_id}/content', json={
            'path': 'balance.py', 'content': '# modified\n'
        }, headers=auth_headers)

        target_dir = str(preset_with_scripts / 'configs' / 'test-host' / '1' / 'scripts')
        os.makedirs(target_dir, exist_ok=True)

        response = client.post(f'/api/drafts/{draft_id}/commit', json={
            'target': 'instance',
            'host': 'test-host',
            'instance_id': '1'
        }, headers=auth_headers)
        assert response.status_code == 200

        # Verify files were copied
        assert os.path.exists(os.path.join(target_dir, 'balance.py'))
        with open(os.path.join(target_dir, 'balance.py')) as f:
            assert f.read() == '# modified\n'

        # Verify draft was deleted
        assert not os.path.exists(os.path.join(drafts_base, draft_id))

    def test_commit_to_preset_directory(self, client, auth_headers, preset_with_scripts, monkeypatch, drafts_base):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)

        target_dir = str(preset_with_scripts / 'configs' / 'presets' / 'custom' / 'scripts')

        response = client.post(f'/api/drafts/{draft_id}/commit', json={
            'target': 'preset',
            'preset': 'custom'
        }, headers=auth_headers)
        assert response.status_code == 200
        assert os.path.exists(os.path.join(target_dir, 'balance.py'))
        assert not os.path.exists(os.path.join(drafts_base, draft_id))

    def test_commit_expired_draft_returns_404(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        response = client.post(f'/api/drafts/{fake_id}/commit', json={
            'target': 'instance', 'host': 'h', 'instance_id': '1'
        }, headers=auth_headers)
        assert response.status_code == 404

    def test_commit_preserves_binary_files(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)

        # Upload a .so file
        elf_content = b'\x7fELF' + b'\x00' * 50
        client.post(
            f'/api/drafts/{draft_id}/upload',
            data={'file': (io.BytesIO(elf_content), 'hook.so')},
            content_type='multipart/form-data',
            headers=auth_headers
        )

        target_dir = str(preset_with_scripts / 'configs' / 'test-host' / '2' / 'scripts')
        os.makedirs(target_dir, exist_ok=True)

        client.post(f'/api/drafts/{draft_id}/commit', json={
            'target': 'instance', 'host': 'test-host', 'instance_id': '2'
        }, headers=auth_headers)

        with open(os.path.join(target_dir, 'hook.so'), 'rb') as f:
            assert f.read() == elf_content

    def test_commit_path_traversal_in_host_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.post(f'/api/drafts/{draft_id}/commit', json={
            'target': 'instance', 'host': '../../etc', 'instance_id': '1'
        }, headers=auth_headers)
        assert response.status_code == 400

    def test_commit_path_traversal_in_preset_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.post(f'/api/drafts/{draft_id}/commit', json={
            'target': 'preset', 'preset': '../../etc'
        }, headers=auth_headers)
        assert response.status_code == 400

    def test_commit_cross_subtree_via_instance_rejected(self, client, auth_headers, preset_with_scripts, monkeypatch):
        draft_id = self._create_draft(client, auth_headers, monkeypatch, preset_with_scripts)
        response = client.post(f'/api/drafts/{draft_id}/commit', json={
            'target': 'instance', 'host': 'presets', 'instance_id': 'default'
        }, headers=auth_headers)
        assert response.status_code == 400
