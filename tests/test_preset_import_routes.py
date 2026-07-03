import base64
import io
import json
import os
import zipfile

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import BinaryMetadata, ConfigPreset

BASE_CONFIGS = {
    'server.cfg': 'set sv_hostname "Imported"\n',
    'mappool.txt': 'campgrounds\n',
    'access.txt': '\n',
    'workshop.txt': '\n',
}


@pytest.fixture(autouse=True)
def presets_base(tmp_path, monkeypatch):
    base = tmp_path / 'configs' / 'presets'
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr('ui.routes.preset_api_routes.PRESETS_DIR', str(base))
    monkeypatch.setattr('ui.routes.preset_import_routes.PRESETS_DIR', str(base))
    return base


def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='tester')
    return {'Authorization': f'Bearer {token}'}


def make_manifest(name='imported', description='Imported preset'):
    return {
        'type': 'qlsm-preset-export',
        'format_version': 1,
        'preset': {
            'id': 1, 'name': name, 'description': description,
            'is_builtin': False, 'created_at': None, 'last_updated': None,
        },
        'includes': {}, 'counts': {'binary_metadata': 0},
    }


def build_zip(name='imported', extra=None, manifest=...):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        if manifest is ...:
            manifest = make_manifest(name)
        if manifest is not None:
            archive.writestr('manifest.json', json.dumps(manifest))
        for path, content in BASE_CONFIGS.items():
            archive.writestr(path, content)
        for path, content in (extra or {}).items():
            archive.writestr(path, content)
    buffer.seek(0)
    return buffer


def post_import(client, app, zip_buffer, filename='preset.zip', form=None):
    data = {'file': (zip_buffer, filename)}
    data.update(form or {})
    return client.post(
        '/api/presets/import',
        data=data,
        headers=auth_headers(app),
        content_type='multipart/form-data',
    )


def existing_preset(app, presets_base, name='taken', is_builtin=False):
    preset_dir = presets_base / name
    preset_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in BASE_CONFIGS.items():
        (preset_dir / filename).write_text(content)
    (preset_dir / 'old-only.cfg').write_text('stale\n')
    with app.app_context():
        preset = ConfigPreset(
            name=name, description='Old description',
            path=str(preset_dir), is_builtin=is_builtin,
        )
        db.session.add(preset)
        db.session.commit()
        return preset.id


def test_import_requires_authentication(client):
    response = client.post('/api/presets/import', data={})
    assert response.status_code == 401


def test_import_requires_file(client, app):
    response = client.post(
        '/api/presets/import', data={},
        headers=auth_headers(app), content_type='multipart/form-data',
    )
    assert response.status_code == 400
    assert 'No file provided' in response.get_json()['error']['message']


def test_import_rejects_non_zip_extension(client, app):
    response = post_import(client, app, build_zip(), filename='preset.tar.gz')
    assert response.status_code == 400
    assert '.zip' in response.get_json()['error']['message']


def test_import_rejects_corrupt_zip(client, app):
    response = post_import(client, app, io.BytesIO(b'garbage-bytes'))
    assert response.status_code == 400
    assert 'not a valid ZIP' in response.get_json()['error']['message']


def test_import_creates_new_preset(client, app, presets_base):
    zip_buffer = build_zip(extra={
        'motd.cfg': 'welcome\n',
        'factories/ca.factories': '{"id": "ca"}\n',
        'scripts/balance.py': 'class balance: pass\n',
        'scripts/highfps_hook.so': b'\x7fELFfake',
        'user-hooks/custom_hook.so': b'\x7fELFfake',
        'checked_plugins.json': json.dumps(['balance.py']),
        'checked_factories.json': json.dumps(['ca.factories']),
        'binary_metadata.json': json.dumps({'format_version': 1, 'metadata': [
            {'file_path': 'custom_hook.so', 'description': '99k hook'},
            {'file_path': 'stale.so', 'description': 'dropped'},
        ]}),
    })
    response = post_import(client, app, zip_buffer)

    assert response.status_code == 201
    data = response.get_json()['data']
    assert data['name'] == 'imported'
    assert data['description'] == 'Imported preset'
    assert data['configs']['motd.cfg'] == 'welcome\n'
    assert data['factories'] == {'ca.factories': '{"id": "ca"}\n'}
    assert data['checked_plugins'] == ['balance.py']
    assert data['checked_factories'] == ['ca.factories']
    # .so scripts must stay visible in the API response (base64, since raw
    # bytes aren't JSON-safe), not silently dropped after import.
    assert data['scripts']['highfps_hook.so'] == base64.b64encode(b'\x7fELFfake').decode('ascii')

    preset_dir = presets_base / 'imported'
    assert (preset_dir / 'server.cfg').read_text() == BASE_CONFIGS['server.cfg']
    assert (preset_dir / 'user-hooks' / 'custom_hook.so').read_bytes() == b'\x7fELFfake'
    assert (preset_dir / 'scripts' / 'highfps_hook.so').read_bytes() == b'\x7fELFfake'

    with app.app_context():
        preset = ConfigPreset.query.filter_by(name='imported').one()
        assert preset.path == str(preset_dir)
        rows = BinaryMetadata.query.filter_by(
            context_type='preset', context_key='imported',
        ).all()
        assert [(r.file_path, r.description) for r in rows] == [('custom_hook.so', '99k hook')]


def test_import_creates_preset_with_enabled_hooks(client, app, presets_base):
    zip_buffer = build_zip(extra={
        'user-hooks/custom_hook.so': b'\x7fELFfake',
        'enabled_hooks.json': json.dumps(['custom_hook.so', 'missing_hook.so']),
    })
    response = post_import(client, app, zip_buffer)

    assert response.status_code == 201
    data = response.get_json()['data']
    # missing_hook.so isn't in the archive's user-hooks/, so it's dropped —
    # a preset should never claim a hook is enabled that it doesn't ship.
    assert data['enabled_hooks'] == ['custom_hook.so']

    preset_dir = presets_base / 'imported'
    with open(preset_dir / 'enabled_hooks.json') as f:
        assert json.load(f) == ['custom_hook.so']


