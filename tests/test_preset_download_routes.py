import io
import json
import os
import zipfile

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import BinaryMetadata, ConfigPreset


@pytest.fixture(autouse=True)
def presets_base(tmp_path, monkeypatch):
    """Route export validation at this test's isolated presets root."""
    base = tmp_path / 'configs' / 'presets'
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr('ui.routes.preset_api_routes.PRESETS_DIR', str(base))
    return base


def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='tester')
    return {'Authorization': f'Bearer {token}'}


def write_file(path, content, mode='w'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as handle:
        handle.write(content)


def create_preset(app, tmp_path, name='export-me'):
    preset_dir = tmp_path / 'configs' / 'presets' / name
    write_file(preset_dir / 'server.cfg', 'set sv_hostname "Export Me"\n')
    write_file(preset_dir / 'motd.cfg', 'hello\n')
    write_file(preset_dir / 'notes' / 'readme.txt', 'custom note\n')
    write_file(preset_dir / 'maps' / 'arena.ent', '{ entities }\n')
    write_file(preset_dir / 'factories' / 'ca.factories', '{"factory": true}\n')
    write_file(preset_dir / 'scripts' / 'discord_extensions' / 'balance.py', 'class balance: pass\n')
    write_file(preset_dir / 'scripts' / 'requirements.txt', 'redis==5.0.0\n')
    write_file(preset_dir / 'user-hooks' / 'force_rate.so', b'\x7fELFfake', mode='wb')
    write_file(preset_dir / 'checked_plugins.json', json.dumps(['discord_extensions/balance.py']))
    write_file(preset_dir / 'checked_factories.json', json.dumps(['ca.factories']))
    write_file(preset_dir / 'scripts' / '__pycache__' / 'balance.cpython-311.pyc', b'junk', mode='wb')
    write_file(preset_dir / 'scripts' / 'temp.tmp', 'junk\n')

    with app.app_context():
        preset = ConfigPreset(
            name=name,
            description='Export test preset',
            path=str(preset_dir),
            is_builtin=False,
        )
        db.session.add(preset)
        db.session.commit()
        preset_id = preset.id
    return preset_id, preset_dir


def read_zip(response):
    return zipfile.ZipFile(io.BytesIO(response.data))


def test_download_preset_requires_authentication(client, app, tmp_path):
    preset_id, _preset_dir = create_preset(app, tmp_path)

    response = client.get(f'/api/presets/{preset_id}/download')

    assert response.status_code == 401
    assert response.mimetype != 'application/zip'


def test_download_preset_returns_zip_with_full_preset_directory(client, app, tmp_path):
    preset_id, _preset_dir = create_preset(app, tmp_path)

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 200
    assert response.mimetype == 'application/zip'
    assert 'attachment;' in response.headers['Content-Disposition']
    assert 'export-me.zip' in response.headers['Content-Disposition']

    with read_zip(response) as archive:
        names = set(archive.namelist())
        assert 'manifest.json' in names
        assert 'server.cfg' in names
        assert 'motd.cfg' in names
        assert 'notes/readme.txt' in names
        assert 'maps/arena.ent' in names
        assert 'factories/ca.factories' in names
        assert 'scripts/discord_extensions/balance.py' in names
        assert 'scripts/requirements.txt' in names
        assert 'user-hooks/force_rate.so' in names
        assert 'checked_plugins.json' in names
        assert 'checked_factories.json' in names
        assert 'scripts/__pycache__/balance.cpython-311.pyc' not in names
        assert 'scripts/temp.tmp' not in names

        manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
        assert manifest['type'] == 'qlsm-preset-export'
        assert manifest['format_version'] == 1
        assert manifest['preset']['id'] == preset_id
        assert manifest['preset']['name'] == 'export-me'
        assert manifest['preset']['description'] == 'Export test preset'
        assert manifest['includes']['preset_directory'] is True
        assert manifest['includes']['configs'] is True
        assert manifest['includes']['factories'] is True
        assert manifest['includes']['scripts'] is True
        assert manifest['includes']['user_hooks'] is True
        assert manifest['includes']['checked_plugins'] is True
        assert manifest['includes']['checked_factories'] is True
        assert manifest['includes']['binary_metadata'] is True
        assert manifest['counts']['binary_metadata'] == 0


def test_download_preset_includes_binary_metadata_json(client, app, tmp_path):
    preset_id, _preset_dir = create_preset(app, tmp_path, name='hook-meta')
    with app.app_context():
        db.session.add(BinaryMetadata(
            context_type='preset',
            context_key='hook-meta',
            file_path='force_rate.so',
            description='99k LAN rate hook',
        ))
        db.session.commit()

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 200
    with read_zip(response) as archive:
        manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
        metadata = json.loads(archive.read('binary_metadata.json').decode('utf-8'))
        assert manifest['counts']['binary_metadata'] == 1
        assert metadata == {
            'format_version': 1,
            'metadata': [
                {
                    'file_path': 'force_rate.so',
                    'description': '99k LAN rate hook',
                }
            ],
        }


def test_download_preset_skips_symlinks(client, app, tmp_path):
    preset_id, preset_dir = create_preset(app, tmp_path, name='symlink-safe')
    outside_secret = tmp_path / 'outside-secret.txt'
    outside_secret.write_text('do not export\n')
    os.symlink(outside_secret, preset_dir / 'leaked-secret.txt')
    os.symlink(tmp_path, preset_dir / 'linked-dir')

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 200
    with read_zip(response) as archive:
        names = set(archive.namelist())
        assert 'leaked-secret.txt' not in names
        assert not any(name.startswith('linked-dir/') for name in names)
        assert b'do not export' not in response.data


def test_download_preset_rejects_path_outside_presets_root(client, app, tmp_path):
    outside_dir = tmp_path / 'outside-preset-root'
    write_file(outside_dir / 'secret.txt', 'do not export\n')
    with app.app_context():
        preset = ConfigPreset(
            name='outside-root',
            description='Outside root',
            path=str(outside_dir),
            is_builtin=False,
        )
        db.session.add(preset)
        db.session.commit()
        preset_id = preset.id

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 500
    assert response.mimetype != 'application/zip'
    assert response.get_json()['error']['message'] == 'Preset path is invalid.'
    assert b'do not export' not in response.data


def test_download_preset_sanitizes_legacy_filename(client, app, tmp_path):
    preset_id, _preset_dir = create_preset(app, tmp_path, name='Unsafe Name')
    with app.app_context():
        preset = db.session.get(ConfigPreset, preset_id)
        preset.name = '../Unsafe Name\nWith Spaces'
        db.session.commit()

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 200
    disposition = response.headers['Content-Disposition']
    assert 'Unsafe-Name-With-Spaces.zip' in disposition
    assert '../' not in disposition
    assert '\n' not in disposition
    assert 'Unsafe Name\nWith Spaces' not in disposition


def test_download_missing_preset_returns_404(client, app):
    response = client.get('/api/presets/9999/download', headers=auth_headers(app))

    assert response.status_code == 404
    assert response.get_json()['error']['message'] == 'Preset not found.'


def test_download_preset_missing_directory_returns_500(client, app, presets_base):
    missing_path = presets_base / 'missing-preset-dir'
    with app.app_context():
        preset = ConfigPreset(
            name='missing-dir',
            description='Missing dir',
            path=str(missing_path),
            is_builtin=False,
        )
        db.session.add(preset)
        db.session.commit()
        preset_id = preset.id

    response = client.get(
        f'/api/presets/{preset_id}/download',
        headers=auth_headers(app),
    )

    assert response.status_code == 500
    assert response.get_json()['error']['message'] == 'Preset configuration files not found.'
