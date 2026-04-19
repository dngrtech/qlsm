import pytest
from unittest.mock import patch, MagicMock
from ui import create_app, db
from ui.models import Host, QLInstance, HostStatus, InstanceStatus


@pytest.fixture
def app_with_instance():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'JWT_COOKIE_CSRF_PROTECT': False,
        'JWT_TOKEN_LOCATION': ['headers'],
        'JWT_SECRET_KEY': 'test-secret',
    })
    with app.app_context():
        db.create_all()
        host = Host(id=1, name='test-host', provider='vultr',
                     status=HostStatus.ACTIVE, ip_address='1.2.3.4',
                     ssh_key_path='/fake/key', ssh_user='root', os_type='debian')
        db.session.add(host)
        inst = QLInstance(id=1, name='test-inst', host_id=1, hostname='test-host',
                          port=27960, status=InstanceStatus.RUNNING)
        db.session.add(inst)
        db.session.commit()
    return app


def _get_auth_headers(app):
    """Get JWT auth headers for test requests."""
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity='testuser')
        return {'Authorization': f'Bearer {token}'}


@patch('ui.routes.instance_routes.enqueue_task')
@patch('ui.routes.instance_routes.acquire_lock', return_value=False)
def test_restart_returns_409_when_locked(mock_lock, mock_enqueue, app_with_instance):
    """Restart should return 409 if entity lock is held."""
    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    resp = client.post('/api/instances/1/restart', headers=headers)
    assert resp.status_code == 409
    assert 'Another operation' in resp.get_json()['error']['message']
    mock_enqueue.assert_not_called()


@patch('ui.routes.instance_routes.enqueue_task')
@patch('ui.routes.instance_routes.acquire_lock', return_value=False)
def test_stop_returns_409_when_locked(mock_lock, mock_enqueue, app_with_instance):
    """Stop should return 409 if entity lock is held."""
    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    resp = client.post('/api/instances/1/stop', headers=headers)
    assert resp.status_code == 409
    assert 'Another operation' in resp.get_json()['error']['message']
    mock_enqueue.assert_not_called()


@patch('ui.routes.instance_routes.enqueue_task')
@patch('ui.routes.instance_routes.acquire_lock', return_value=False)
def test_start_returns_409_when_locked(mock_lock, mock_enqueue, app_with_instance):
    """Start should return 409 if entity lock is held."""
    # Need a STOPPED instance for start
    with app_with_instance.app_context():
        inst = db.session.get(QLInstance, 1)
        inst.status = InstanceStatus.STOPPED
        db.session.commit()

    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    resp = client.post('/api/instances/1/start', headers=headers)
    assert resp.status_code == 409
    assert 'Another operation' in resp.get_json()['error']['message']
    mock_enqueue.assert_not_called()


@patch('ui.routes.instance_routes.enqueue_task')
@patch('ui.routes.instance_routes.acquire_lock', return_value=False)
def test_delete_returns_409_when_locked(mock_lock, mock_enqueue, app_with_instance):
    """Delete should return 409 if entity lock is held."""
    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    resp = client.delete('/api/instances/1', headers=headers)
    assert resp.status_code == 409
    assert 'Another operation' in resp.get_json()['error']['message']
    mock_enqueue.assert_not_called()


@patch('ui.routes.host_routes.enqueue_task')
@patch('ui.routes.host_routes.acquire_lock', return_value=False)
def test_restart_host_returns_409_when_locked(mock_lock, mock_enqueue, app_with_instance):
    """Host restart should return 409 if entity lock is held."""
    with app_with_instance.app_context():
        host = db.session.get(Host, 1)
        host.status = HostStatus.ACTIVE
        db.session.commit()

    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    resp = client.post('/api/hosts/1/restart', headers=headers)
    assert resp.status_code == 409
    assert 'Another operation' in resp.get_json()['error']['message']
    mock_enqueue.assert_not_called()


