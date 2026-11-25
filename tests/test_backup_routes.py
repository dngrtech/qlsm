import io
import json
import zipfile
from unittest.mock import patch

import pytest
from ui import db, task_lock
from ui.backup_crypto import MAGIC_ENCRYPTED, MAGIC_PLAIN, encrypt_archive
from ui.models import AddonState, Host, HostStatus
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.task_logic.backup_db_export import serialize_database
from tests.helpers import make_user, auth_headers
from tests.test_task_lock import ScriptRedis


@pytest.fixture
def app_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'VERSION').write_text('1.0.0')
    return tmp_path


class TestExportBackup:
    @patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
    def test_export_returns_a_downloadable_file(self, _lock, app, client, app_root):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        resp = client.post('/api/settings/backup/export', headers=headers, json={'password': None})
        assert resp.status_code == 200
        assert resp.headers['Content-Disposition'].startswith('attachment')
        # Our own container header, not a raw zip. (zipfile.is_zipfile() isn't a
        # reliable check here: ZIP tolerates arbitrary prefix bytes, so it finds
        # the EOCD record and returns True regardless of our QLBP/QLBE header.)
        assert resp.data[:4] == MAGIC_PLAIN

    @patch('ui.task_lock.acquire_maintenance_lock', return_value=False)
    def test_export_blocked_while_a_task_lock_is_held(self, _lock, app, client, app_root):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        resp = client.post('/api/settings/backup/export', headers=headers, json={})
        assert resp.status_code == 409

    @pytest.mark.parametrize('state,host_status,expected_status', [
        ('preparing', HostStatus.CONFIGURING, 409),
        ('recovery_required', HostStatus.ERROR, 409),
        ('succeeded', HostStatus.ACTIVE, 200),
        ('rolled_back', HostStatus.ACTIVE, 200),
        ('failed_preparation', HostStatus.ACTIVE, 200),
    ])
    def test_export_respects_custom_reservations_without_execution_locks(
            self, app, client, app_root, monkeypatch, state, host_status, expected_status):
        redis_client = ScriptRedis()
        monkeypatch.setattr(task_lock, '_get_redis', lambda: redis_client)
        app.config['ADDON_PACKAGES_DIR'] = str(app_root / 'custom-packages')
        headers = auth_headers(app, 'admin')
        with app.app_context():
            host = Host(name='custom-host', provider='standalone', runtime='custom',
                        runtime_provider_id='custom-provider', runtime_release_sha256='a' * 64,
                        runtime_plugin_api='minqlx', status=host_status)
            db.session.add(host)
            db.session.flush()
            operation = HostRuntimeUpgradeOperation(
                host_id=host.id, state=state, original_runtime='custom',
                original_host_status='active', recovery_required=state == 'recovery_required')
            db.session.add(operation)
            db.session.commit()

        # Queued operations and failed recovery attempts have durable rows but
        # no Redis execution locks between attempts.
        assert redis_client.values == {}
        response = client.post('/api/settings/backup/export', headers=headers, json={})

        assert response.status_code == expected_status
        assert redis_client.values == {}  # including early rejection releases maintenance
        if expected_status == 200:
            assert response.data.startswith(MAGIC_PLAIN)
        else:
            assert 'runtime upgrade' in response.get_json()['error']['message']
            # Archive construction takes a package lock; it must not begin.
            assert not (app_root / '.custom-packages.provider-locks').exists()
        with app.app_context():
            assert HostRuntimeUpgradeOperation.query.one().state == state
            assert Host.query.one().status == host_status

    def test_export_fences_new_custom_reservations_before_checking_existing_ones(
            self, app, client, app_root, monkeypatch):
        from tests.test_custom_runtime_release import PROVIDER, activate, runtime_package
        from ui.addons.install import install_addon_zip
        from ui.routes import backup_routes

        packages = app_root / 'custom-packages'
        old_package, old_digest = runtime_package()
        new_package, new_digest = runtime_package('2.0')
        with app.app_context():
            install_addon_zip(old_package, packages)
            install_addon_zip(new_package, packages)
        activate(app, packages)
        with app.app_context():
            host = Host(name='custom-host', provider='standalone', runtime='custom',
                        runtime_provider_id=PROVIDER, runtime_release_sha256=old_digest,
                        runtime_plugin_api='minqlx', status=HostStatus.ACTIVE)
            db.session.add(host)
            db.session.commit()
            update_url = f'/api/hosts/{host.id}/custom-runtime-update'
        headers = auth_headers(app, 'admin')
        data = client.get(update_url, headers=headers).get_json()['data']
        assert data['eligibility']['enabled'] is True
        body = {'action': 'update', 'fingerprint': data['fingerprint'], 'target_sha256': new_digest}
        redis_client = ScriptRedis()
        monkeypatch.setattr(task_lock, '_get_redis', lambda: redis_client)
        monkeypatch.setattr('ui.tasks.enqueue_task', lambda *_args, **_kwargs: None)
        reservation_statuses = []
        reserved_host_ids = backup_routes.reserved_host_ids

        def try_reserving_at_export_check():
            response = client.post(update_url, headers=headers, json=body)
            reservation_statuses.append(response.status_code)
            return reserved_host_ids()

        monkeypatch.setattr(backup_routes, 'reserved_host_ids', try_reserving_at_export_check)
        response = client.post('/api/settings/backup/export', headers=headers, json={})

        assert response.status_code == 200
        assert reservation_statuses == [409]
        assert redis_client.values == {}
        with app.app_context():
            assert HostRuntimeUpgradeOperation.query.count() == 0
            assert Host.query.one().status == HostStatus.ACTIVE
        # The same valid request succeeds once the export fence is released.
        assert client.post(update_url, headers=headers, json=body).status_code == 202

    def test_export_requires_auth(self, client, app_root):
        resp = client.post('/api/settings/backup/export', json={})
        assert resp.status_code == 401


