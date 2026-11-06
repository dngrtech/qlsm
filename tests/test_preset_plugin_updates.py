import os

import pytest

from tests.helpers import auth_headers, make_user
from ui.database import create_preset, get_preset

USER = 'presetpluginupdates'
PASSWORD = 'presetpluginupdatespass1'

MINQLX_POOL = os.path.join('ql-assets', 'data', 'minqlx-plugins')
MINQLXTENDED_POOL = os.path.join('ql-assets', 'data', 'minqlxtended-plugins')


@pytest.fixture(autouse=True)
def setup(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_user(app, USER, PASSWORD)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        f.write(content)


def _read(path):
    with open(path) as f:
        return f.read()


def _make_preset(app, name, runtime='minqlx', is_builtin=False, scripts=None):
    path = os.path.join('configs', 'presets', name)
    for filename, content in (scripts or {}).items():
        _write(os.path.join(path, 'scripts', filename), content)
    os.makedirs(path, exist_ok=True)
    with app.app_context():
        preset = create_preset(name=name, description='', path=path, runtime=runtime, is_builtin=is_builtin)
        return preset.id, path


def test_check_reports_outdated_current_and_local(client, app):
    _write(os.path.join(MINQLX_POOL, 'stale.py'), 'v2')
    _write(os.path.join(MINQLX_POOL, 'same.py'), 'same')
    _write(os.path.join(MINQLX_POOL, 'pool_only.py'), 'not in the preset')
    preset_id, _ = _make_preset(app, 'mine', scripts={
        'stale.py': 'v1', 'same.py': 'same', 'custom.py': 'preset only',
    })

    resp = client.get(f'/api/presets/{preset_id}/plugin-updates', headers=auth_headers(app, USER))

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['preset_id'] == preset_id
    assert data['runtime'] == 'minqlx'
    assert data['plugin_changes'] == [{'name': 'stale.py', 'change': 'modified'}]
    assert data['plugins'] == [
        {'name': 'custom.py', 'status': 'local'},
        {'name': 'same.py', 'status': 'current'},
        {'name': 'stale.py', 'status': 'outdated'},
    ]


def test_check_uses_the_presets_runtime_pool(client, app):
    _write(os.path.join(MINQLX_POOL, 'p.py'), 'minqlx build')
    _write(os.path.join(MINQLXTENDED_POOL, 'p.py'), 'minqlxtended build')
    preset_id, _ = _make_preset(app, 'ext', runtime='minqlxtended', scripts={'p.py': 'minqlxtended build'})

    data = client.get(f'/api/presets/{preset_id}/plugin-updates',
                      headers=auth_headers(app, USER)).get_json()['data']

    assert data['runtime'] == 'minqlxtended'
    assert data['plugin_changes'] == []
    assert data['plugins'] == [{'name': 'p.py', 'status': 'current'}]


def test_apply_selected_files_copies_from_runtime_pool_and_bumps_last_updated(client, app):
    _write(os.path.join(MINQLX_POOL, 'a.py'), 'minqlx a')
    _write(os.path.join(MINQLXTENDED_POOL, 'a.py'), 'ext a v2')
    _write(os.path.join(MINQLXTENDED_POOL, 'b.py'), 'ext b v2')
    preset_id, path = _make_preset(app, 'ext2', runtime='minqlxtended', scripts={'a.py': 'old', 'b.py': 'old'})
    with app.app_context():
        before = get_preset(preset_id).last_updated

    resp = client.post(f'/api/presets/{preset_id}/plugin-updates/apply',
                       headers=auth_headers(app, USER), json={'files': ['a.py', 'not_there.py']})

    assert resp.status_code == 200
    assert resp.get_json()['data'] == {'updated': ['a.py'], 'skipped': ['not_there.py']}
    assert _read(os.path.join(path, 'scripts', 'a.py')) == 'ext a v2'
    assert _read(os.path.join(path, 'scripts', 'b.py')) == 'old'
    assert not os.path.exists(os.path.join(path, 'scripts', 'not_there.py'))
    with app.app_context():
        assert get_preset(preset_id).last_updated > before


def test_apply_all_updates_every_outdated_file(client, app):
    _write(os.path.join(MINQLX_POOL, 'a.py'), 'a v2')
    _write(os.path.join(MINQLX_POOL, 'b.py'), 'b v2')
    preset_id, path = _make_preset(app, 'all', scripts={'a.py': 'a v1', 'b.py': 'b v1', 'c.py': 'local'})

    resp = client.post(f'/api/presets/{preset_id}/plugin-updates/apply',
                       headers=auth_headers(app, USER), json={'all': True})

    assert resp.status_code == 200
    assert resp.get_json()['data'] == {'updated': ['a.py', 'b.py'], 'skipped': []}
    assert _read(os.path.join(path, 'scripts', 'a.py')) == 'a v2'
    assert _read(os.path.join(path, 'scripts', 'c.py')) == 'local'


def test_apply_never_writes_a_path_outside_scripts(client, app):
    _write(os.path.join(MINQLX_POOL, 'a.py'), 'a v2')
    preset_id, _ = _make_preset(app, 'safe', scripts={'a.py': 'a v1'})

    resp = client.post(f'/api/presets/{preset_id}/plugin-updates/apply',
                       headers=auth_headers(app, USER), json={'files': ['../a.py']})

    assert resp.status_code == 200
    assert resp.get_json()['data'] == {'updated': [], 'skipped': ['../a.py']}


@pytest.mark.parametrize('body', [{}, {'files': []}, {'files': 'a.py'}, {'files': [1]}])
def test_apply_rejects_bad_selection(client, app, body):
    preset_id, _ = _make_preset(app, 'bad')
    resp = client.post(f'/api/presets/{preset_id}/plugin-updates/apply',
                       headers=auth_headers(app, USER), json=body)
    assert resp.status_code == 400


def test_builtin_preset_is_refused(client, app):
    _write(os.path.join(MINQLX_POOL, 'a.py'), 'a v2')
    preset_id, path = _make_preset(app, 'default', is_builtin=True, scripts={'a.py': 'a v1'})
    headers = auth_headers(app, USER)

    assert client.get(f'/api/presets/{preset_id}/plugin-updates', headers=headers).status_code == 403
    resp = client.post(f'/api/presets/{preset_id}/plugin-updates/apply', headers=headers, json={'all': True})
    assert resp.status_code == 403
    assert _read(os.path.join(path, 'scripts', 'a.py')) == 'a v1'


def test_unknown_preset_is_404(client, app):
    headers = auth_headers(app, USER)
    assert client.get('/api/presets/999/plugin-updates', headers=headers).status_code == 404
    assert client.post('/api/presets/999/plugin-updates/apply', headers=headers, json={'all': True}).status_code == 404


def test_check_all_lists_user_presets_only(client, app):
    _write(os.path.join(MINQLX_POOL, 'a.py'), 'a v2')
    user_id, _ = _make_preset(app, 'user', scripts={'a.py': 'a v1'})
    _make_preset(app, 'default', is_builtin=True, scripts={'a.py': 'a v1'})

    resp = client.get('/api/presets/plugin-updates', headers=auth_headers(app, USER))

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert [p['preset_id'] for p in data] == [user_id]
    assert data[0]['plugin_changes'] == [{'name': 'a.py', 'change': 'modified'}]


def test_requires_auth(client, app):
    preset_id, _ = _make_preset(app, 'anon')
    assert client.get(f'/api/presets/{preset_id}/plugin-updates').status_code == 401
