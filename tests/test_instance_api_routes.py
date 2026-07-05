import os
import uuid

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from flask_jwt_extended import create_access_token
from ui.models import QLInstance, Host, HostStatus, InstanceStatus, ConfigPreset
from ui import db
from ui.database import create_instance, create_host


@pytest.fixture
def auth_token(app):
    with app.app_context():
        return create_access_token(identity='testuser')


@pytest.fixture
def sample_host(app):
    with app.app_context():
        host = create_host(name='sample-host', provider='vultr', status=HostStatus.ACTIVE)
        return SimpleNamespace(id=host.id, name=host.name)


@pytest.fixture
def sample_instance(app, sample_host):
    with app.app_context():
        instance = create_instance(
            name='sample-instance',
            host_id=sample_host.id,
            port=27960,
            hostname='sample.hostname',
        )
        return SimpleNamespace(id=instance.id, name=instance.name), sample_host


def _auth_header(token):
    return {'Authorization': f'Bearer {token}'}


def _full_configs(**overrides):
    configs = {'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': ''}
    configs.update(overrides)
    return configs


def test_update_instance_hostname(client, app):
    """
    GIVEN an existing instance
    WHEN PUT /api/instances/<id> is called with a new hostname
    THEN the instance hostname is updated in the database
    """
    # Create test data
    with app.app_context():
        host = create_host(name='api-test-host', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(name='api-test-inst', host_id=host.id, port=27960, hostname='old.hostname.com')
        db.session.commit()
        instance_id = instance.id

        # Generate Token
        token = create_access_token(identity='testuser')

    # Make Request
    headers = {'Authorization': f'Bearer {token}'}
    data = {'hostname': 'new.hostname.com'}
    
    # Note: URL is /api/instances/<id> because of blueprint registration
    response = client.put(f'/api/instances/{instance_id}', json=data, headers=headers)

    # Debug failure if any
    if response.status_code != 200:
        print(f"Response Body: {response.data}")

    assert response.status_code == 200
    assert response.json['message'] == 'Instance details updated successfully.'
    assert response.json['data']['hostname'] == 'new.hostname.com'

    # Verify DB
    with app.app_context():
        updated = db.session.get(QLInstance, instance_id)
        assert updated.hostname == 'new.hostname.com'

def test_update_instance_name_and_hostname(client, app):
    """
    GIVEN an existing instance
    WHEN PUT /api/instances/<id> is called with a new name AND hostname
    THEN both are updated
    """
    # Create test data
    with app.app_context():
        host = create_host(name='api-test-host-2', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(name='api-test-inst-2', host_id=host.id, port=27961, hostname='old.hostname.com')
        db.session.commit()
        instance_id = instance.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {'name': 'renamed-inst', 'hostname': 'renamed.hostname.com'}

    response = client.put(f'/api/instances/{instance_id}', json=data, headers=headers)

    assert response.status_code == 200
    assert response.json['data']['name'] == 'renamed-inst'
    assert response.json['data']['hostname'] == 'renamed.hostname.com'

    with app.app_context():
        updated = db.session.get(QLInstance, instance_id)
        assert updated.name == 'renamed-inst'
        assert updated.hostname == 'renamed.hostname.com'


def test_view_instance_includes_host_os_type(client, app):
    """GET /api/instances/<id> should include host_os_type in the payload."""
    with app.app_context():
        host = create_host(
            name='ubuntu-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            os_type='ubuntu',
        )
        instance = create_instance(
            name='inst-os',
            host_id=host.id,
            port=27960,
            hostname='test.hostname',
        )
        db.session.commit()
        instance_id = instance.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    response = client.get(f'/api/instances/{instance_id}', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data']['host_os_type'] == 'ubuntu'


def test_read_default_config_uses_builtin_default_path(app, tmp_path, monkeypatch):
    from ui.routes.instance_routes import _read_default_config

    monkeypatch.chdir(tmp_path)
    builtin_default = tmp_path / 'configs' / 'presets' / '_builtin' / 'default'
    builtin_default.mkdir(parents=True)
    (builtin_default / 'server.cfg').write_text('set sv_hostname "Builtin"\n')

    with app.app_context():
        db.session.add(ConfigPreset(
            name='default',
            description='Default',
            path='configs/presets/_builtin/default',
            is_builtin=True,
        ))
        db.session.commit()

        assert _read_default_config('server.cfg') == 'set sv_hostname "Builtin"\n'


@patch('ui.routes.instance_routes.enqueue_task')
def test_add_instance_rejects_when_host_has_4_instances(mock_enqueue, client, app, tmp_path, monkeypatch):
    """POST /api/instances must return 400 when the host already has 4 instances."""
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        host = create_host(name='full-host', provider='vultr', status=HostStatus.ACTIVE)
        for port in [27960, 27961, 27962, 27963]:
            create_instance(name=f'inst-{port}', host_id=host.id, port=port, hostname='test.host')
        db.session.commit()
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'name': 'fifth-instance',
        'host_id': host_id,
        'port': 27964,
        'hostname': 'test.host',
        'configs': {'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': ''},
    }

    response = client.post('/api/instances/', json=payload, headers=headers)

    assert response.status_code == 400
    assert 'maximum of 4 instances' in response.get_json()['error']['message']
    mock_enqueue.assert_not_called()


@patch('ui.routes.instance_routes.enqueue_task')
def test_add_instance_rejects_invalid_checked_plugins_before_creating_side_effects(
    mock_enqueue, client, app, tmp_path, monkeypatch
):
    """POST /api/instances must fail before creating rows/files when checked_plugins is invalid."""
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        host = create_host(name='api-create-host', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'name': 'new-instance',
        'host_id': host_id,
        'port': 27970,
        'hostname': 'test.hostname',
        'configs': {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
        },
        'checked_plugins': ['my-plugin'],
    }

    response = client.post('/api/instances/', json=payload, headers=headers)

    assert response.status_code == 400
    assert 'qlx_plugins contains invalid characters' in response.get_json()['error']['message']
    mock_enqueue.assert_not_called()

    with app.app_context():
        assert QLInstance.query.count() == 0

    assert not (tmp_path / 'configs' / 'api-create-host').exists()


@patch('ui.routes.instance_routes.enqueue_task')
def test_add_instance_rejects_non_string_checked_plugins(
    mock_enqueue, client, app, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        host = create_host(name='api-create-host', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'name': 'new-instance',
        'host_id': host_id,
        'port': 27970,
        'hostname': 'test.hostname',
        'configs': {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
        },
        'checked_plugins': ['balance', 123],
    }

    response = client.post('/api/instances/', json=payload, headers=headers)

    assert response.status_code == 400
    assert 'checked_plugins must be a list of strings' in response.get_json()['error']['message']
    mock_enqueue.assert_not_called()

    with app.app_context():
        assert QLInstance.query.count() == 0


def test_create_instance_hostname_too_long(client, app):
    """
    GIVEN a POST request to create an instance
    WHEN hostname exceeds 64 characters
    THEN a 400 error is returned
    """
    with app.app_context():
        host = create_host(name='host-len-test', provider='vultr', status=HostStatus.ACTIVE)
        db.session.commit()
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {
        'name': 'len-test-inst',
        'host_id': host_id,
        'port': 27970,
        'hostname': 'A' * 65,
    }
    response = client.post('/api/instances/', json=data, headers=headers)

    assert response.status_code == 400
    assert 'Server Hostname must be 64 characters or fewer' in response.json['error']['message']

def test_update_instance_hostname_too_long(client, app):
    """
    GIVEN an existing instance
    WHEN PUT /api/instances/<id> is called with a hostname exceeding 64 characters
    THEN a 400 error is returned
    """
    with app.app_context():
        host = create_host(name='host-len-update', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(name='len-update-inst', host_id=host.id, port=27971, hostname='short.host')
        db.session.commit()
        instance_id = instance.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {'hostname': 'B' * 65}
    response = client.put(f'/api/instances/{instance_id}', json=data, headers=headers)

    assert response.status_code == 400
    assert 'Server Hostname must be 64 characters or fewer' in response.json['error']['message']


@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
@patch('ui.routes.instance_routes.enqueue_task')
def test_create_instance_hostname_exactly_64_chars(mock_enqueue, mock_lock, client, app, tmp_path, monkeypatch):
    """
    GIVEN a POST request to create an instance
    WHEN hostname is exactly 64 characters
    THEN the instance is created successfully
    """
    monkeypatch.chdir(tmp_path)

    with app.app_context():
        host = create_host(name='host-boundary-test', provider='vultr', status=HostStatus.ACTIVE)
        db.session.commit()
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {
        'name': 'boundary-inst',
        'host_id': host_id,
        'port': 27972,
        'hostname': 'A' * 64,
    }
    mock_enqueue.return_value = type('Job', (), {'id': 'fake-job-id'})()
    response = client.post('/api/instances/', json=data, headers=headers)

    assert response.status_code == 201


@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
@patch('ui.routes.instance_routes.enqueue_task')
def test_create_instance_from_draft_copies_user_hooks(mock_enqueue, mock_lock, client, app, tmp_path, monkeypatch):
    """
    GIVEN a draft seeded from a preset with a user-hooks/ file (e.g. imported via
          preset ZIP import, then loaded when creating a new instance)
    WHEN POST /api/instances/ is called with that draft_id
    THEN the draft's user-hooks/ directory is copied to the new instance, not discarded
    """
    monkeypatch.chdir(tmp_path)

    draft_id = str(uuid.uuid4())
    draft_dir = os.path.join(app.config['DRAFTS_BASE'], draft_id)
    os.makedirs(os.path.join(draft_dir, 'scripts'), exist_ok=True)
    hooks_dir = os.path.join(draft_dir, 'user-hooks')
    os.makedirs(hooks_dir, exist_ok=True)
    with open(os.path.join(hooks_dir, 'my_hook.so'), 'wb') as f:
        f.write(b'\x7fELF' + b'\x00' * 16)

    with app.app_context():
        host = create_host(name='host-draft-hooks', provider='vultr', status=HostStatus.ACTIVE)
        db.session.commit()
        host_id = host.id
        host_name = host.name
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {
        'name': 'draft-hooks-inst',
        'host_id': host_id,
        'port': 27974,
        'hostname': 'draft.hooks.host',
        'draft_id': draft_id,
    }
    mock_enqueue.return_value = type('Job', (), {'id': 'fake-job-id'})()
    response = client.post('/api/instances/', json=data, headers=headers)

    assert response.status_code == 201, response.get_json()
    instance_id = response.get_json()['data']['id']
    instance_hooks_dir = tmp_path / 'configs' / host_name / str(instance_id) / 'user-hooks'
    assert (instance_hooks_dir / 'my_hook.so').exists(), (
        "user-hooks/ from the draft (seeded from a preset) must be copied to the new instance"
    )


@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
@patch('ui.routes.instance_routes.enqueue_task')
def test_create_instance_applies_enabled_hooks_filtered_to_existing_files(
    mock_enqueue, mock_lock, client, app, tmp_path, monkeypatch
):
    """
    GIVEN a draft with two hook files, and enabled_hooks naming one real hook
          plus one hook that doesn't actually exist in the draft
    WHEN POST /api/instances/ is called with draft_id + enabled_hooks
    THEN ld_preload_hooks is set to only the hook(s) that actually landed on disk
    """
    monkeypatch.chdir(tmp_path)

    draft_id = str(uuid.uuid4())
    draft_dir = os.path.join(app.config['DRAFTS_BASE'], draft_id)
    os.makedirs(os.path.join(draft_dir, 'scripts'), exist_ok=True)
    hooks_dir = os.path.join(draft_dir, 'user-hooks')
    os.makedirs(hooks_dir, exist_ok=True)
    with open(os.path.join(hooks_dir, 'real_hook.so'), 'wb') as f:
        f.write(b'\x7fELF' + b'\x00' * 16)

    with app.app_context():
        host = create_host(name='host-enabled-hooks', provider='vultr', status=HostStatus.ACTIVE)
        db.session.commit()
        host_id = host.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {
        'name': 'enabled-hooks-inst',
        'host_id': host_id,
        'port': 27975,
        'hostname': 'enabled.hooks.host',
        'draft_id': draft_id,
        'enabled_hooks': ['real_hook.so', 'ghost_hook.so'],
    }
    mock_enqueue.return_value = type('Job', (), {'id': 'fake-job-id'})()
    response = client.post('/api/instances/', json=data, headers=headers)

    assert response.status_code == 201, response.get_json()
    instance_id = response.get_json()['data']['id']
    with app.app_context():
        instance = db.session.get(QLInstance, instance_id)
        assert instance.ld_preload_hooks == 'real_hook.so'


def test_update_instance_hostname_exactly_64_chars(client, app):
    """
    GIVEN an existing instance
    WHEN PUT /api/instances/<id> is called with a hostname of exactly 64 characters
    THEN the update is accepted
    """
    with app.app_context():
        host = create_host(name='host-boundary-update', provider='vultr', status=HostStatus.ACTIVE)
        instance = create_instance(name='boundary-update-inst', host_id=host.id, port=27973, hostname='short.host')
        db.session.commit()
        instance_id = instance.id
        token = create_access_token(identity='testuser')

    headers = {'Authorization': f'Bearer {token}'}
    data = {'hostname': 'B' * 64}
    response = client.put(f'/api/instances/{instance_id}', json=data, headers=headers)

    assert response.status_code == 200
    assert response.json['data']['hostname'] == 'B' * 64


def test_update_config_accepts_custom_cfg_and_syncs_removed_files(
    client, auth_token, sample_instance, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance
    instance_dir = tmp_path / 'configs' / host.name / str(instance.id)
    instance_dir.mkdir(parents=True)
    (instance_dir / 'old_custom.cfg').write_text('old')

    payload = {
        'configs': _full_configs(**{'custom.cfg': '// custom\n'}),
        'restart': False,
    }

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')):
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json=payload,
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 202, response.get_json()
    assert (instance_dir / 'custom.cfg').read_text() == '// custom\n'
    assert not (instance_dir / 'old_custom.cfg').exists()


def test_update_config_from_draft_copies_user_hooks(
    client, app, auth_token, sample_instance, tmp_path, monkeypatch
):
    """
    GIVEN a draft seeded from a preset with a user-hooks/ file (loaded into the
          "Load Preset" flow when editing an existing instance)
    WHEN PUT /api/instances/<id>/config is called with that draft_id
    THEN the draft's user-hooks/ directory is copied to the instance, not discarded
    """
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance

    draft_id = str(uuid.uuid4())
    draft_dir = os.path.join(app.config['DRAFTS_BASE'], draft_id)
    os.makedirs(os.path.join(draft_dir, 'scripts'), exist_ok=True)
    hooks_dir = os.path.join(draft_dir, 'user-hooks')
    os.makedirs(hooks_dir, exist_ok=True)
    with open(os.path.join(hooks_dir, 'my_hook.so'), 'wb') as f:
        f.write(b'\x7fELF' + b'\x00' * 16)

    payload = {
        'configs': _full_configs(),
        'draft_id': draft_id,
        'restart': False,
    }

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')):
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json=payload,
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 202, response.get_json()
    instance_hooks_dir = tmp_path / 'configs' / host.name / str(instance.id) / 'user-hooks'
    assert (instance_hooks_dir / 'my_hook.so').exists(), (
        "user-hooks/ from the draft (seeded from a preset) must be copied to the instance"
    )


def test_update_config_enabled_hooks_replaces_existing_selection(
    client, app, auth_token, sample_instance, tmp_path, monkeypatch
):
    """
    GIVEN an instance that already has a hook enabled, and a loaded preset whose
          enabled_hooks names a different (also real) hook
    WHEN PUT /api/instances/<id>/config is called with draft_id + enabled_hooks
    THEN ld_preload_hooks is fully replaced to match the preset's enabled_hooks
         (mirrors how checked_plugins/checked_factories replace on preset load)
    """
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance

    with app.app_context():
        db_instance = db.session.get(QLInstance, instance.id)
        db_instance.ld_preload_hooks = 'old_hook.so'
        db.session.commit()

    draft_id = str(uuid.uuid4())
    draft_dir = os.path.join(app.config['DRAFTS_BASE'], draft_id)
    os.makedirs(os.path.join(draft_dir, 'scripts'), exist_ok=True)
    hooks_dir = os.path.join(draft_dir, 'user-hooks')
    os.makedirs(hooks_dir, exist_ok=True)
    with open(os.path.join(hooks_dir, 'preset_hook.so'), 'wb') as f:
        f.write(b'\x7fELF' + b'\x00' * 16)

    payload = {
        'configs': _full_configs(),
        'draft_id': draft_id,
        'enabled_hooks': ['preset_hook.so', 'ghost_hook.so'],
        'restart': False,
    }

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')):
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json=payload,
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 202, response.get_json()
    with app.app_context():
        updated = db.session.get(QLInstance, instance.id)
        assert updated.ld_preload_hooks == 'preset_hook.so'


def test_update_config_enabled_hooks_without_draft_filters_to_existing_files(
    client, app, auth_token, sample_instance, tmp_path, monkeypatch
):
    """
    GIVEN an instance with a hook file already on disk, and no draft_id in the
          request (e.g. a client resubmitting enabled_hooks on its own)
    WHEN PUT /api/instances/<id>/config is called with enabled_hooks but no draft_id
    THEN ld_preload_hooks is filtered against the instance's existing user-hooks/
         directory — names not already on disk are dropped, not treated as an error
    """
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance

    instance_hooks_dir = tmp_path / 'configs' / host.name / str(instance.id) / 'user-hooks'
    instance_hooks_dir.mkdir(parents=True)
    (instance_hooks_dir / 'existing_hook.so').write_bytes(b'\x7fELF' + b'\x00' * 16)

    payload = {
        'configs': _full_configs(),
        'enabled_hooks': ['existing_hook.so', 'ghost_hook.so'],
        'restart': False,
    }

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')):
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json=payload,
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 202, response.get_json()
    with app.app_context():
        updated = db.session.get(QLInstance, instance.id)
        assert updated.ld_preload_hooks == 'existing_hook.so'


def test_update_config_creates_user_hooks_source_dir_when_absent(
    client, app, auth_token, sample_instance, tmp_path, monkeypatch
):
    """
    GIVEN an instance whose local configs/<host>/<id>/user-hooks/ dir does not
          exist (e.g. deployed before the hook feature)
    WHEN PUT /api/instances/<id>/config is called with enabled_hooks
    THEN the request succeeds AND the user-hooks/ source dir is created, so the
         general-save rsync source is never missing (spec §5.4).
    """
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance

    hooks_dir = tmp_path / 'configs' / host.name / str(instance.id) / 'user-hooks'
    assert not hooks_dir.exists()

    payload = {'configs': _full_configs(), 'enabled_hooks': [], 'restart': False}

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-1')):
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json=payload,
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 202, response.get_json()
    assert hooks_dir.is_dir()


@pytest.mark.parametrize(
    ('configs', 'message'),
    [
        (_full_configs(**{'evil.exe': 'bad'}), 'Disallowed extension'),
        (_full_configs(**{'../evil.cfg': 'bad'}), 'Invalid name'),
        ({'mappool.txt': '', 'access.txt': '', 'workshop.txt': ''}, 'server.cfg'),
    ],
)
def test_update_config_rejects_invalid_configs(
    client, auth_token, sample_instance, configs, message
):
    instance, _host = sample_instance
    response = client.put(
        f'/api/instances/{instance.id}/config',
        json={'configs': configs, 'restart': False},
        headers=_auth_header(auth_token),
    )

    assert response.status_code == 400
    assert message in response.get_json()['error']['message']


def test_update_config_rejects_non_string_file_content(client, auth_token, sample_instance):
    instance, _host = sample_instance
    config_response = client.put(
        f'/api/instances/{instance.id}/config',
        json={
            'configs': _full_configs(**{'custom.cfg': {'not': 'text'}}),
            'restart': False,
        },
        headers=_auth_header(auth_token),
    )
    assert config_response.status_code == 400
    assert 'must be a string' in config_response.get_json()['error']['message']

    factory_response = client.put(
        f'/api/instances/{instance.id}/config',
        json={
            'configs': _full_configs(),
            'factories': {'duel.factories': ['not text']},
            'restart': False,
        },
        headers=_auth_header(auth_token),
    )
    assert factory_response.status_code == 400
    assert 'must be a string' in factory_response.get_json()['error']['message']


def test_update_config_validates_factories_and_preserves_sync(
    client, auth_token, sample_instance, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance
    factories_dir = tmp_path / 'configs' / host.name / str(instance.id) / 'factories'
    factories_dir.mkdir(parents=True)
    (factories_dir / 'old.factories').write_text('old')

    bad_response = client.put(
        f'/api/instances/{instance.id}/config',
        json={'configs': _full_configs(), 'factories': {'evil.txt': 'bad'}},
        headers=_auth_header(auth_token),
    )
    assert bad_response.status_code == 400

    bad_path_response = client.put(
        f'/api/instances/{instance.id}/config',
        json={'configs': _full_configs(), 'factories': {'nested/bad.factories': 'bad'}},
        headers=_auth_header(auth_token),
    )
    assert bad_path_response.status_code == 400

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-2')):
        good_response = client.put(
            f'/api/instances/{instance.id}/config',
            json={
                'configs': _full_configs(),
                'factories': {'new.factories': 'new'},
                'restart': False,
            },
            headers=_auth_header(auth_token),
        )

    assert good_response.status_code == 202, good_response.get_json()
    assert (factories_dir / 'new.factories').read_text() == 'new'
    assert not (factories_dir / 'old.factories').exists()


def test_update_config_omitting_factories_preserves_existing(
    client, auth_token, sample_instance, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance
    factories_dir = tmp_path / 'configs' / host.name / str(instance.id) / 'factories'
    factories_dir.mkdir(parents=True)
    existing = factories_dir / 'existing.factories'
    existing.write_text('keep')

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-preserve')):
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json={'configs': _full_configs(), 'restart': False},
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 202, response.get_json()
    assert existing.read_text() == 'keep'


def test_update_config_updates_name_and_hostname(client, auth_token, sample_instance):
    instance, _host = sample_instance
    payload = {
        'name': 'Renamed Instance',
        'hostname': 'New Hostname',
        'configs': _full_configs(),
        'restart': False,
    }

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-3')):
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json=payload,
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 202, response.get_json()

    response = client.get(
        f'/api/instances/{instance.id}',
        headers=_auth_header(auth_token),
    )
    body = response.get_json()['data']
    assert body['name'] == 'Renamed Instance'
    assert body['hostname'] == 'New Hostname'


def test_update_config_rejects_non_string_name_and_hostname(
    client, auth_token, sample_instance
):
    instance, _host = sample_instance
    name_response = client.put(
        f'/api/instances/{instance.id}/config',
        json={'name': 123, 'configs': _full_configs(), 'restart': False},
        headers=_auth_header(auth_token),
    )
    assert name_response.status_code == 400
    assert 'Name must be a string' in name_response.get_json()['error']['message']

    hostname_response = client.put(
        f'/api/instances/{instance.id}/config',
        json={'hostname': ['bad'], 'configs': _full_configs(), 'restart': False},
        headers=_auth_header(auth_token),
    )
    assert hostname_response.status_code == 400
    assert 'Hostname must be a string' in hostname_response.get_json()['error']['message']


def test_update_config_validates_before_metadata_update(
    client, auth_token, sample_instance
):
    instance, _host = sample_instance
    response = client.put(
        f'/api/instances/{instance.id}/config',
        json={
            'name': 'Should Not Persist',
            'hostname': 'Should Not Persist',
            'configs': {'server.cfg': ''},
            'restart': False,
        },
        headers=_auth_header(auth_token),
    )

    assert response.status_code == 400
    with client.application.app_context():
        updated = db.session.get(QLInstance, instance.id)
        assert updated.name == 'sample-instance'
        assert updated.hostname == 'sample.hostname'


def test_update_config_rejects_duplicate_name(client, auth_token, sample_instance):
    instance, host = sample_instance
    with client.application.app_context():
        create_instance(
            name='taken-name',
            host_id=host.id,
            port=27961,
            hostname='taken.hostname',
        )

    response = client.put(
        f'/api/instances/{instance.id}/config',
        json={'name': 'taken-name', 'configs': _full_configs(), 'restart': False},
        headers=_auth_header(auth_token),
    )

    assert response.status_code == 409
    assert 'already exists' in response.get_json()['error']['message']


def test_update_config_integrity_failure_does_not_write_files(
    client, auth_token, sample_instance, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance
    instance_dir = tmp_path / 'configs' / host.name / str(instance.id)
    instance_dir.mkdir(parents=True)
    server_cfg = instance_dir / 'server.cfg'
    server_cfg.write_text('original')

    with client.application.app_context():
        other_host = create_host(name='other-host', provider='vultr', status=HostStatus.ACTIVE)
        create_instance(
            name='globally-taken',
            host_id=other_host.id,
            port=27961,
            hostname='taken.hostname',
        )

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.release_lock'), \
         patch('ui.routes.instance_routes.enqueue_task') as mock_enqueue:
        response = client.put(
            f'/api/instances/{instance.id}/config',
            json={
                'name': 'globally-taken',
                'configs': _full_configs(**{'server.cfg': 'changed'}),
                'restart': False,
            },
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 409
    assert server_cfg.read_text() == 'original'
    mock_enqueue.assert_not_called()


def test_get_config_returns_custom_files_and_falls_back_for_protected(
    client, auth_token, sample_instance, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    instance, host = sample_instance
    instance_dir = tmp_path / 'configs' / host.name / str(instance.id)
    instance_dir.mkdir(parents=True)
    (instance_dir / 'server.cfg').write_text('// server')
    (instance_dir / 'custom.cfg').write_text('// custom')
    (instance_dir / 'notes.txt').write_text('notes')
    (instance_dir / 'ignored.factories').write_text('ignored')

    response = client.get(
        f'/api/instances/{instance.id}/config',
        headers=_auth_header(auth_token),
    )

    assert response.status_code == 200
    body = response.get_json()['data']
    assert body['server.cfg'] == '// server'
    assert body['custom.cfg'] == '// custom'
    assert body['notes.txt'] == 'notes'
    assert 'ignored.factories' not in body
    for filename in ['mappool.txt', 'access.txt', 'workshop.txt']:
        assert filename in body


def test_create_instance_accepts_custom_cfg_and_factories(
    client, auth_token, sample_host, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    payload = {
        'name': 'custom-cfg-instance',
        'host_id': sample_host.id,
        'port': 27960,
        'hostname': 'custom.hostname',
        'configs': _full_configs(**{'custom.cfg': 'extra'}),
        'factories': {'duel.factories': 'factory'},
    }

    with patch('ui.routes.instance_routes.acquire_lock', return_value=True), \
         patch('ui.routes.instance_routes.enqueue_task', return_value=MagicMock(id='job-4')):
        response = client.post(
            '/api/instances/',
            json=payload,
            headers=_auth_header(auth_token),
        )

    assert response.status_code == 201, response.get_json()
    instance_id = response.get_json()['data']['id']
    instance_dir = tmp_path / 'configs' / sample_host.name / str(instance_id)
    assert (instance_dir / 'custom.cfg').read_text() == 'extra'
    assert (instance_dir / 'factories' / 'duel.factories').read_text() == 'factory'


@pytest.mark.parametrize(
    'payload_update',
    [
        {'configs': _full_configs(**{'bad.exe': 'bad'})},
        {'configs': _full_configs(**{'../bad.cfg': 'bad'})},
        {'factories': {'bad.txt': 'bad'}},
        {'factories': {'nested/bad.factories': 'bad'}},
    ],
)
def test_create_instance_rejects_invalid_file_maps_before_side_effects(
    client, auth_token, sample_host, payload_update, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    payload = {
        'name': 'invalid-file-instance',
        'host_id': sample_host.id,
        'port': 27960,
        'hostname': 'invalid.hostname',
        'configs': _full_configs(),
    }
    payload.update(payload_update)

    response = client.post(
        '/api/instances/',
        json=payload,
        headers=_auth_header(auth_token),
    )

    assert response.status_code == 400
    with client.application.app_context():
        assert QLInstance.query.count() == 0
    assert not (tmp_path / 'configs' / sample_host.name).exists()