@pytest.mark.parametrize('operation', ['export', 'import'])
@patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
def test_backup_maintenance_conflicts_with_an_addon_change(_lock, app, client, app_root, monkeypatch, operation):
    from ui.addons import runtime_protection

    app.config['ADDON_PACKAGES_DIR'] = str(app_root / 'custom-packages')
    make_user(app, 'admin', 'pw')
    headers = auth_headers(app, 'admin')
    export_url = '/api/settings/backup/export'
    blob = client.post(export_url, headers=headers, json={}).data
    monkeypatch.setattr(runtime_protection, 'LOCK_TIMEOUT_SECONDS', 0)

    with app.app_context():
        db.session.add(AddonState(addon_id='custom-provider', scope='global', enabled=True))
        db.session.commit()
        with runtime_protection.provider_lifecycle_lock('custom-provider'):
            if operation == 'export':
                resp = client.post(export_url, headers=headers, json={})
            else:
                resp = client.post(
                    '/api/settings/backup/import', headers=headers,
                    data={'file': (io.BytesIO(blob), 'backup.qlsmbak')},
                )

        assert resp.status_code == 409
        assert resp.get_json()['error']['code'] == 'runtime_provider_busy'
        assert AddonState.query.one().enabled is True
        assert not (app_root / 'backup_snapshots').exists()


