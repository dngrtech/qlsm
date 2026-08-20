"""Anything that falls back to "the default preset" must resolve it per runtime.

minqlx and minqlxtended are hard forks: a plugin written for one raises
ImportError on the other. Hardcoding the preset name 'default' therefore always
means "the minqlx one", and the wrong-runtime files are invisible until every
plugin fails to load on the running server.
"""
import os

import pytest
from unittest.mock import patch
from flask_jwt_extended import create_access_token

from ui import db
from ui.database import create_host, create_preset
from ui.models import HostStatus
from ui.preset_support import default_preset_name_for_runtime
from ui.routes.preset_api_routes import _read_preset_scripts
from ui.runtime import MINQLX, MINQLXTENDED


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(content)


def _seed_builtin_presets(root):
    """Two builtin presets whose scripts/ share a filename but not its content.

    The shared filename is the point: the on-host baseline backfill runs with
    --ignore-existing, so a wrong-runtime file of the same name is never
    corrected afterwards.
    """
    for name, runtime, marker in (
        ('default', MINQLX, 'import minqlx'),
        ('default-minqlxtended', MINQLXTENDED, 'import minqlxtended'),
    ):
        path = os.path.join(root, 'configs', 'presets', '_builtin', name)
        _write(os.path.join(path, 'scripts', 'balance.py'), marker)
        _write(os.path.join(path, 'scripts', f'{name}-only.py'), marker)
        create_preset(name=name, path=path, is_builtin=True, runtime=runtime)


def test_default_preset_name_resolves_per_runtime():
    assert default_preset_name_for_runtime(MINQLX) == 'default'
    assert default_preset_name_for_runtime(MINQLXTENDED) == 'default-minqlxtended'
    # Unknown and NULL predate the runtime column, where only minqlx existed.
    assert default_preset_name_for_runtime(None) == 'default'
    assert default_preset_name_for_runtime('nonsense') == 'default'


@pytest.mark.parametrize(
    'host_runtime,expected_marker,expected_only_file',
    [
        (MINQLX, 'import minqlx', 'default-only.py'),
        (MINQLXTENDED, 'import minqlxtended', 'default-minqlxtended-only.py'),
    ],
)
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
@patch('ui.routes.instance_routes.enqueue_task')
def test_create_instance_without_a_draft_seeds_the_hosts_runtime(
    mock_enqueue, mock_lock, client, app, tmp_path, monkeypatch,
    host_runtime, expected_marker, expected_only_file,
):
    """draft_id is optional on POST /api/instances, so the no-draft fallback is
    a live path for API clients and for the UI after a draft-creation failure.
    """
    monkeypatch.chdir(tmp_path)
    mock_enqueue.return_value = type('Job', (), {'id': 'fake-job-id'})()

    with app.app_context():
        _seed_builtin_presets(str(tmp_path))
        host = create_host(
            name=f'seed-host-{host_runtime}', provider='vultr',
            status=HostStatus.ACTIVE, runtime=host_runtime,
        )
        db.session.commit()
        host_id, host_name = host.id, host.name
        token = create_access_token(identity='testuser')

    response = client.post(
        '/api/instances/',
        json={
            'name': f'seed-inst-{host_runtime}', 'host_id': host_id, 'port': 27960,
            'hostname': 'seed.example.com',
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 201, response.json

    scripts_dir = os.path.join(
        str(tmp_path), 'configs', host_name, str(response.json['data']['id']), 'scripts',
    )
    with open(os.path.join(scripts_dir, 'balance.py'), 'r', encoding='utf-8') as handle:
        assert handle.read() == expected_marker
    assert expected_only_file in os.listdir(scripts_dir)
    assert len([n for n in os.listdir(scripts_dir) if n.endswith('-only.py')]) == 1


def test_reading_a_minqlxtended_preset_merges_the_minqlxtended_default(
    app, tmp_path, monkeypatch,
):
    """_read_preset_scripts() overlays the builtin default beneath a saved
    preset. Reading a minqlxtended preset must not drag ~50 minqlx plugins in
    under its own."""
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        _seed_builtin_presets(str(tmp_path))
        preset_path = os.path.join(str(tmp_path), 'configs', 'presets', 'my-tended')
        _write(os.path.join(preset_path, 'scripts', 'custom.py'), 'import minqlxtended')
        preset = create_preset(
            name='my-tended', path=preset_path, runtime=MINQLXTENDED,
        )

        scripts = _read_preset_scripts(preset.path, preset.runtime)

    assert set(scripts) == {
        'custom.py', 'balance.py', 'default-minqlxtended-only.py',
    }
    assert scripts['balance.py'] == 'import minqlxtended'


def test_reading_a_minqlx_preset_still_merges_the_minqlx_default(
    app, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        _seed_builtin_presets(str(tmp_path))
        preset_path = os.path.join(str(tmp_path), 'configs', 'presets', 'my-classic')
        _write(os.path.join(preset_path, 'scripts', 'custom.py'), 'import minqlx')
        preset = create_preset(name='my-classic', path=preset_path, runtime=MINQLX)

        scripts = _read_preset_scripts(preset.path, preset.runtime)

    assert set(scripts) == {'custom.py', 'balance.py', 'default-only.py'}
    assert scripts['balance.py'] == 'import minqlx'


def test_reading_a_builtin_default_does_not_merge_itself(app, tmp_path, monkeypatch):
    """The self-merge guard has to compare against the runtime's own default
    name, not the literal string 'default'."""
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        _seed_builtin_presets(str(tmp_path))
        path = os.path.join(
            str(tmp_path), 'configs', 'presets', '_builtin', 'default-minqlxtended',
        )
        scripts = _read_preset_scripts(path, MINQLXTENDED)

    assert set(scripts) == {'balance.py', 'default-minqlxtended-only.py'}
