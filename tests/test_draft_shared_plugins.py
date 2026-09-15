"""Shared-pool plugins in the draft tree (ui/plugin_pool.py + draft_routes).

The Plugins tab lists root plugins from the draft runtime's shared pool next
to the draft's own files, since deploy backfills them onto every instance.
"""

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import ConfigPreset
from ui.plugin_pool import list_shared_plugins


@pytest.fixture
def auth_headers(app):
    with app.app_context():
        token = create_access_token(identity='testuser')
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def pool(tmp_path, monkeypatch):
    """A minqlxtended shared pool with one shared-only plugin, one plugin the
    preset also holds, and the files that must never become rows."""
    base = tmp_path / 'assets'
    root = base / 'minqlxtended-plugins'
    (root / 'helpers').mkdir(parents=True)
    (root / 'hello_qlsm.py').write_text('# shared hello\n')
    (root / 'balance.py').write_text('# pool balance\n')
    (root / '__init__.py').write_text('')
    (root / 'serverchecker.py').write_text('# system plugin\n')
    (root / 'README.md').write_text('readme\n')
    (root / 'helpers' / 'util.py').write_text('# helper\n')
    (root / 'hello_qlsm.ql-plugin.json').write_text('{"label": "Hello QLSM"}')
    monkeypatch.setattr('ui.plugin_pool.POOL_BASE', str(base))
    monkeypatch.setattr('ui.plugin_manifest.MINQLXTENDED_PLUGINS_POOL_DIR', str(root))
    monkeypatch.setattr('ui.plugin_manifest.MINQLX_PLUGINS_POOL_DIR', str(tmp_path / 'no-minqlx-pool'))
    return root


@pytest.fixture
def preset(app, tmp_path, monkeypatch):
    scripts = tmp_path / 'configs' / 'presets' / 'default' / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'balance.py').write_text('# local balance\n')
    monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(tmp_path / 'configs'))
    with app.app_context():
        db.session.add(ConfigPreset(name='default', path=str(scripts.parent), runtime='minqlxtended'))
        db.session.commit()
    return scripts


def _draft(client, auth_headers, **extra):
    body = {'source': 'preset', 'preset': 'default', **extra}
    resp = client.post('/api/drafts/', json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()['data']['draft_id']


def _tree(client, auth_headers, draft_id):
    return client.get(f'/api/drafts/{draft_id}/tree', headers=auth_headers).get_json()['data']


def test_list_shared_plugins_skips_non_plugins(pool):
    assert set(list_shared_plugins('minqlxtended')) == {'hello_qlsm.py', 'balance.py'}


def test_list_shared_plugins_is_empty_for_unknown_runtime(pool):
    assert list_shared_plugins(None) == {}
    assert list_shared_plugins('quake3') == {}


def test_tree_adds_shared_only_plugin_with_manifest(client, auth_headers, pool, preset):
    tree = _tree(client, auth_headers, _draft(client, auth_headers, target_runtime='minqlxtended'))

    hello = next(f for f in tree if f['name'] == 'hello_qlsm.py')
    assert hello['shared'] is True
    assert hello['path'] == 'hello_qlsm.py'
    assert hello['plugin_manifest'] == {'label': 'Hello QLSM'}
    names = [f['name'] for f in tree]
    assert '__init__.py' not in names
    assert 'serverchecker.py' not in names
    assert 'util.py' not in names and 'helpers' not in names


def test_tree_prefers_the_drafts_own_copy(client, auth_headers, pool, preset):
    tree = _tree(client, auth_headers, _draft(client, auth_headers, target_runtime='minqlxtended'))

    balances = [f for f in tree if f['name'] == 'balance.py']
    assert len(balances) == 1
    assert 'shared' not in balances[0]


def test_tree_has_no_shared_rows_without_a_runtime(app, client, auth_headers, pool, tmp_path, monkeypatch):
    scripts = tmp_path / 'configs' / 'presets' / 'default' / 'scripts'
    scripts.mkdir(parents=True)
    monkeypatch.setattr('ui.routes.draft_routes.CONFIGS_BASE', str(tmp_path / 'configs'))

    tree = _tree(client, auth_headers, _draft(client, auth_headers))

    assert not any(f.get('shared') for f in tree)


def test_content_falls_back_to_shared_pool(client, auth_headers, pool, preset):
    draft_id = _draft(client, auth_headers, target_runtime='minqlxtended')

    resp = client.get(f'/api/drafts/{draft_id}/content?path=hello_qlsm.py', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()['data']['content'] == '# shared hello\n'

    file_resp = client.get(f'/api/drafts/{draft_id}/file?path=hello_qlsm.py', headers=auth_headers)
    assert file_resp.status_code == 200
    assert file_resp.data == b'# shared hello\n'


def test_content_fallback_rejects_nested_paths(client, auth_headers, pool, preset):
    draft_id = _draft(client, auth_headers, target_runtime='minqlxtended')

    resp = client.get(f'/api/drafts/{draft_id}/content?path=helpers/util.py', headers=auth_headers)
    assert resp.status_code == 404


def test_editing_a_shared_plugin_makes_a_local_copy(client, auth_headers, pool, preset):
    draft_id = _draft(client, auth_headers, target_runtime='minqlxtended')

    put = client.put(f'/api/drafts/{draft_id}/content', json={
        'path': 'hello_qlsm.py', 'content': '# customized\n',
    }, headers=auth_headers)
    assert put.status_code == 200, put.get_json()

    tree = _tree(client, auth_headers, draft_id)
    hellos = [f for f in tree if f['name'] == 'hello_qlsm.py']
    assert len(hellos) == 1
    assert 'shared' not in hellos[0]
    assert (pool / 'hello_qlsm.py').read_text() == '# shared hello\n'