@pytest.mark.parametrize('layout', ['nested', 'nested-symlink', 'lock-symlink'])
@pytest.mark.parametrize('operation', ['export', 'import'])
@patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
def test_overlapping_addon_backup_layout_leaves_destination_intact(_lock, app, client, app_root, layout, operation):
    from ui.addons import runtime_protection

    make_user(app, 'admin', 'pw')
    headers = auth_headers(app, 'admin')
    export_url = '/api/settings/backup/export'
    source_packages = app_root / 'source-packages'
    app.config['ADDON_PACKAGES_DIR'] = str(source_packages)
    package_path = 'custom-provider/qlsm-addon.json'
    bundle_path = f".runtime-releases/custom-provider/{'a' * 64}/bundle.tar.gz"
    for path, content in [(package_path, b'archived provider'), (bundle_path, b'archived retained release')]:
        source_file = source_packages / path
        source_file.parent.mkdir(parents=True)
        source_file.write_bytes(content)
    with app.app_context():
        state = AddonState(addon_id='custom-provider', scope='global', enabled=True)
        db.session.add(state)
        db.session.commit()
    source = client.post(export_url, headers=headers, json={})
    assert source.status_code == 200

    config_dir = app_root / 'configs'
    config_dir.mkdir()
    packages = config_dir / 'addon-packages' if layout == 'nested' else app_root / 'destination-packages'
    packages.mkdir()
    configured_packages = packages
    lock_dir = packages.parent / f'.{packages.name}.provider-locks'
    if layout == 'nested-symlink':
        configured_packages = config_dir / 'linked-packages'
        configured_packages.symlink_to(packages, target_is_directory=True)
    if layout == 'lock-symlink':
        redirected_locks = config_dir / 'redirected-locks'
        redirected_locks.mkdir()
        lock_dir.symlink_to(redirected_locks, target_is_directory=True)
    app.config['ADDON_PACKAGES_DIR'] = str(configured_packages)

    local_package = packages / package_path
    local_bundle = packages / bundle_path
    for path, content in [(local_package, b'local provider'), (local_bundle, b'local retained release')]:
        path.parent.mkdir(parents=True)
        path.write_bytes(content)

    maintenance_lock = lock_dir / runtime_protection._MAINTENANCE_FILE
    with app.app_context():
        state = AddonState.query.one()
        state.enabled = False
        state.settings_json = '{"profile": "local-only"}'
        db.session.commit()
        if operation == 'import':
            with runtime_protection.provider_lifecycle_lock('custom-provider'):
                original_inode = maintenance_lock.stat().st_ino

    if operation == 'export':
        response = client.post(export_url, headers=headers, json={})
        assert not maintenance_lock.exists()
    else:
        response = client.post(
            '/api/settings/backup/import', headers=headers,
            data={'file': (io.BytesIO(source.data), 'backup.qlsmbak')},
        )
        assert maintenance_lock.stat().st_ino == original_inode
        assert not (app_root / 'backup_snapshots').exists()

    assert local_package.read_bytes() == b'local provider'
    assert local_bundle.read_bytes() == b'local retained release'
    with app.app_context():
        state = AddonState.query.one()
        assert state.enabled is False
        assert state.settings == {'profile': 'local-only'}

    assert response.status_code == 409
    error = response.get_json()['error']
    assert error['code'] == 'backup_layout_conflict'
    assert 'ADDON_PACKAGES_DIR' in error['message']


@pytest.mark.parametrize('symlink_location', [
    'package-directory', 'parent-directory', 'parent-before-dot-dot', 'maintenance-lock-directory',
])
@pytest.mark.parametrize('operation', ['export', 'import'])
@patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
def test_backup_rejects_symlinks_in_package_and_lock_paths(_lock, app, client, app_root, symlink_location, operation):
    from ui.addons import runtime_protection

    make_user(app, 'admin', 'pw')
    headers = auth_headers(app, 'admin')
    export_url = '/api/settings/backup/export'
    if operation == 'import':
        source = client.post(export_url, headers=headers, json={})
        assert source.status_code == 200

    packages = app_root / 'direct-parent' / 'packages'
    packages.mkdir(parents=True)
    local_file = packages / 'local-package'
    local_file.write_text('keep installed package')
    lock_dir = runtime_protection.addon_lifecycle_lock_directory(packages)
    configured_packages = packages
    if symlink_location == 'package-directory':
        configured_packages = app_root / 'linked-packages'
        configured_packages.symlink_to(packages, target_is_directory=True)
    elif symlink_location == 'parent-directory':
        linked_parent = app_root / 'linked-parent'
        linked_parent.symlink_to(packages.parent, target_is_directory=True)
        configured_packages = linked_parent / packages.name
    elif symlink_location == 'parent-before-dot-dot':
        linked_parent = app_root / 'linked-parent'
        linked_parent.symlink_to(packages, target_is_directory=True)
        configured_packages = linked_parent / '..' / packages.name
    else:
        direct_locks = app_root / 'separate-locks'
        direct_locks.mkdir()
        lock_dir.symlink_to(direct_locks, target_is_directory=True)
    app.config['ADDON_PACKAGES_DIR'] = str(configured_packages)

    if operation == 'export':
        response = client.post(export_url, headers=headers, json={})
    else:
        response = client.post(
            '/api/settings/backup/import', headers=headers,
            data={'file': (io.BytesIO(source.data), 'backup.qlsmbak')},
        )

    assert response.status_code == 409
    error = response.get_json()['error']
    assert error['code'] == 'backup_layout_conflict'
    assert 'symbolic links' in error['message']
    assert local_file.read_text() == 'keep installed package'
    assert not (lock_dir / runtime_protection._MAINTENANCE_FILE).exists()
    assert not (app_root / 'backup_snapshots').exists()
    assert not list(packages.glob('.qlsm-restore-*'))


