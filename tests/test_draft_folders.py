"""Tests for draft folder endpoints and empty-folder rendering."""

import os
import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def empty_draft(client, auth_headers, tmp_path, monkeypatch):
    """Create a draft seeded from an empty preset; return its draft_id."""
    scripts_dir = tmp_path / 'configs' / 'presets' / 'default' / 'scripts'
    scripts_dir.mkdir(parents=True)
    monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(tmp_path / 'configs'))
    resp = client.post('/api/drafts/', json={'source': 'preset', 'preset': 'default'}, headers=auth_headers)
    assert resp.status_code == 201
    return resp.get_json()['data']['draft_id']


@pytest.fixture
def drafts_base(app):
    return app.config['DRAFTS_BASE']


class TestEmptyFolderInTree:
    def test_empty_folder_appears_in_tree(self, client, auth_headers, empty_draft, app, drafts_base):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'extras'}, headers=auth_headers)
        assert resp.status_code == 201
        tree_resp = client.get(f'/api/drafts/{empty_draft}/tree', headers=auth_headers)
        assert tree_resp.status_code == 200
        tree = tree_resp.get_json()['data']
        assert any(item.get('type') == 'folder' and item.get('name') == 'extras' for item in tree)


class TestCreateFolder:
    def test_create_folder_201(self, client, auth_headers, empty_draft):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'foo'}, headers=auth_headers)
        assert resp.status_code == 201

    def test_create_folder_conflict(self, client, auth_headers, empty_draft):
        client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'foo'}, headers=auth_headers)
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'foo'}, headers=auth_headers)
        assert resp.status_code == 409

    def test_rejects_path_traversal(self, client, auth_headers, empty_draft):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': '../oops'}, headers=auth_headers)
        assert resp.status_code == 400

    def test_rejects_leading_dot_segment(self, client, auth_headers, empty_draft):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': '.foo'}, headers=auth_headers)
        assert resp.status_code == 400

    def test_rejects_dot_segment(self, client, auth_headers, empty_draft):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': '.'}, headers=auth_headers)
        assert resp.status_code == 400

    def test_rejects_empty_string(self, client, auth_headers, empty_draft):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': ''}, headers=auth_headers)
        assert resp.status_code == 400

    def test_rejects_whitespace_only(self, client, auth_headers, empty_draft):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': '   '}, headers=auth_headers)
        assert resp.status_code == 400

    def test_rejects_invalid_chars(self, client, auth_headers, empty_draft):
        resp = client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'foo bar'}, headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_rejects_root_via_dot_segment(self, client, auth_headers, empty_draft):
        resp = client.delete(f'/api/drafts/{empty_draft}/folders?path=.', headers=auth_headers)
        assert resp.status_code == 400

    def test_rename_rejects_traversal_in_either_arg(self, client, auth_headers, empty_draft):
        client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'good'}, headers=auth_headers)
        resp = client.patch(
            f'/api/drafts/{empty_draft}/folders',
            json={'old_path': 'good', 'new_path': '../escape'},
            headers=auth_headers,
        )
        assert resp.status_code == 400


class TestDeleteFolder:
    def test_delete_empty_folder(self, client, auth_headers, empty_draft):
        client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'gone'}, headers=auth_headers)
        resp = client.delete(f'/api/drafts/{empty_draft}/folders?path=gone', headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_nonempty_folder_recursive(self, client, auth_headers, empty_draft, app, drafts_base):
        client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'mod'}, headers=auth_headers)
        client.put(
            f'/api/drafts/{empty_draft}/content',
            json={'path': 'mod/util.py', 'content': '# x\n'},
            headers=auth_headers,
        )
        resp = client.delete(f'/api/drafts/{empty_draft}/folders?path=mod', headers=auth_headers)
        assert resp.status_code == 200


class TestRenameFolder:
    def test_rename_folder(self, client, auth_headers, empty_draft):
        client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'old'}, headers=auth_headers)
        resp = client.patch(
            f'/api/drafts/{empty_draft}/folders',
            json={'old_path': 'old', 'new_path': 'new'},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_rename_target_exists_409(self, client, auth_headers, empty_draft):
        client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'a'}, headers=auth_headers)
        client.post(f'/api/drafts/{empty_draft}/folders', json={'path': 'b'}, headers=auth_headers)
        resp = client.patch(
            f'/api/drafts/{empty_draft}/folders',
            json={'old_path': 'a', 'new_path': 'b'},
            headers=auth_headers,
        )
        assert resp.status_code == 409
