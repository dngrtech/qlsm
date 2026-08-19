"""Verify the SQLAlchemy ORM default (`default=False`) and the alembic
server-default (`server_default='0'`) agree, so test-suite rows created
via `db.create_all()` get the same baseline as production rows created
via `flask db upgrade`."""
import tempfile
import os
from ui import create_app
from ui.models import Host, db


def _make_app():
    db_fd, db_path = tempfile.mkstemp()
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
    return app, db_fd, db_path


def test_host_lan_rate_uses_hook_defaults_false():
    app, db_fd, db_path = _make_app()
    try:
        with app.app_context():
            host = Host(
                name="default-test",
                provider="vultr",
                os_type="debian",
                ip_address="1.2.3.4",
            )
            db.session.add(host)
            db.session.commit()
            assert host.lan_rate_uses_hook is False
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        os.close(db_fd)
        for path in (db_path, f'{db_path}-wal', f'{db_path}-shm'):
            if os.path.exists(path):
                os.unlink(path)


def test_qlinstance_to_dict_exposes_host_lan_rate_uses_hook():
    """Required for frontend instance-scoped components."""
    from ui.models import QLInstance, InstanceStatus
    app, db_fd, db_path = _make_app()
    try:
        with app.app_context():
            host = Host(
                name="serializer-test",
                provider="vultr",
                os_type="debian",
                ip_address="1.2.3.4",
                lan_rate_uses_hook=True,
            )
            db.session.add(host)
            db.session.commit()
            instance = QLInstance(
                host_id=host.id,
                name="i",
                port=27960,
                hostname="test-server",
                lan_rate_enabled=False,
                status=InstanceStatus.RUNNING,
            )
            db.session.add(instance)
            db.session.commit()
            d = instance.to_dict()
            assert d['host_lan_rate_uses_hook'] is True
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        os.close(db_fd)
        for path in (db_path, f'{db_path}-wal', f'{db_path}-shm'):
            if os.path.exists(path):
                os.unlink(path)


def test_qlinstance_to_dict_exposes_host_runtime():
    """Required so EditInstanceConfigModal can stamp a saved preset with the
    runtime of the host it was saved from."""
    from ui.models import QLInstance, InstanceStatus
    from ui.runtime import MINQLXTENDED
    app, db_fd, db_path = _make_app()
    try:
        with app.app_context():
            host = Host(
                name="runtime-serializer-test",
                provider="vultr",
                os_type="debian",
                ip_address="1.2.3.4",
                runtime=MINQLXTENDED,
            )
            db.session.add(host)
            db.session.commit()
            instance = QLInstance(
                host_id=host.id,
                name="i",
                port=27960,
                hostname="test-server",
                lan_rate_enabled=False,
                status=InstanceStatus.RUNNING,
            )
            db.session.add(instance)
            db.session.commit()
            d = instance.to_dict()
            assert d['host_runtime'] == MINQLXTENDED
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        os.close(db_fd)
        for path in (db_path, f'{db_path}-wal', f'{db_path}-shm'):
            if os.path.exists(path):
                os.unlink(path)


def test_qlinstance_to_dict_host_runtime_defaults_to_minqlx():
    """A host created before the runtime column existed must still report
    minqlx through the instance serializer."""
    from ui.models import QLInstance, InstanceStatus
    from ui.runtime import MINQLX
    app, db_fd, db_path = _make_app()
    try:
        with app.app_context():
            host = Host(
                name="legacy-runtime-serializer-test",
                provider="vultr",
                os_type="debian",
                ip_address="1.2.3.4",
            )
            db.session.add(host)
            db.session.commit()
            instance = QLInstance(
                host_id=host.id,
                name="i",
                port=27960,
                hostname="test-server",
                lan_rate_enabled=False,
                status=InstanceStatus.RUNNING,
            )
            db.session.add(instance)
            db.session.commit()
            d = instance.to_dict()
            assert d['host_runtime'] == MINQLX
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        os.close(db_fd)
        for path in (db_path, f'{db_path}-wal', f'{db_path}-shm'):
            if os.path.exists(path):
                os.unlink(path)
