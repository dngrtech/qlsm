import pytest

from ui import db
from ui.models import Host, InstanceAdmin, QLInstance


def _instance(name='inst-1', port=27960):
    host = Host(name=f'host-for-{name}', provider='vultr', ip_address='10.0.0.1', ssh_user='root',
                ssh_key_path='/keys/id', ssh_port=22)
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(name=name, port=port, hostname='hn', host_id=host.id)
    db.session.add(instance)
    db.session.flush()
    return instance


def test_rows_persist_and_read_back(app):
    with app.app_context():
        instance = _instance()
        db.session.add(InstanceAdmin(instance_id=instance.id, steam_id64='76561198012345678', level=3))
        db.session.commit()
        assert [(a.steam_id64, a.level) for a in instance.admins] == [('76561198012345678', 3)]


def test_same_steamid_twice_on_one_instance_is_rejected(app):
    with app.app_context():
        instance = _instance(name='inst-2', port=27961)
        db.session.add(InstanceAdmin(instance_id=instance.id, steam_id64='76561198012345678', level=1))
        db.session.commit()
        db.session.add(InstanceAdmin(instance_id=instance.id, steam_id64='76561198012345678', level=2))
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()


def test_deleting_the_instance_removes_its_admins(app):
    with app.app_context():
        instance = _instance(name='inst-3', port=27962)
        db.session.add(InstanceAdmin(instance_id=instance.id, steam_id64='76561198012345678', level=5))
        db.session.commit()
        db.session.delete(instance)
        db.session.commit()
        assert InstanceAdmin.query.count() == 0


def test_deleting_the_host_removes_its_instances_admins(app):
    with app.app_context():
        instance = _instance(name='inst-4', port=27963)
        host = instance.host
        db.session.add(InstanceAdmin(instance_id=instance.id, steam_id64='76561198012345678', level=5))
        db.session.commit()
        db.session.delete(host)
        db.session.commit()
        assert InstanceAdmin.query.count() == 0


def test_delete_instance_helper_leaves_no_rows_for_a_reused_id(app):
    """SQLite reuses the rowid of the highest deleted row, so a leaked admin row
    would be inherited by the next instance created."""
    from ui.database import delete_instance

    with app.app_context():
        instance = _instance(name='inst-5', port=27964)
        old_id = instance.id
        db.session.add(InstanceAdmin(instance_id=old_id, steam_id64='76561198012345678', level=5))
        db.session.commit()
        delete_instance(old_id)
        assert InstanceAdmin.query.filter_by(instance_id=old_id).count() == 0
        replacement = _instance(name='inst-6', port=27965)
        db.session.commit()
        assert replacement.admins == []
