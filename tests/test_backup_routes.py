import io
import json
from unittest.mock import patch

import pytest
from ui import db
from ui.backup_crypto import MAGIC_PLAIN
from ui.models import Host
from tests.helpers import make_user, auth_headers


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

    def test_export_requires_auth(self, client, app_root):
        resp = client.post('/api/settings/backup/export', json={})
        assert resp.status_code == 401


class TestImportBackup:
    @patch('ui.task_lock.acquire_maintenance_lock', return_value=True)
    def test_import_round_trip(self, _lock, app, client, app_root):
        make_user(app, 'admin', 'pw')
        headers = auth_headers(app, 'admin')

        with app.app_context():
            db.session.add(Host(name='exported-host', provider='vultr'))
            db.session.commit()

        export_resp = client.post('/api/settings/backup/export', headers=headers, json={})
        blob = export_resp.data

        with app.app_context():
            db.session.query(Host).delete()
            db.session.commit()

        import_resp = client.post(
            '/api/settings/backup/import',
            headers=headers,
            data={'file': (io.BytesIO(blob), 'backup.qlsmbak')},
            content_type='multipart/form-data',
        )
        assert import_resp.status_code == 200
        with app.app_context():
            assert [h.name for h in Host.query.all()] == ['exported-host']

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
