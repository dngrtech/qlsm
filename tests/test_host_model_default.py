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
        os.close(db_fd)
        os.unlink(db_path)


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
        os.close(db_fd)
        os.unlink(db_path)
