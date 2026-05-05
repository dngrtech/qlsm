import os
import shutil
import pytest
from tests.helpers import make_user, auth_headers
from ui.models import ConfigPreset
from ui import db
from ui.database import create_preset

DEFAULT_USER = 'presetadmin'
DEFAULT_PASS = 'presetpass1'
BASE_CONFIG_MAP = {
    'server.cfg': '',
    'mappool.txt': '',
    'access.txt': '',
    'workshop.txt': '',
}


def _create_preset_folder(app, name, files=None, factories=None):
    preset_path = os.path.join('configs', 'presets', name)
    with app.app_context():
        os.makedirs(preset_path, exist_ok=True)
        for filename, content in (files or {}).items():
            with open(os.path.join(preset_path, filename), 'w') as f:
                f.write(content)
        if factories is not None:
            factories_dir = os.path.join(preset_path, 'factories')
            os.makedirs(factories_dir, exist_ok=True)
            for filename, content in factories.items():
                with open(os.path.join(factories_dir, filename), 'w') as f:
                    f.write(content)
        preset = create_preset(name=name, description='', path=preset_path)
        return preset.id, preset_path


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


@pytest.fixture(autouse=True)
def cleanup_preset_dirs(tmp_path, monkeypatch):
    """Redirect preset filesystem writes to a temp directory."""
    monkeypatch.chdir(tmp_path)
    yield
    # Cleanup handled by tmp_path fixture


# --- GET /api/presets/validate-name ---

def test_validate_preset_name_valid(client, app):
    """Valid unused name returns is_valid=True."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/validate-name?name=my-preset', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['is_valid'] is True
    assert data['data']['error'] is None


def test_validate_preset_name_reserved(client, app, tmp_path, monkeypatch):
    """Name owned by a built-in preset returns is_valid=False."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin', 'default')
        os.makedirs(preset_path, exist_ok=True)
        create_preset(name='default', description='default', path=preset_path, is_builtin=True)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/validate-name?name=default', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['is_valid'] is False
    assert 'reserved by a built-in preset' in data['data']['error']


def test_validate_preset_name_invalid_chars(client, app):
    """Name with spaces/special chars returns is_valid=False."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/validate-name?name=bad%20name!', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['is_valid'] is False


def test_validate_preset_name_empty(client, app):
    """Empty name returns is_valid=False."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/validate-name?name=', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data']['is_valid'] is False


def test_validate_preset_name_duplicate(client, app, tmp_path, monkeypatch):
    """Name of an existing preset returns is_valid=False."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'taken')
        os.makedirs(preset_path, exist_ok=True)
        create_preset(name='taken', description='', path=preset_path)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/validate-name?name=taken', headers=headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['is_valid'] is False
    assert 'already exists' in data['data']['error']


def test_validate_preset_name_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/presets/validate-name?name=test')
    assert response.status_code == 401


# --- GET /api/presets/ ---

def test_list_presets_empty(client, app):
    """No presets returns empty list."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data'] == []


def test_list_presets_with_data(client, app, tmp_path, monkeypatch):
    """Returns all presets in the database."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'mypreset')
        os.makedirs(preset_path, exist_ok=True)
        create_preset(name='mypreset', description='test', path=preset_path)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert len(data) == 1
    assert data[0]['name'] == 'mypreset'


def test_list_presets_includes_is_builtin(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin', 'default')
        os.makedirs(preset_path, exist_ok=True)
        create_preset(name='default', description='default', path=preset_path, is_builtin=True)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data'][0]['is_builtin'] is True


def test_list_presets_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/presets/')
    assert response.status_code == 401


# --- POST /api/presets/ ---

def test_create_preset_success(client, app):
    """Valid data creates a preset record and folder."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'newpreset',
        'description': 'A test preset',
        'server_cfg': '[settings]\nfrag_limit=20\n'
    })
    assert response.status_code == 201
    data = response.get_json()
    assert data['data']['name'] == 'newpreset'
    assert data['data']['description'] == 'A test preset'

    with app.app_context():
        preset = ConfigPreset.query.filter_by(name='newpreset').first()
        assert preset is not None


def test_create_preset_with_generic_configs_writes_custom_file(client, app):
    """POST accepts the generic configs map and writes custom files."""
    headers = auth_headers(app, DEFAULT_USER)
    configs = {**BASE_CONFIG_MAP, 'server.cfg': 'sv_hostname test\n',
               'custom.cfg': '// custom\n'}
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'genericpreset',
        'description': '',
        'configs': configs,
    })

    assert response.status_code == 201
    data = response.get_json()['data']
    assert data['configs']['custom.cfg'] == '// custom\n'
    with open(os.path.join('configs', 'presets', 'genericpreset', 'custom.cfg')) as f:
        assert f.read() == '// custom\n'


