"""A config row must not outlive its instance, and must survive a backup trip."""
import json

from ui import db
from ui.models import Host, QLInstance, RankProviderConfig
from ui.task_logic.backup_db_export import serialize_database
from ui.task_logic.backup_db_import import replace_database


def _seed_instance(name='inst-a', port=27960):
    host = Host.query.filter_by(name='host-a').first()
    if host is None:
        host = Host(name='host-a', ip_address='10.0.0.1', ssh_user='root',
                    ssh_key_path='/keys/id', ssh_port=22, provider='vultr')
        db.session.add(host)
        db.session.flush()
    instance = QLInstance(name=name, port=port, hostname='hn', host_id=host.id)
    db.session.add(instance)
    db.session.flush()
    db.session.add(RankProviderConfig(
        instance_id=instance.id, provider_type='elo_service',
        base_url='http://elo:5002', api_key='secret-key',
        game_type='ffa_auto', extra=json.dumps({}), enabled=True,
    ))
    db.session.commit()
    return instance.id


def test_deleting_an_instance_removes_its_config(app):
    with app.app_context():
        instance_id = _seed_instance()
        instance = db.session.get(QLInstance, instance_id)
        db.session.delete(instance)
        db.session.commit()
        assert RankProviderConfig.query.filter_by(instance_id=instance_id).count() == 0


def test_config_is_exported(app):
    with app.app_context():
        instance_id = _seed_instance()
        snapshot = serialize_database()
        assert 'rank_provider_configs' in snapshot
        row = snapshot['rank_provider_configs'][0]
        assert row['instance_id'] == instance_id
        assert row['provider_type'] == 'elo_service'
        assert row['api_key'] == 'secret-key'


def test_backup_round_trip_reattaches_the_config(app):
    with app.app_context():
        instance_id = _seed_instance()
        snapshot = serialize_database()
        replace_database(snapshot)
        db.session.commit()
        configs = RankProviderConfig.query.all()
        assert len(configs) == 1
        assert configs[0].instance_id == instance_id
        assert configs[0].api_key == 'secret-key'


def test_restore_does_not_strand_a_config_on_a_reused_id(app):
    """A pre-existing config for id N must not survive a restore that creates a
    DIFFERENT instance with id N — otherwise one operator's token silently
    points at another operator's server."""
    with app.app_context():
        _seed_instance(name='old', port=27960)
        snapshot = serialize_database()
        # An archive that has the same instance id but no config row for it.
        snapshot['rank_provider_configs'] = []
        replace_database(snapshot)
        db.session.commit()
        assert RankProviderConfig.query.count() == 0


def test_an_older_archive_without_the_key_still_restores(app):
    """'rank_provider_configs' is optional, following the 'operators' precedent."""
    with app.app_context():
        _seed_instance()
        snapshot = serialize_database()
        del snapshot['rank_provider_configs']
        replace_database(snapshot)
        db.session.commit()
        assert RankProviderConfig.query.count() == 0
        assert QLInstance.query.count() == 1
