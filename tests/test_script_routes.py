"""Tests for script management API routes."""

import pytest
import os
import tempfile
import shutil
from flask_jwt_extended import create_access_token


@pytest.fixture
def scripts_dir(app):
    """Create a temporary scripts directory structure for testing."""
    # Create temp directory for test scripts
    with app.app_context():
        base_dir = os.path.join(tempfile.gettempdir(), 'test_qlds_scripts')
        preset_scripts = os.path.join(base_dir, 'presets', 'default', 'scripts')
        instance_scripts = os.path.join(base_dir, 'test-host', '1', 'scripts')

        os.makedirs(preset_scripts, exist_ok=True)
        os.makedirs(instance_scripts, exist_ok=True)

        # Create test files in preset
        with open(os.path.join(preset_scripts, 'test_plugin.py'), 'w') as f:
            f.write('# Test plugin\nprint("hello")\n')

        with open(os.path.join(preset_scripts, 'another.py'), 'w') as f:
            f.write('# Another plugin\nx = 1\n')

        # Create subfolder with file
        subfolder = os.path.join(preset_scripts, 'extras')
        os.makedirs(subfolder, exist_ok=True)
        with open(os.path.join(subfolder, 'extra_plugin.py'), 'w') as f:
            f.write('# Extra plugin\ndef foo(): pass\n')

        # Create test file in instance scripts
        with open(os.path.join(instance_scripts, 'instance_plugin.py'), 'w') as f:
            f.write('# Instance plugin\nclass Plugin: pass\n')

        yield base_dir

        # Cleanup
        shutil.rmtree(base_dir, ignore_errors=True)


@pytest.fixture
def auth_headers(app):
    """Generate JWT auth headers for testing."""
    with app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