@pytest.mark.parametrize('filename', [
    'nested/custom.cfg',
    '../custom.cfg',
    'custom.py',
])
def test_create_preset_rejects_invalid_generic_config_filename(client, app, filename):
    """Generic config map filenames must be flat .cfg/.txt files."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'badconfig',
        'description': '',
        'configs': {**BASE_CONFIG_MAP, filename: 'bad'},
    })

    assert response.status_code == 400
    assert 'Invalid config' in response.get_json()['error']['message']
    assert not os.path.exists(os.path.join('configs', 'presets', 'badconfig'))


def test_create_preset_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.post('/api/presets/', json={'name': 'x', 'description': ''})
    assert response.status_code == 401


def test_create_preset_no_body(client, app):
    """No valid JSON body returns 4xx error."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers,
                           data='not json', content_type='text/plain')
    assert response.status_code in (400, 415)


def test_create_preset_reserved_name(client, app, tmp_path, monkeypatch):
    """Built-in preset names are reserved for user-created presets."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin', 'default')
        os.makedirs(preset_path, exist_ok=True)
        create_preset(name='default', description='default', path=preset_path, is_builtin=True)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'default',
        'description': ''
    })
    assert response.status_code == 409
    assert 'reserved by a built-in preset' in response.get_json()['error']['message']


def test_create_preset_invalid_name(client, app):
    """Invalid name chars returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'bad name!',
        'description': ''
    })
    assert response.status_code == 400


def test_create_preset_duplicate_name(client, app, tmp_path, monkeypatch):
    """Duplicate name returns 409."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'dup')
        os.makedirs(preset_path, exist_ok=True)
        create_preset(name='dup', description='', path=preset_path)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'dup',
        'description': ''
    })
    assert response.status_code == 409


def test_create_preset_with_checked_plugins(client, app):
    """Preset created with checked_plugins persists and returns the list."""
    headers = auth_headers(app, DEFAULT_USER)
    plugins = ['balance.py', 'ban.py', 'my_upload.py']
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'plugged',
        'description': '',
        'checked_plugins': plugins
    })
    assert response.status_code == 201
    data = response.get_json()['data']
    assert data.get('checked_plugins') == plugins


def test_get_preset_returns_checked_plugins(client, app, tmp_path, monkeypatch):
    """GET preset returns checked_plugins saved with it."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'cptest')
        os.makedirs(preset_path, exist_ok=True)
        import json as _json
        with open(os.path.join(preset_path, 'checked_plugins.json'), 'w') as f:
            _json.dump(['balance.py', 'my_plugin.py'], f)
        preset = create_preset(name='cptest', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data'].get('checked_plugins') == ['balance.py', 'my_plugin.py']


def test_get_preset_checked_plugins_none_when_absent(client, app, tmp_path, monkeypatch):
    """GET preset returns checked_plugins=null when absent (legacy preset)."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'legacy')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='legacy', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 200
    # null signals "no saved state — keep defaults" to the frontend
    assert response.get_json()['data'].get('checked_plugins') is None


def test_create_preset_with_scripts(client, app):
    """Preset with scripts data writes script files."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'scripted',
        'description': '',
        'scripts': {'myscript.py': 'print("hello")'}
    })
    assert response.status_code == 201
    data = response.get_json()['data']
    assert 'myscript.py' in data.get('scripts', {})


