from ui import db
from ui.models import Host, InstanceAdmin, QLInstance
from ui.task_logic.backup_db_export import serialize_database
from ui.task_logic.backup_db_import import replace_database


def _seed():
    host = Host(name='host-b', ip_address='10.0.0.2', ssh_user='root',
                ssh_key_path='/keys/id', ssh_port=22, provider='vultr')
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(name='inst-b', port=27990, hostname='hn', host_id=host.id)
    db.session.add(instance)
    db.session.flush()
    db.session.add(InstanceAdmin(instance_id=instance.id, steam_id64='76561198012345678', level=3))
    db.session.commit()
    return instance


def _seed_second():
    host = Host(name='host-b2', ip_address='10.0.0.3', ssh_user='root',
                ssh_key_path='/keys/id', ssh_port=22, provider='vultr')
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(name='inst-b2', port=27991, hostname='hn', host_id=host.id)
    db.session.add(instance)
    db.session.commit()
    return instance


def test_export_includes_admin_rows(app):
    with app.app_context():
        instance = _seed()
        payload = serialize_database()
        assert {'instance_id': instance.id, 'steam_id64': '76561198012345678', 'level': 3} \
            in payload['instance_admins']


def test_import_restores_admin_rows(app):
    with app.app_context():
        instance = _seed()
        payload = serialize_database()
        replace_database(payload)
        assert InstanceAdmin.query.filter_by(instance_id=instance.id).count() == 1


def test_import_keeps_each_row_on_the_right_instance(app):
    """Two instances with interleaved admin rows -- pins the restore mapping."""
    with app.app_context():
        first = _seed()
        second = _seed_second()
        db.session.add_all([
            InstanceAdmin(instance_id=second.id, steam_id64='76561198087654321', level=5),
            InstanceAdmin(instance_id=first.id, steam_id64='76561198111111111', level=1),
        ])
        db.session.commit()
        first_id, second_id = first.id, second.id
        payload = serialize_database()
        replace_database(payload)

        def rows(instance_id):
            return sorted(
                (a.steam_id64, a.level)
                for a in InstanceAdmin.query.filter_by(instance_id=instance_id).all()
            )

        assert rows(first_id) == [('76561198012345678', 3), ('76561198111111111', 1)]
        assert rows(second_id) == [('76561198087654321', 5)]


def test_import_tolerates_a_backup_without_the_key(app):
    with app.app_context():
        _seed()
        payload = serialize_database()
        payload.pop('instance_admins')
        replace_database(payload)
        assert InstanceAdmin.query.count() == 0
