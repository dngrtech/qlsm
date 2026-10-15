import datetime

import pytest
from ui import db
from ui.models import Host, QLInstance, User, ConfigPreset, ApiKey, AppSetting, BinaryMetadata, HostStatus, InstanceStatus, Notification
from ui.task_logic.backup_db_export import serialize_database
from ui.task_logic.backup_db_import import replace_database, BackupImportError


def _seed(app):
    with app.app_context():
        host = Host(name='host-1', provider='vultr', status=HostStatus.ACTIVE)
        db.session.add(host)
        db.session.flush()
        db.session.add(QLInstance(name='inst-1', port=27960, hostname='srv1', host_id=host.id, status=InstanceStatus.RUNNING))
        db.session.add(User(username='admin', password_hash='hashed'))
        db.session.add(ConfigPreset(name='mypreset', path='configs/presets/mypreset'))
        db.session.add(ApiKey(key='apikey123'))
        db.session.add(AppSetting(key='vultr_api_key', value='vultrkey'))
        db.session.add(BinaryMetadata(context_type='preset', context_key='mypreset', file_path='foo.so', description='desc'))
        db.session.commit()


class TestSerializeDatabase:
    def test_includes_every_table(self, app):
        _seed(app)
        with app.app_context():
            data = serialize_database()
            assert data['format_version'] == 1
            assert len(data['hosts']) == 1
            assert data['hosts'][0]['name'] == 'host-1'
            assert len(data['instances']) == 1
            assert data['instances'][0]['host_id'] == data['hosts'][0]['id']
            assert len(data['users']) == 1
            assert data['users'][0]['password_hash'] == 'hashed'
            assert len(data['presets']) == 1
            assert len(data['api_keys']) == 1
            assert len(data['app_settings']) == 1
            assert data['app_settings'][0] == {'key': 'vultr_api_key', 'value': 'vultrkey'}
            assert len(data['binary_metadata']) == 1


class TestReplaceDatabase:
    def test_round_trip(self, app):
        _seed(app)
        with app.app_context():
            exported = serialize_database()
            replace_database(exported)
            db.session.commit()
            assert Host.query.count() == 1
            assert Host.query.first().name == 'host-1'
            assert QLInstance.query.count() == 1
            assert QLInstance.query.first().host_id == Host.query.first().id
            assert User.query.count() == 1
            assert ConfigPreset.query.count() == 1
            assert ApiKey.query.count() == 1
            assert AppSetting.query.count() == 1
            assert BinaryMetadata.query.count() == 1

    def test_wipes_existing_rows_not_in_import(self, app):
        _seed(app)
        with app.app_context():
            exported = serialize_database()
            # Add an extra row that isn't in the export.
            db.session.add(Host(name='extra-host', provider='standalone'))
            db.session.commit()
            replace_database(exported)
            db.session.commit()
            names = {h.name for h in Host.query.all()}
            assert names == {'host-1'}

    def test_ids_preserved_and_future_inserts_still_unique(self, app):
        _seed(app)
        with app.app_context():
            original_id = Host.query.first().id
            exported = serialize_database()
            replace_database(exported)
            db.session.commit()
            assert Host.query.first().id == original_id
            db.session.add(Host(name='new-after-restore', provider='standalone'))
            db.session.commit()
            ids = [h.id for h in Host.query.all()]
            assert len(ids) == len(set(ids))  # no collision

    def test_notifications_round_trip(self, app):
        _seed(app)
        with app.app_context():
            db.session.add(Notification(
                source='sample-addon', severity='critical', title='Host down', body='details',
                link='/servers', key='host-1', resolved_at=datetime.datetime(2026, 10, 1, 12, 0),
                read_at=datetime.datetime(2026, 10, 1, 12, 5),
            ))
            db.session.commit()
            exported = serialize_database()
            assert len(exported['notifications']) == 1
            db.session.add(Notification(source='core', severity='info', title='not in backup'))
            db.session.commit()

            replace_database(exported)
            db.session.commit()
            row = Notification.query.one()
            assert (row.source, row.severity, row.title, row.body, row.link, row.key) == (
                'sample-addon', 'critical', 'Host down', 'details', '/servers', 'host-1')
            assert row.resolved_at == datetime.datetime(2026, 10, 1, 12, 0)
            assert row.read_at == datetime.datetime(2026, 10, 1, 12, 5)

    def test_backup_without_notifications_restores(self, app):
        _seed(app)
        with app.app_context():
            db.session.add(Notification(source='core', severity='info', title='stale'))
            db.session.commit()
            exported = serialize_database()
            del exported['notifications']  # a backup taken before the table existed
            replace_database(exported)
            db.session.commit()
            assert Notification.query.count() == 0

    def test_rejects_missing_format_version(self, app):
        with app.app_context():
            with pytest.raises(BackupImportError):
                replace_database({'hosts': [], 'instances': [], 'users': [], 'presets': [], 'api_keys': [], 'app_settings': [], 'binary_metadata': []})

    def test_rejects_missing_table_key(self, app):
        with app.app_context():
            with pytest.raises(BackupImportError):
                replace_database({'format_version': 1, 'hosts': []})