def test_get_preset_scripts_merges_defaults(client, app, tmp_path):
    """Getting a preset with its own scripts also returns default preset scripts."""
    # Set up default preset scripts directory
    default_scripts_dir = os.path.join(str(tmp_path), 'configs', 'presets', 'default', 'scripts')
    os.makedirs(default_scripts_dir, exist_ok=True)
    with open(os.path.join(default_scripts_dir, 'balance.py'), 'w') as f:
        f.write('# balance plugin')

    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'custom')
        scripts_dir = os.path.join(preset_path, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        # Write only the uploaded/custom script to the preset folder
        with open(os.path.join(scripts_dir, 'my_upload.py'), 'w') as f:
            f.write('# custom upload')
        preset = create_preset(name='custom', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 200
    scripts = response.get_json()['data'].get('scripts', {})
    # Both the preset-specific upload and the default script should be present
    assert 'my_upload.py' in scripts
    assert 'balance.py' in scripts


def test_get_preset_scripts_merges_builtin_default_scripts(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    builtin_scripts_dir = os.path.join('configs', 'presets', '_builtin', 'default', 'scripts')
    os.makedirs(builtin_scripts_dir, exist_ok=True)
    with open(os.path.join(builtin_scripts_dir, 'balance.py'), 'w') as f:
        f.write('# builtin balance')

    with app.app_context():
        create_preset(
            name='default',
            description='default',
            path=os.path.join('configs', 'presets', '_builtin', 'default'),
            is_builtin=True,
        )
        preset_path = os.path.join('configs', 'presets', 'custom')
        scripts_dir = os.path.join(preset_path, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, 'custom.py'), 'w') as f:
            f.write('# custom')
        preset = create_preset(name='custom', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)

    scripts = response.get_json()['data']['scripts']
    assert scripts['balance.py'] == '# builtin balance'
    assert scripts['custom.py'] == '# custom'


def test_get_preset_includes_txt_scripts(client, app, tmp_path):
    """Getting a preset with .txt scripts returns them alongside .py scripts."""
    default_scripts_dir = os.path.join(str(tmp_path), 'configs', 'presets', 'default', 'scripts')
    os.makedirs(default_scripts_dir, exist_ok=True)

    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'txtest')
        scripts_dir = os.path.join(preset_path, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, 'plugin.py'), 'w') as f:
            f.write('# py plugin')
        with open(os.path.join(scripts_dir, 'readme.txt'), 'w') as f:
            f.write('readme content')
        preset = create_preset(name='txtest', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 200
    scripts = response.get_json()['data'].get('scripts', {})
    assert 'plugin.py' in scripts
    assert 'readme.txt' in scripts


def test_get_preset_scripts_preset_overrides_default(client, app, tmp_path):
    """Preset script with same name as a default overrides the default."""
    # Set up default preset scripts directory with a known file
    default_scripts_dir = os.path.join(str(tmp_path), 'configs', 'presets', 'default', 'scripts')
    os.makedirs(default_scripts_dir, exist_ok=True)
    with open(os.path.join(default_scripts_dir, 'balance.py'), 'w') as f:
        f.write('# default balance')

    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'override')
        scripts_dir = os.path.join(preset_path, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        # Preset has its own version of balance.py
        with open(os.path.join(scripts_dir, 'balance.py'), 'w') as f:
            f.write('# custom balance')
        preset = create_preset(name='override', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 200
    scripts = response.get_json()['data'].get('scripts', {})
    assert scripts.get('balance.py') == '# custom balance'


# --- GET /api/presets/<id> ---

def test_get_preset_success(client, app, tmp_path, monkeypatch):
    """Returns preset data including config content."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'gettest')
        os.makedirs(preset_path, exist_ok=True)
        # Write a config file
        with open(os.path.join(preset_path, 'server.cfg'), 'w') as f:
            f.write('[game]\nfrag_limit=10\n')
        preset = create_preset(name='gettest', description='test', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['name'] == 'gettest'
    assert '[game]' in data.get('server_cfg', '')


def test_get_preset_returns_generic_configs_map(client, app, tmp_path, monkeypatch):
    """GET scans all top-level .cfg/.txt files and keeps legacy keys."""
    monkeypatch.chdir(tmp_path)
    preset_id, _ = _create_preset_folder(app, 'genericget', {
        'server.cfg': 'server content\n',
        'custom.cfg': 'custom content\n',
        'notes.txt': 'notes content\n',
        'ignored.json': '{}',
    })

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['server_cfg'] == 'server content\n'
    assert data['mappool_txt'] == ''
    assert data['configs']['server.cfg'] == 'server content\n'
    assert data['configs']['mappool.txt'] == ''
    assert data['configs']['access.txt'] == ''
    assert data['configs']['workshop.txt'] == ''
    assert data['configs']['custom.cfg'] == 'custom content\n'
    assert data['configs']['notes.txt'] == 'notes content\n'
    assert 'ignored.json' not in data['configs']


def test_get_preset_not_found(client, app):
    """Non-existent preset ID returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.get('/api/presets/99999', headers=headers)
    assert response.status_code == 404


def test_get_preset_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.get('/api/presets/1')
    assert response.status_code == 401


# --- PUT /api/presets/<id> ---

def test_update_preset_description(client, app, tmp_path, monkeypatch):
    """Updates preset description."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'updatable')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='updatable', description='old desc', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'description': 'new desc'
    })
    assert response.status_code == 200
    assert response.get_json()['data']['description'] == 'new desc'


def test_update_preset_checked_plugins(client, app, tmp_path, monkeypatch):
    """PUT preset with checked_plugins persists and returns updated list."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'upd_cp')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='upd_cp', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    plugins = ['balance.py', 'extra.py']
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'checked_plugins': plugins
    })
    assert response.status_code == 200
    assert response.get_json()['data'].get('checked_plugins') == plugins

    # Verify it round-trips on GET too
    response = client.get(f'/api/presets/{preset_id}', headers=headers)
    assert response.get_json()['data'].get('checked_plugins') == plugins


