"""Tests for the binary metadata API endpoints."""

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import BinaryMetadata

ELF = b'\x7fELF' + b'\x00' * 100


@pytest.fixture
def drafts_base(app):
    """Return the per-test isolated drafts base directory from app config."""
    return app.config['DRAFTS_BASE']


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def preset_with_scripts(tmp_path):
    scripts_dir = tmp_path / 'configs' / 'presets' / 'default' / 'scripts'
    scripts_dir.mkdir(parents=True)
    (scripts_dir / 'balance.py').write_text('# plugin\n')
    (scripts_dir / 'hook.so').write_bytes(ELF)
    return tmp_path


def _create_draft(client, auth_headers, monkeypatch, preset_with_scripts, drafts_base):
    monkeypatch.setattr(
        'ui.routes.draft_routes.CONFIGS_BASE',
        str(preset_with_scripts / 'configs'),
    )
    resp = client.post(
        '/api/drafts/',
        json={'source': 'preset', 'preset': 'default'},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.get_json()['data']['draft_id']


class TestGetBinaryMeta:

    def test_returns_empty_string_when_no_row_exists(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.get(
            f'/api/drafts/{draft_id}/binary-meta'
            '?path=hook.so&context_type=instance&context_key=1',
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['description'] == ''

    def test_returns_saved_description(
        self, app, client, auth_headers, monkeypatch, preset_with_scripts,
        drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        with app.app_context():
            db.session.add(BinaryMetadata(
                context_type='instance',
                context_key='1',
                file_path='hook.so',
                description='Speed hook',
            ))
            db.session.commit()

        resp = client.get(
            f'/api/drafts/{draft_id}/binary-meta'
            '?path=hook.so&context_type=instance&context_key=1',
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['description'] == 'Speed hook'

    def test_missing_params_returns_400(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.get(
            f'/api/drafts/{draft_id}/binary-meta?context_type=instance&context_key=1',
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_non_so_path_returns_400(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.get(
            f'/api/drafts/{draft_id}/binary-meta'
            '?path=balance.py&context_type=instance&context_key=1',
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert 'Only .so' in resp.get_json()['error']['message']

    def test_invalid_draft_returns_400(self, client, auth_headers):
        resp = client.get(
            '/api/drafts/not-a-uuid/binary-meta'
            '?path=hook.so&context_type=instance&context_key=1',
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_unknown_draft_returns_404(self, client, auth_headers):
        resp = client.get(
            '/api/drafts/00000000-0000-4000-8000-000000000000/binary-meta'
            '?path=hook.so&context_type=instance&context_key=1',
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestSaveBinaryMeta:

    def test_saves_valid_description(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'hook.so',
                'description': 'Speed hook',
                'context_type': 'instance',
                'context_key': '1',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['description'] == 'Speed hook'

    def test_upserts_on_second_patch(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        payload = {
            'path': 'hook.so',
            'description': 'First',
            'context_type': 'instance',
            'context_key': '1',
        }
        client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json=payload,
            headers=auth_headers,
        )
        payload['description'] = 'Updated'
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['description'] == 'Updated'

    def test_strips_whitespace(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'hook.so',
                'description': '  trimmed  ',
                'context_type': 'instance',
                'context_key': '1',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['description'] == 'trimmed'

    def test_allows_empty_description(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'hook.so',
                'description': '',
                'context_type': 'instance',
                'context_key': '1',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['description'] == ''

    def test_rejects_description_over_1000_chars(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'hook.so',
                'description': 'x' * 1001,
                'context_type': 'instance',
                'context_key': '1',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert '1000' in resp.get_json()['error']['message']

    @pytest.mark.parametrize('bad_char', ['<', '>', '{', '}', '"'])
    def test_rejects_forbidden_characters(
        self, bad_char, client, auth_headers, monkeypatch, preset_with_scripts,
        drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'hook.so',
                'description': f'bad {bad_char} char',
                'context_type': 'instance',
                'context_key': '1',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert 'invalid characters' in resp.get_json()['error']['message']

    def test_rejects_non_so_path(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'balance.py',
                'description': 'test',
                'context_type': 'instance',
                'context_key': '1',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert 'Only .so' in resp.get_json()['error']['message']

    def test_rejects_invalid_context_type(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'hook.so',
                'description': 'ok',
                'context_type': 'draft',
                'context_key': '1',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_rejects_path_traversal_in_context_key(
        self, client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
    ):
        draft_id = _create_draft(
            client, auth_headers, monkeypatch, preset_with_scripts, drafts_base,
        )
        resp = client.patch(
            f'/api/drafts/{draft_id}/binary-meta',
            json={
                'path': 'hook.so',
                'description': 'ok',
                'context_type': 'instance',
                'context_key': '../evil',
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
