import datetime
import json

import pytest
from ui import db
from ui.models import AddonState, Host, QLInstance, User, ConfigPreset, ApiKey, AppSetting, BinaryMetadata, HostStatus, InstanceStatus, Notification
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


def _addon_state_row(**overrides):
    return {
        'id': 40,
        'addon_id': 'custom-provider',
        'scope': 'global',
        'scope_id': 0,
        'enabled': True,
        'settings': {'credentials': {'token': 'test-token'}, 'mirrors': ['one', None]},
        'created_at': '2026-10-01T12:00:05.123456',
        'updated_at': '2026-10-02T12:01:30',
        **overrides,
    }


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

    def test_exports_addon_state_as_an_object_in_version_one(self, app):
        with app.app_context():
            db.session.add(AddonState(
                id=40, addon_id='custom-provider', scope='global', scope_id=0, enabled=True,
                settings_json='{"credentials":{"token":"test-token"},"mirrors":["one",null]}',
                created_at=datetime.datetime(2026, 10, 1, 12, 0, 5, 123456),
                updated_at=datetime.datetime(2026, 10, 2, 12, 1, 30),
            ))
            db.session.commit()

            data = json.loads(json.dumps(serialize_database()))

            assert data['format_version'] == 1
            assert data['addon_states'] == [_addon_state_row()]


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

    def test_restores_all_addon_scopes_and_replaces_destination_state(self, app):
        _seed(app)
        with app.app_context():
            exported = serialize_database()
            exported['addon_states'] = [
                _addon_state_row(),
                _addon_state_row(id=41, scope='host', scope_id=Host.query.one().id,
                                 enabled=False, settings={'local': ['host']}),
                _addon_state_row(id=42, scope='instance', scope_id=QLInstance.query.one().id,
                                 settings={'local': ['instance']}, updated_at=None),
            ]
            db.session.add_all([
                AddonState(id=40, addon_id='custom-provider', scope='global', enabled=False),
                AddonState(addon_id='destination-addon', scope='host', scope_id=Host.query.one().id,
                           enabled=True),
            ])
            db.session.commit()

            replace_database(exported)
            db.session.commit()

            rows = AddonState.query.order_by(AddonState.id).all()
            assert [row.to_dict() for row in rows] == exported['addon_states']

    @pytest.mark.parametrize('archive_states', ['absent', 'empty'])
    def test_archive_without_addon_rows_clears_destination_state(self, app, archive_states):
        _seed(app)
        with app.app_context():
            exported = serialize_database()
            if archive_states == 'absent':
                exported.pop('addon_states', None)
            else:
                exported['addon_states'] = []
            db.session.add_all([
                AddonState(addon_id='custom-provider', scope='global', enabled=True),
                AddonState(addon_id='custom-provider', scope='host', scope_id=Host.query.one().id,
                           enabled=True),
                AddonState(addon_id='custom-provider', scope='instance', scope_id=QLInstance.query.one().id,
                           enabled=True),
            ])
            db.session.commit()

            replace_database(exported)
            db.session.commit()

            assert AddonState.query.count() == 0

    @pytest.mark.parametrize('archive_states', [
        pytest.param(None, id='null-collection'),
        pytest.param({}, id='object-collection'),
        pytest.param([None], id='invalid-row'),
        pytest.param([_addon_state_row(id=True)], id='boolean-id'),
        pytest.param([_addon_state_row(id=2 ** 63)], id='out-of-range-id'),
        pytest.param([_addon_state_row(addon_id='bad/provider')], id='invalid-addon-id'),
        pytest.param([_addon_state_row(scope='cluster')], id='invalid-scope'),
        pytest.param([_addon_state_row(scope_id=False)], id='boolean-scope-id'),
        pytest.param([_addon_state_row(scope_id=1)], id='invalid-global-scope-id'),
        pytest.param([_addon_state_row(scope='host', scope_id=99)], id='orphaned-host-scope'),
        pytest.param([_addon_state_row(scope='instance', scope_id=99)], id='orphaned-instance-scope'),
        pytest.param([_addon_state_row(enabled=1)], id='non-boolean-enabled'),
        pytest.param([_addon_state_row(settings=['secret-marker'])], id='non-object-settings'),
        pytest.param([_addon_state_row(updated_at='secret-marker')], id='invalid-timestamp'),
        pytest.param([_addon_state_row(), _addon_state_row(id=41)], id='duplicate-scope'),
        pytest.param([_addon_state_row(), _addon_state_row(addon_id='duplicate-id')], id='duplicate-id'),
    ])
    def test_invalid_addon_state_is_rejected_before_deleting_rows(self, app, archive_states):
        _seed(app)
        with app.app_context():
            exported = serialize_database()
            exported['hosts'][0]['name'] = 'archive-host'
            exported['addon_states'] = archive_states
            db.session.add(AddonState(addon_id='destination-addon', scope='global', enabled=True))
            db.session.commit()

            with pytest.raises(BackupImportError, match='addon_states') as error:
                replace_database(exported)

            assert 'secret-marker' not in str(error.value)
            assert Host.query.one().name == 'host-1'
            db.session.rollback()
            assert Host.query.one().name == 'host-1'
            assert AddonState.query.one().addon_id == 'destination-addon'

    def test_out_of_range_scope_id_is_rejected_even_if_listed_as_a_host(self, app):
        _seed(app)
        with app.app_context():
            exported = serialize_database()
            invalid_id = 2 ** 63
            exported['hosts'][0]['id'] = invalid_id
            exported['addon_states'] = [_addon_state_row(scope='host', scope_id=invalid_id)]

            with pytest.raises(BackupImportError, match='invalid scope ID'):
                replace_database(exported)

            assert Host.query.one().name == 'host-1'

    def test_rejects_missing_format_version(self, app):
        with app.app_context():
            with pytest.raises(BackupImportError):
                replace_database({'hosts': [], 'instances': [], 'users': [], 'presets': [], 'api_keys': [], 'app_settings': [], 'binary_metadata': []})

    def test_rejects_missing_table_key(self, app):
        with app.app_context():
            with pytest.raises(BackupImportError):
                replace_database({'format_version': 1, 'hosts': []})