def test_update_preset_syncs_deleted_generic_config_file(client, app, tmp_path, monkeypatch):
    """PUT with generic configs removes unprotected .cfg/.txt files omitted from the map."""
    monkeypatch.chdir(tmp_path)
    preset_id, preset_path = _create_preset_folder(app, 'syncconfigs', {
        **BASE_CONFIG_MAP,
        'old_custom.cfg': 'old',
    })

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'configs': BASE_CONFIG_MAP,
    })

    assert response.status_code == 200
    assert not os.path.exists(os.path.join(preset_path, 'old_custom.cfg'))
    assert os.path.exists(os.path.join(preset_path, 'server.cfg'))


def test_update_preset_blocks_missing_protected_config(client, app, tmp_path, monkeypatch):
    """Generic configs map cannot omit protected built-in files."""
    monkeypatch.chdir(tmp_path)
    preset_id, preset_path = _create_preset_folder(app, 'missingprotected', BASE_CONFIG_MAP)
    configs = BASE_CONFIG_MAP.copy()
    configs.pop('server.cfg')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'configs': configs,
    })

    assert response.status_code == 400
    assert 'server.cfg' in response.get_json()['error']['message']
    assert os.path.exists(os.path.join(preset_path, 'server.cfg'))


def test_update_preset_rejects_null_configs(client, app, tmp_path, monkeypatch):
    """Present configs value must be the generic filename-to-content map."""
    monkeypatch.chdir(tmp_path)
    preset_id, _ = _create_preset_folder(app, 'nullconfigs', BASE_CONFIG_MAP)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'configs': None,
    })

    assert response.status_code == 400
    assert "'configs' must be a dict" in response.get_json()['error']['message']


def test_update_preset_syncs_deleted_factory_file(client, app, tmp_path, monkeypatch):
    """PUT factories map removes .factories files omitted from the map."""
    monkeypatch.chdir(tmp_path)
    preset_id, preset_path = _create_preset_folder(
        app, 'syncfactories', BASE_CONFIG_MAP,
        factories={'old.factories': 'old', 'keep.factories': 'keep'},
    )

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'factories': {'keep.factories': 'new'},
    })

    factories_dir = os.path.join(preset_path, 'factories')
    assert response.status_code == 200
    assert not os.path.exists(os.path.join(factories_dir, 'old.factories'))
    with open(os.path.join(factories_dir, 'keep.factories')) as f:
        assert f.read() == 'new'


def test_get_preset_ignores_nested_factory_files(client, app, tmp_path, monkeypatch):
    """Factories are a flat file-manager context; nested files are not returned."""
    monkeypatch.chdir(tmp_path)
    preset_id, preset_path = _create_preset_folder(
        app, 'nestedfactory', BASE_CONFIG_MAP,
        factories={'top.factories': 'top'},
    )
    nested_dir = os.path.join(preset_path, 'factories', 'nested')
    os.makedirs(nested_dir)
    with open(os.path.join(nested_dir, 'hidden.factories'), 'w') as f:
        f.write('hidden')

    headers = auth_headers(app, DEFAULT_USER)
    response = client.get(f'/api/presets/{preset_id}', headers=headers)

    assert response.status_code == 200
    factories = response.get_json()['data']['factories']
    assert factories == {'top.factories': 'top'}


@pytest.mark.parametrize('filename', [
    'bad.txt',
    '../bad.factories',
    'nested/bad.factories',
])
def test_update_preset_rejects_invalid_factory_filename(
    client, app, tmp_path, monkeypatch, filename
):
    """Factory writes validate flat .factories filenames."""
    monkeypatch.chdir(tmp_path)
    preset_id, _ = _create_preset_folder(app, 'badfactory', BASE_CONFIG_MAP)

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'factories': {filename: '{}'},
    })

    assert response.status_code == 400
    assert 'Invalid factory' in response.get_json()['error']['message']