def test_import_preset_without_enabled_hooks_json(client, app, presets_base):
    """Legacy/no-hooks exports don't write enabled_hooks.json and return null."""
    response = post_import(client, app, build_zip())

    assert response.status_code == 201
    data = response.get_json()['data']
    assert data['enabled_hooks'] is None
    preset_dir = presets_base / 'imported'
    assert not (preset_dir / 'enabled_hooks.json').exists()


def test_import_metadata_failure_rolls_back_row_and_folder(client, app, presets_base, monkeypatch):
    def fail_metadata(*_args, **_kwargs):
        raise ValueError('forced metadata failure')

    monkeypatch.setattr('ui.routes.preset_import_routes._replace_binary_metadata', fail_metadata)

    response = post_import(client, app, build_zip(name='broken'))

    assert response.status_code == 400
    assert 'forced metadata failure' in response.get_json()['error']['message']
    assert not (presets_base / 'broken').exists()
    with app.app_context():
        assert ConfigPreset.query.filter_by(name='broken').first() is None


def test_import_invalid_archive_leaves_no_files_or_rows(client, app, presets_base):
    zip_buffer = build_zip(extra={'malware.exe': b'MZ'})
    response = post_import(client, app, zip_buffer)

    assert response.status_code == 400
    assert list(presets_base.iterdir()) == []
    with app.app_context():
        assert ConfigPreset.query.count() == 0


def test_import_duplicate_name_returns_conflict(client, app, presets_base):
    preset_id = existing_preset(app, presets_base, name='taken')

    response = post_import(client, app, build_zip(name='taken'))

    assert response.status_code == 409
    body = response.get_json()
    assert body['conflict'] == {'type': 'duplicate', 'name': 'taken', 'preset_id': preset_id}
    # No side effects: original untouched, no staging leftovers
    assert (presets_base / 'taken' / 'old-only.cfg').exists()
    assert sorted(p.name for p in presets_base.iterdir()) == ['taken']


def test_import_orphan_folder_conflict_does_not_delete_folder(client, app, presets_base):
    orphan = presets_base / 'orphan'
    orphan.mkdir()
    (orphan / 'marker.txt').write_text('keep me\n')

    response = post_import(client, app, build_zip(name='orphan'))

    assert response.status_code == 409
    assert response.get_json()['conflict']['type'] == 'invalid'
    assert (orphan / 'marker.txt').read_text() == 'keep me\n'
    with app.app_context():
        assert ConfigPreset.query.filter_by(name='orphan').first() is None


def test_import_overwrite_replaces_existing(client, app, presets_base):
    preset_id = existing_preset(app, presets_base, name='taken')

    response = post_import(
        client, app, build_zip(name='taken'),
        form={'overwrite_preset_id': str(preset_id)},
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['id'] == preset_id
    assert data['description'] == 'Imported preset'
    preset_dir = presets_base / 'taken'
    assert not (preset_dir / 'old-only.cfg').exists()
    assert (preset_dir / 'server.cfg').read_text() == BASE_CONFIGS['server.cfg']
    assert not (presets_base / 'taken.import-old').exists()


def test_import_overwrite_ignores_stale_backup_directory(client, app, presets_base):
    preset_id = existing_preset(app, presets_base, name='taken')
    stale_backup = presets_base / 'taken.import-old'
    stale_backup.mkdir()
    (stale_backup / 'marker.txt').write_text('stale backup\n')

    response = post_import(
        client, app, build_zip(name='taken'),
        form={'overwrite_preset_id': str(preset_id)},
    )

    assert response.status_code == 200
    assert (presets_base / 'taken' / 'server.cfg').read_text() == BASE_CONFIGS['server.cfg']
    assert not (presets_base / 'taken' / 'old-only.cfg').exists()
    assert (stale_backup / 'marker.txt').read_text() == 'stale backup\n'


def test_import_overwrite_builtin_returns_403(client, app, presets_base):
    preset_id = existing_preset(app, presets_base, name='housed', is_builtin=True)

    response = post_import(
        client, app, build_zip(name='housed'),
        form={'overwrite_preset_id': str(preset_id)},
    )

    assert response.status_code == 403
    assert 'built-in' in response.get_json()['error']['message']


def test_import_with_explicit_new_name(client, app, presets_base):
    existing_preset(app, presets_base, name='taken')

    response = post_import(
        client, app, build_zip(name='taken'), form={'name': 'taken-v2'},
    )

    assert response.status_code == 201
    assert response.get_json()['data']['name'] == 'taken-v2'
    assert (presets_base / 'taken-v2' / 'server.cfg').exists()


def test_import_builtin_manifest_name_conflicts_rename_only(client, app, presets_base):
    existing_preset(app, presets_base, name='default', is_builtin=True)

    response = post_import(client, app, build_zip(name='default'))

    assert response.status_code == 409
    conflict = response.get_json()['conflict']
    assert conflict['type'] == 'builtin'
    assert 'preset_id' not in conflict


def test_import_invalid_manifest_name_asks_for_rename(client, app):
    response = post_import(client, app, build_zip(name='bad name!'))

    assert response.status_code == 409
    assert response.get_json()['conflict']['type'] == 'invalid'


def test_import_rejects_invalid_explicit_name(client, app):
    response = post_import(client, app, build_zip(), form={'name': 'bad name!'})

    assert response.status_code == 400
