"""Tests for BinaryMetadata propagation on preset create/update."""

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import BinaryMetadata, ConfigPreset


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def presets_base(tmp_path, monkeypatch):
    """Isolated presets directory; patch PRESETS_DIR in preset_api_routes."""
    base = tmp_path / 'configs' / 'presets'
    base.mkdir(parents=True)
    monkeypatch.setattr('ui.routes.preset_api_routes.PRESETS_DIR', str(base))
    return base


def _seed_meta(app, context_type, context_key, file_path, description):
    with app.app_context():
        db.session.add(BinaryMetadata(
            context_type=context_type,
            context_key=context_key,
            file_path=file_path,
            description=description,
        ))
        db.session.commit()


def _get_meta(app, context_type, context_key, file_path):
    with app.app_context():
        row = BinaryMetadata.query.filter_by(
            context_type=context_type,
            context_key=context_key,
            file_path=file_path,
        ).first()
        return row.description if row else None


class TestPresetCreateCopiesMeta:

    def test_copies_instance_meta_to_new_preset(
        self, app, client, auth_headers, presets_base,
    ):
        _seed_meta(app, 'instance', '3', 'hook.so', 'Speed hook')

        resp = client.post('/api/presets/', json={
            'name': 'mypreset',
            'binary_meta_source': {'context_type': 'instance', 'context_key': '3'},
        }, headers=auth_headers)
        assert resp.status_code == 201

        assert _get_meta(app, 'preset', 'mypreset', 'hook.so') == 'Speed hook'

    def test_copies_instance_meta_even_when_key_matches_target_name(
        self, app, client, auth_headers, presets_base,
    ):
        _seed_meta(app, 'instance', 'same-name', 'hook.so', 'Instance hook')

        resp = client.post('/api/presets/', json={
            'name': 'same-name',
            'binary_meta_source': {
                'context_type': 'instance',
                'context_key': 'same-name',
            },
        }, headers=auth_headers)
        assert resp.status_code == 201

        assert _get_meta(app, 'preset', 'same-name', 'hook.so') == 'Instance hook'

    def test_copies_preset_meta_to_new_preset_when_name_differs(
        self, app, client, auth_headers, presets_base,
    ):
        _seed_meta(app, 'preset', 'default', 'hook.so', 'Default hook')

        resp = client.post('/api/presets/', json={
            'name': 'competitive',
            'binary_meta_source': {
                'context_type': 'preset',
                'context_key': 'default',
            },
        }, headers=auth_headers)
        assert resp.status_code == 201

        assert _get_meta(app, 'preset', 'competitive', 'hook.so') == 'Default hook'

    def test_skips_copy_when_source_and_target_are_same_preset(
        self, app, client, auth_headers, presets_base,
    ):
        _seed_meta(app, 'preset', 'default', 'hook.so', 'Existing')

        resp = client.post('/api/presets/', json={
            'name': 'default',
            'binary_meta_source': {
                'context_type': 'preset',
                'context_key': 'default',
            },
        }, headers=auth_headers)
        assert resp.status_code == 201

        with app.app_context():
            count = BinaryMetadata.query.filter_by(
                context_type='preset',
                context_key='default',
                file_path='hook.so',
            ).count()
        assert count == 1

    def test_no_meta_rows_created_without_binary_meta_source(
        self, app, client, auth_headers, presets_base,
    ):
        resp = client.post(
            '/api/presets/',
            json={'name': 'empty-preset'},
            headers=auth_headers,
        )
        assert resp.status_code == 201

        with app.app_context():
            count = BinaryMetadata.query.filter_by(
                context_type='preset',
                context_key='empty-preset',
            ).count()
        assert count == 0

    def test_source_rows_are_not_deleted_after_copy(
        self, app, client, auth_headers, presets_base,
    ):
        _seed_meta(app, 'instance', '3', 'hook.so', 'Speed hook')

        client.post('/api/presets/', json={
            'name': 'newpreset',
            'binary_meta_source': {'context_type': 'instance', 'context_key': '3'},
        }, headers=auth_headers)

        assert _get_meta(app, 'instance', '3', 'hook.so') == 'Speed hook'


class TestPresetUpdateCopiesMeta:

    def _create_preset(self, app, presets_base, name='mypreset'):
        """Create a minimal preset record in the DB for update tests."""
        preset_dir = presets_base / name
        preset_dir.mkdir(parents=True, exist_ok=True)
        with app.app_context():
            preset = ConfigPreset(name=name, path=str(preset_dir))
            db.session.add(preset)
            db.session.commit()
            return preset.id

    def test_copies_instance_meta_on_update(
        self, app, client, auth_headers, presets_base,
    ):
        preset_id = self._create_preset(app, presets_base)
        _seed_meta(app, 'instance', '5', 'hook.so', 'Updated hook')

        resp = client.put(f'/api/presets/{preset_id}', json={
            'binary_meta_source': {'context_type': 'instance', 'context_key': '5'},
        }, headers=auth_headers)
        assert resp.status_code == 200

        assert _get_meta(app, 'preset', 'mypreset', 'hook.so') == 'Updated hook'

    def test_overwrites_existing_preset_meta_on_update(
        self, app, client, auth_headers, presets_base,
    ):
        preset_id = self._create_preset(app, presets_base)
        _seed_meta(app, 'preset', 'mypreset', 'hook.so', 'Old description')
        _seed_meta(app, 'instance', '5', 'hook.so', 'New description')

        client.put(f'/api/presets/{preset_id}', json={
            'binary_meta_source': {'context_type': 'instance', 'context_key': '5'},
        }, headers=auth_headers)

        assert _get_meta(app, 'preset', 'mypreset', 'hook.so') == 'New description'

    def test_renames_existing_preset_meta_on_preset_rename(
        self, app, client, auth_headers, presets_base,
    ):
        preset_id = self._create_preset(app, presets_base, name='oldpreset')
        _seed_meta(app, 'preset', 'oldpreset', 'hook.so', 'Kept description')

        resp = client.put(f'/api/presets/{preset_id}', json={'name': 'newpreset'},
                          headers=auth_headers)
        assert resp.status_code == 200

        assert _get_meta(app, 'preset', 'newpreset', 'hook.so') == 'Kept description'
        assert _get_meta(app, 'preset', 'oldpreset', 'hook.so') is None

    def test_no_copy_when_binary_meta_source_absent_on_update(
        self, app, client, auth_headers, presets_base,
    ):
        preset_id = self._create_preset(app, presets_base)
        _seed_meta(app, 'preset', 'mypreset', 'hook.so', 'Untouched')

        client.put(
            f'/api/presets/{preset_id}',
            json={'description': 'updated desc'},
            headers=auth_headers,
        )

        assert _get_meta(app, 'preset', 'mypreset', 'hook.so') == 'Untouched'