def test_rename_user_preset_to_builtin_name_rejected(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        builtin_path = os.path.join('configs', 'presets', '_builtin', 'duel')
        user_path = os.path.join('configs', 'presets', 'custom')
        os.makedirs(builtin_path, exist_ok=True)
        os.makedirs(user_path, exist_ok=True)
        create_preset(name='duel', description='Duel', path=builtin_path, is_builtin=True)
        user = create_preset(name='custom', description='', path=user_path)
        user_id = user.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{user_id}', headers=headers, json={'name': 'duel'})

    assert response.status_code == 409
    assert 'reserved by a built-in preset' in response.get_json()['error']['message']


def test_rename_builtin_preset_prevented(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin', 'default')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='default', description='default', path=preset_path, is_builtin=True)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={'name': 'renamed'})

    assert response.status_code == 403
    assert 'Cannot rename a built-in preset' in response.get_json()['error']['message']


def test_update_builtin_preset_content_allowed(client, app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin', 'default')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='default', description='default', path=preset_path, is_builtin=True)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'server_cfg': 'set sv_hostname "Updated"\n'
    })

    assert response.status_code == 200
    assert 'Updated' in response.get_json()['data']['server_cfg']


def test_create_preset_checked_plugins_invalid_type(client, app):
    """checked_plugins that is not a list returns 400."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.post('/api/presets/', headers=headers, json={
        'name': 'badcp',
        'description': '',
        'checked_plugins': 'balance.py,ban.py'  # string instead of list
    })
    assert response.status_code == 400
    assert 'checked_plugins must be a list of strings' in response.get_json()['error']['message']


def test_create_preset_checked_plugins_rejects_non_string_entries(client, app):
    """checked_plugins entries must be strings."""
    payload = {
        'name': 'badplugins2',
        'description': '',
        'configs': BASE_CONFIG_MAP,
        'checked_plugins': ['balance.py', 123],
    }
    response = client.post(
        '/api/presets/',
        json=payload,
        headers=auth_headers(app, DEFAULT_USER),
    )
    assert response.status_code == 400
    assert 'checked_plugins must be a list of strings' in response.get_json()['error']['message']


def test_update_preset_checked_plugins_invalid_type(client, app, tmp_path, monkeypatch):
    """PUT with non-list checked_plugins returns 400."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'badupd')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='badupd', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers, json={
        'checked_plugins': {'balance': True}  # dict instead of list
    })
    assert response.status_code == 400
    assert 'checked_plugins must be a list of strings' in response.get_json()['error']['message']


def test_update_preset_checked_plugins_rejects_non_string_entries(client, app, tmp_path, monkeypatch):
    """PUT checked_plugins entries must be strings."""
    preset_id, _ = _create_preset_folder(app, 'checktype', BASE_CONFIG_MAP)

    response = client.put(f'/api/presets/{preset_id}', json={
        'checked_plugins': ['balance.py', 123],
    }, headers=auth_headers(app, DEFAULT_USER))

    assert response.status_code == 400
    assert 'checked_plugins must be a list of strings' in response.get_json()['error']['message']


def test_update_preset_not_found(client, app):
    """Non-existent preset ID returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.put('/api/presets/99999', headers=headers, json={
        'description': 'something'
    })
    assert response.status_code == 404


def test_update_preset_no_body(client, app, tmp_path, monkeypatch):
    """No valid JSON body returns 4xx error."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'upd2')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='upd2', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.put(f'/api/presets/{preset_id}', headers=headers,
                          data='not json', content_type='text/plain')
    assert response.status_code in (400, 415)


def test_update_preset_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.put('/api/presets/1', json={'description': 'x'})
    assert response.status_code == 401


# --- DELETE /api/presets/<id> ---

def test_delete_preset_success(client, app, tmp_path, monkeypatch):
    """Deletes preset from DB and removes folder."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'deleteme')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='deleteme', description='', path=preset_path)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 200

    with app.app_context():
        assert db.session.get(ConfigPreset, preset_id) is None


def test_delete_preset_not_found(client, app):
    """Non-existent preset ID returns 404."""
    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete('/api/presets/99999', headers=headers)
    assert response.status_code == 404


def test_delete_preset_unauthenticated(client, app):
    """Unauthenticated request returns 401."""
    response = client.delete('/api/presets/1')
    assert response.status_code == 401


def test_delete_default_preset_prevented(client, app, tmp_path, monkeypatch):
    """Deleting a built-in preset returns 403."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', '_builtin', 'default')
        os.makedirs(preset_path, exist_ok=True)
        preset = create_preset(name='default', description='default', path=preset_path, is_builtin=True)
        preset_id = preset.id

    headers = auth_headers(app, DEFAULT_USER)
    response = client.delete(f'/api/presets/{preset_id}', headers=headers)
    assert response.status_code == 403
    assert 'Cannot delete a built-in preset' in response.get_json()['error']['message']
