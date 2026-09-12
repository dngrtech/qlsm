from ui import db
from ui.admin_permissions import replace_instance_admins
from ui.models import Host, InstanceAdmin, QLInstance


def _instance():
    host = Host(name='host-s', ip_address='10.0.0.9', ssh_user='root',
                ssh_key_path='/keys/id', ssh_port=22, provider='vultr')
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(name='inst-s', port=27970, hostname='hn', host_id=host.id)
    db.session.add(instance)
    db.session.flush()
    return instance


def test_replace_swaps_the_whole_list(app):
    with app.app_context():
        instance = _instance()
        replace_instance_admins(instance, [{'steam_id64': '76561198012345678', 'level': 1}])
        db.session.commit()
        replace_instance_admins(instance, [{'steam_id64': '76561198087654321', 'level': 4}])
        db.session.commit()
        rows = InstanceAdmin.query.filter_by(instance_id=instance.id).all()
        assert [(r.steam_id64, r.level) for r in rows] == [('76561198087654321', 4)]


def test_replace_with_empty_list_clears(app):
    with app.app_context():
        instance = _instance()
        replace_instance_admins(instance, [{'steam_id64': '76561198012345678', 'level': 1}])
        db.session.commit()
        replace_instance_admins(instance, [])
        db.session.commit()
        assert InstanceAdmin.query.filter_by(instance_id=instance.id).count() == 0


def test_replace_is_idempotent(app):
    with app.app_context():
        instance = _instance()
        entries = [{'steam_id64': '76561198012345678', 'level': 1}]
        replace_instance_admins(instance, entries)
        db.session.commit()
        replace_instance_admins(instance, entries)
        db.session.commit()
        assert InstanceAdmin.query.filter_by(instance_id=instance.id).count() == 1