class TestGetScriptTree:
    """Tests for GET /api/scripts/tree endpoint."""

    def test_tree_returns_empty_for_nonexistent_path(self, client, app, auth_headers):
        """Test that tree returns empty list when scripts dir doesn't exist."""
        response = client.get(
            '/api/scripts/tree?preset=nonexistent',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json['data'] == []

    def test_tree_returns_structure(self, client, app, scripts_dir, auth_headers, monkeypatch):
        """Test that tree returns correct file structure."""
        # Patch the CONFIGS_BASE to use our test directory
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        response = client.get(
            '/api/scripts/tree?preset=default',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json['data']

        # Should have files and folders
        names = [item['name'] for item in data]
        assert 'test_plugin.py' in names
        assert 'another.py' in names
        assert 'extras' in names

        # Check extras folder has children
        extras = next(item for item in data if item['name'] == 'extras')
        assert extras['type'] == 'folder'
        assert len(extras['children']) == 1
        assert extras['children'][0]['name'] == 'extra_plugin.py'

    def test_tree_requires_auth(self, client):
        """Test that tree endpoint requires authentication."""
        response = client.get('/api/scripts/tree')
        assert response.status_code == 401


class TestGetScriptContent:
    """Tests for GET /api/scripts/content endpoint."""

    def test_content_requires_path(self, client, auth_headers):
        """Test that path parameter is required."""
        response = client.get(
            '/api/scripts/content',
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'Path parameter is required' in response.json['error']['message']

    def test_content_returns_file(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that content returns file contents."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        response = client.get(
            '/api/scripts/content?path=test_plugin.py&preset=default',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json['data']['path'] == 'test_plugin.py'
        assert '# Test plugin' in response.json['data']['content']

    def test_content_returns_subfolder_file(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that content returns files in subfolders."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        response = client.get(
            '/api/scripts/content?path=extras/extra_plugin.py&preset=default',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert '# Extra plugin' in response.json['data']['content']

    def test_content_rejects_non_py(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that only .py files can be read."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        # Create a non-py file to test against
        preset_scripts = os.path.join(scripts_dir, 'presets', 'default', 'scripts')
        with open(os.path.join(preset_scripts, 'readme.txt'), 'w') as f:
            f.write('This is a readme')

        response = client.get(
            '/api/scripts/content?path=readme.txt&preset=default',
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'Only .py files' in response.json['error']['message']

    def test_content_prevents_path_traversal(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that path traversal is prevented."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        response = client.get(
            '/api/scripts/content?path=../../../etc/passwd&preset=default',
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'Invalid path' in response.json['error']['message']


class TestSaveScriptContent:
    """Tests for PUT /api/scripts/content endpoint."""

    def test_save_requires_fields(self, client, auth_headers):
        """Test that required fields are validated."""
        response = client.put(
            '/api/scripts/content',
            json={'content': 'test'},
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'required' in response.json['error']['message']

    def test_save_creates_file(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that save creates/updates file."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        response = client.put(
            '/api/scripts/content',
            json={
                'host': 'test-host',
                'instance_id': 1,
                'path': 'new_plugin.py',
                'content': '# New plugin\nprint("new")\n'
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        assert 'saved successfully' in response.json['data']['message']

        # Verify file was created
        file_path = os.path.join(scripts_dir, 'test-host', '1', 'scripts', 'new_plugin.py')
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert '# New plugin' in f.read()

    def test_save_rejects_non_py(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that only .py files can be saved."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        response = client.put(
            '/api/scripts/content',
            json={
                'host': 'test-host',
                'instance_id': 1,
                'path': 'malicious.sh',
                'content': 'rm -rf /'
            },
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'Only .py files' in response.json['error']['message']


class TestValidateScript:
    """Tests for POST /api/scripts/validate endpoint."""

    def test_validate_valid_python(self, client, auth_headers):
        """Test validation of valid Python code."""
        response = client.post(
            '/api/scripts/validate',
            json={'content': 'def hello():\n    print("world")\n'},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json['data']['valid'] is True
        assert response.json['data']['errors'] == []

    def test_validate_invalid_python(self, client, auth_headers):
        """Test validation of invalid Python code."""
        response = client.post(
            '/api/scripts/validate',
            json={'content': 'def hello(\n    print("unclosed'},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json['data']['valid'] is False
        assert len(response.json['data']['errors']) > 0

    def test_validate_requires_content(self, client, auth_headers):
        """Test that content is required."""
        # Send JSON with a different key but no 'content' key
        response = client.post(
            '/api/scripts/validate',
            json={'other_field': 'value'},
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'content is required' in response.json['error']['message']


class TestUploadScript:
    """Tests for POST /api/scripts/upload endpoint."""

    def test_upload_requires_file(self, client, auth_headers):
        """Test that file is required."""
        response = client.post(
            '/api/scripts/upload',
            data={'host': 'test-host', 'instance_id': '1'},
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'No file provided' in response.json['error']['message']

    def test_upload_rejects_non_py(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that only .py files can be uploaded."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        from io import BytesIO
        data = {
            'file': (BytesIO(b'malicious content'), 'script.sh'),
            'host': 'test-host',
            'instance_id': '1'
        }
        response = client.post(
            '/api/scripts/upload',
            data=data,
            content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 400
        assert 'Only .py files' in response.json['error']['message']

    def test_upload_accepts_py(self, client, scripts_dir, auth_headers, monkeypatch):
        """Test that .py files are uploaded successfully."""
        monkeypatch.setattr('ui.routes.script_routes.CONFIGS_BASE', scripts_dir)

        from io import BytesIO
        data = {
            'file': (BytesIO(b'# Uploaded plugin\nprint("hi")\n'), 'uploaded.py'),
            'host': 'test-host',
            'instance_id': '1'
        }
        response = client.post(
            '/api/scripts/upload',
            data=data,
            content_type='multipart/form-data',
            headers=auth_headers
        )
        assert response.status_code == 200
        assert 'uploaded successfully' in response.json['data']['message']

        # Verify file was created
        file_path = os.path.join(scripts_dir, 'test-host', '1', 'scripts', 'uploaded.py')
        assert os.path.exists(file_path)
