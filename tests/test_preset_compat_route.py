"""The route contract: absent or matching target_runtime changes nothing."""
import json
import os

import pytest

from tests.helpers import make_user, auth_headers
from ui.database import create_preset

DEFAULT_USER = 'compatadmin'
DEFAULT_PASS = 'compatpass1'


@pytest.fixture(autouse=True)
def setup_user(app):
    make_user(app, DEFAULT_USER, DEFAULT_PASS)


@pytest.fixture(autouse=True)
def redirect_preset_writes(tmp_path, monkeypatch):
    """Same autouse chdir tests/test_preset_routes.py uses -- preset writes must
    land in a temp directory, not in the developer's working tree."""
    monkeypatch.chdir(tmp_path)


def _make_preset(app, runtime='minqlx'):
    """A preset on disk with one plugin that cannot run on minqlxtended."""
    with app.app_context():
        preset_path = os.path.join('configs', 'presets', 'compat_probe')
        os.makedirs(os.path.join(preset_path, 'scripts'), exist_ok=True)
        with open(os.path.join(preset_path, 'scripts', 'legacy.py'), 'w') as handle:
            handle.write('import minqlx\n\nclass legacy(minqlx.Plugin):\n    pass\n')
        with open(os.path.join(preset_path, 'checked_plugins.json'), 'w') as handle:
            json.dump(['legacy.py'], handle)
        preset = create_preset(name='compat_probe', description='', path=preset_path,
                               runtime=runtime)
        return preset.id


def test_no_target_runtime_returns_no_compatibility_key(client, app):
    preset_id = _make_preset(app)
    response = client.get(f'/api/presets/{preset_id}', headers=auth_headers(app, DEFAULT_USER))
    assert response.status_code == 200
    assert 'compatibility' not in response.get_json()['data']


def test_a_matching_target_runtime_returns_no_compatibility_key(client, app):
    preset_id = _make_preset(app)
    response = client.get(f'/api/presets/{preset_id}?target_runtime=minqlx',
                          headers=auth_headers(app, DEFAULT_USER))
    assert 'compatibility' not in response.get_json()['data']


def test_a_matching_target_runtime_returns_the_same_body_as_no_parameter(client, app):
    """The gate must be invisible to every existing caller."""
    preset_id = _make_preset(app)
    headers = auth_headers(app, DEFAULT_USER)
    plain = client.get(f'/api/presets/{preset_id}', headers=headers).get_json()
    matched = client.get(f'/api/presets/{preset_id}?target_runtime=minqlx', headers=headers).get_json()
    assert plain == matched


def test_a_mismatched_target_runtime_strips_and_reports(client, app):
    preset_id = _make_preset(app)
    response = client.get(f'/api/presets/{preset_id}?target_runtime=minqlxtended',
                          headers=auth_headers(app, DEFAULT_USER))
    data = response.get_json()['data']
    assert data['compatibility']['target_runtime'] == 'minqlxtended'
    assert data['compatibility']['preset_runtime'] == 'minqlx'
    assert [e['path'] for e in data['compatibility']['stripped']] == ['legacy.py']
    assert 'legacy.py' not in data['scripts']
    assert data['checked_plugins'] == []


def test_an_unknown_target_runtime_is_rejected(client, app):
    """Silently defaulting an unknown value would strip against the wrong
    baseline and look like the gate malfunctioning."""
    preset_id = _make_preset(app)
    response = client.get(f'/api/presets/{preset_id}?target_runtime=nonsense',
                          headers=auth_headers(app, DEFAULT_USER))
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_the_route_still_401s_without_a_token(client, app):
    preset_id = _make_preset(app)
    assert client.get(f'/api/presets/{preset_id}').status_code == 401