@patch('ui.routes.host_routes.enqueue_task', side_effect=Exception("Redis down"))
@patch('ui.routes.host_routes.release_lock')
@patch('ui.routes.host_routes.acquire_lock', return_value=True)
def test_install_qlfilter_rollback_on_enqueue_failure(
    mock_lock, mock_release, mock_enqueue, app_with_instance
):
    """qlfilter_status must revert if enqueue fails after lock acquired."""
    from ui.models import QLFilterStatus
    with app_with_instance.app_context():
        host = db.session.get(Host, 1)
        host.status = HostStatus.ACTIVE
        host.qlfilter_status = QLFilterStatus.NOT_INSTALLED
        db.session.commit()

    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    resp = client.post('/api/hosts/1/qlfilter/install', headers=headers)
    assert resp.status_code == 500

    mock_release.assert_called_once()
    with app_with_instance.app_context():
        host = db.session.get(Host, 1)
        assert host.qlfilter_status == QLFilterStatus.NOT_INSTALLED


@patch('ui.routes.instance_routes.enqueue_task')
@patch('ui.routes.instance_routes.acquire_lock', return_value=False)
def test_manage_instance_config_returns_409_before_writing_files(
    mock_lock, mock_enqueue, app_with_instance, tmp_path, monkeypatch
):
    """Config PUT must not rewrite files when the instance lock cannot be acquired."""
    monkeypatch.chdir(tmp_path)
    config_root = tmp_path / 'configs' / 'test-host' / '1'
    config_root.mkdir(parents=True)
    server_cfg = config_root / 'server.cfg'
    server_cfg.write_text('original-config')
    scripts_dir = config_root / 'scripts'
    scripts_dir.mkdir()
    script_file = scripts_dir / 'restart.sh'
    script_file.write_text('original-script')
    factories_dir = config_root / 'factories'
    factories_dir.mkdir()
    factory_file = factories_dir / 'base.factories'
    factory_file.write_text('original-factory')

    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    payload = {
        'configs': {'server.cfg': 'updated-config'},
        'scripts': {'restart.sh': 'updated-script'},
        'factories': {'other.factories': 'updated-factory'},
    }

    with app_with_instance.app_context():
        resp = client.put('/api/instances/1/config', json=payload, headers=headers)

    assert resp.status_code == 409
    assert server_cfg.read_text() == 'original-config'
    assert script_file.read_text() == 'original-script'
    assert factory_file.read_text() == 'original-factory'
    assert not (factories_dir / 'other.factories').exists()
    mock_enqueue.assert_not_called()


@patch('ui.routes.instance_routes.release_lock')
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
def test_manage_instance_config_releases_lock_on_invalid_qlx_plugins(
    mock_lock, mock_release, app_with_instance
):
    """Config PUT must release the instance lock when qlx_plugins validation fails."""
    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)

    with app_with_instance.app_context():
        resp = client.put(
            '/api/instances/1/config',
            json={'configs': {}, 'qlx_plugins': ['bad-type']},
            headers=headers,
        )

    assert resp.status_code == 400
    assert 'qlx_plugins must be a string' in resp.get_json()['error']['message']
    mock_release.assert_called_once()


@patch('ui.routes.instance_routes.enqueue_task')
@patch('ui.routes.instance_routes.acquire_lock', return_value=True)
def test_manage_instance_config_updates_lan_rate_and_queues_single_apply_task(
    mock_lock, mock_enqueue, app_with_instance, tmp_path, monkeypatch
):
    """Config PUT should update LAN rate and queue one apply task under the same lock."""
    monkeypatch.chdir(tmp_path)
    config_root = tmp_path / 'configs' / 'test-host' / '1'
    config_root.mkdir(parents=True)
    server_cfg = config_root / 'server.cfg'
    server_cfg.write_text('original-config')

    mock_enqueue.return_value = MagicMock(id='job-123')

    client = app_with_instance.test_client()
    headers = _get_auth_headers(app_with_instance)
    payload = {
        'configs': {'server.cfg': 'updated-config'},
        'lan_rate_enabled': True,
        'restart': True,
    }

    with app_with_instance.app_context():
        resp = client.put('/api/instances/1/config', json=payload, headers=headers)
        instance = db.session.get(QLInstance, 1)

    assert resp.status_code == 202
    assert server_cfg.read_text() == 'updated-config'
    assert instance.lan_rate_enabled is True
    assert instance.status == InstanceStatus.CONFIGURING

    args, kwargs = mock_enqueue.call_args
    assert args[0].__name__ == 'apply_instance_config'
    assert args[1] == 1
    assert kwargs['restart'] is True
    assert 'lock_token' in kwargs