@pytest.mark.parametrize('parent_exists', [True, False], ids=['existing-parent', 'missing-parent'])
@patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
def test_backup_preflight_rejects_parent_traversal(_lock, app, client, app_root, parent_exists):
    from ui.addons.runtime_protection import addon_lifecycle_lock_directory

    make_user(app, 'admin', 'pw')
    headers = auth_headers(app, 'admin')
    packages = app_root / 'packages'
    packages.mkdir()
    package = packages / 'local-package'
    package.write_text('keep installed package')
    parent = app_root / 'traversed-parent'
    if parent_exists:
        parent.mkdir()
    app.config['ADDON_PACKAGES_DIR'] = str(parent / '..' / packages.name)

    response = client.post('/api/settings/backup/export', headers=headers, json={})

    assert response.status_code == 409
    error = response.get_json()['error']
    assert error['code'] == 'backup_layout_conflict'
    assert '..' in error['message']
    assert package.read_text() == 'keep installed package'
    assert not addon_lifecycle_lock_directory(packages).exists()
    assert parent.exists() is parent_exists


class TestImportBackup:
    @patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
    def test_import_round_trip(self, _lock, app, client, app_root):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        digest = 'a' * 64
        packages_dir = app_root / 'custom-packages'
        app.config['ADDON_PACKAGES_DIR'] = str(packages_dir)
        package = packages_dir / 'custom-provider' / 'qlsm-addon.json'
        bundle = packages_dir / '.runtime-releases' / 'custom-provider' / digest / 'bundle.tar.gz'
        for path, payload in [(package, b'provider package'), (bundle, b'retained runtime bundle')]:
            path.parent.mkdir(parents=True)
            path.write_bytes(payload)

        with app.app_context():
            db.session.add(Host(
                name='exported-host', provider='standalone', is_standalone=True, runtime='custom',
                runtime_provider_id='custom-provider', runtime_release_sha256=digest,
                runtime_plugin_api='minqlx',
            ))
            db.session.add(AddonState(
                addon_id='custom-provider', scope='global', enabled=True,
                settings_json='{"token": "test-provider-secret"}',
            ))
            db.session.commit()

        export_resp = client.post('/api/settings/backup/export', headers=headers, json={'password': 'backup-pw'})
        blob = export_resp.data
        assert blob.startswith(MAGIC_ENCRYPTED)
        package.unlink()
        bundle.unlink()

        with app.app_context():
            db.session.query(Host).delete()
            db.session.query(AddonState).delete()
            db.session.commit()

        import_resp = client.post(
            '/api/settings/backup/import',
            headers=headers,
            data={'file': (io.BytesIO(blob), 'backup.qlsmbak'), 'password': 'backup-pw'},
            content_type='multipart/form-data',
        )
        assert import_resp.status_code == 200
        payload = import_resp.get_json()
        assert payload['data']['restart_required'] is True
        assert payload['data']['addon_state_restored'] is True
        assert payload['data']['qlsm_version'] == '1.0.0'
        assert payload['data']['created_at']
        assert 'restart all qlsm application and worker processes' in payload['message'].lower()
        assert 'test-provider-secret' not in import_resp.get_data(as_text=True)
        assert package.read_bytes() == b'provider package'
        assert bundle.read_bytes() == b'retained runtime bundle'
        with app.app_context():
            host = Host.query.one()
            state = AddonState.query.one()
            assert (host.name, host.runtime, host.runtime_provider_id) == (
                'exported-host', 'custom', 'custom-provider',
            )
            assert (state.addon_id, state.enabled, state.settings) == (
                'custom-provider', True, {'token': 'test-provider-secret'},
            )

    @pytest.mark.parametrize('legacy', [True, False], ids=['legacy', 'empty-collection'])
    @patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
    def test_reports_addon_state_compatibility(self, _lock, app, client, app_root, legacy):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        with app.app_context():
            snapshot = serialize_database()
            snapshot['addon_states'] = []
            if legacy:
                del snapshot['addon_states']
            db.session.add(AddonState(addon_id='custom-provider', scope='global', enabled=True))
            db.session.commit()

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('manifest.json', json.dumps({'type': 'qlsm-global-backup', 'format_version': 1}))
            archive.writestr('db_export.json', json.dumps(snapshot))
        blob = encrypt_archive(buffer.getvalue(), None)
        resp = client.post(
            '/api/settings/backup/import', headers=headers,
            data={'file': (io.BytesIO(blob), 'backup.qlsmbak')},
        )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['data']['restart_required'] is True
        assert payload['data']['addon_state_restored'] is (not legacy)
        message = payload['message'].lower()
        assert 'restart all qlsm application and worker processes' in message
        assert ('enable' in message and 'configure' in message) is legacy
        with app.app_context():
            assert AddonState.query.count() == 0

    @patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
    def test_restore_does_not_log_database_errors_containing_settings(self, _lock, app, client, app_root, caplog):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        blob = client.post('/api/settings/backup/export', headers=headers, json={}).data

        with patch('ui.task_logic.backup_import.db.session.commit', side_effect=RuntimeError('test-add-on-secret')):
            resp = client.post(
                '/api/settings/backup/import', headers=headers,
                data={'file': (io.BytesIO(blob), 'backup.qlsmbak')},
            )

        assert resp.status_code == 500
        assert 'test-add-on-secret' not in resp.get_data(as_text=True)
        assert 'test-add-on-secret' not in caplog.text

    @patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
    def test_import_wrong_password_returns_400(self, _lock, app, client, app_root):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        export_resp = client.post('/api/settings/backup/export', headers=headers, json={'password': 'right'})

        resp = client.post(
            '/api/settings/backup/import',
            headers=headers,
            data={'file': (io.BytesIO(export_resp.data), 'backup.qlsmbak'), 'password': 'wrong'},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 400

    @patch('ui.task_lock.acquire_maintenance_lock', return_value=False)
    def test_import_blocked_while_a_task_lock_is_held(self, _lock, app, client, app_root):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        resp = client.post(
            '/api/settings/backup/import',
            headers=headers,
            data={'file': (io.BytesIO(b'anything'), 'backup.qlsmbak')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 409

    @patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
    def test_import_blocked_while_a_runtime_upgrade_is_nonterminal(self, _lock, app, client, app_root):
        from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation

        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        blob = client.post('/api/settings/backup/export', headers=headers, json={}).data
        with app.app_context():
            host = Host(name='upgrading', provider='vultr')
            db.session.add(host)
            db.session.flush()
            db.session.add(HostRuntimeUpgradeOperation(host_id=host.id, state='recovery_required'))
            db.session.commit()
        with patch('ui.routes.backup_routes.restore_backup_archive') as restore:
            resp = client.post(
                '/api/settings/backup/import',
                headers=headers,
                data={'file': (io.BytesIO(blob), 'backup.qlsmbak')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 409
        assert 'runtime upgrade' in resp.get_json()['error']['message']
        restore.assert_not_called()
        with app.app_context():
            assert HostRuntimeUpgradeOperation.query.count() == 1

    def test_import_requires_a_file(self, app, client, app_root):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')
        with patch('ui.task_lock.acquire_maintenance_lock', return_value=True):
            resp = client.post('/api/settings/backup/import', headers=headers, data={}, content_type='multipart/form-data')
        assert resp.status_code == 400
