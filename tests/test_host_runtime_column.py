"""Host.runtime is written once at creation and is immutable thereafter."""
import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import Host, HostStatus
from ui.runtime import MINQLX, MINQLXTENDED


def test_host_defaults_to_minqlx_when_runtime_not_given(app):
    """Every host created before this column existed, and every code path that
    forgets to pass a runtime, must land on minqlx."""
    with app.app_context():
        host = Host(name="legacy-host", provider="vultr", ip_address="10.0.0.1")
        db.session.add(host)
        db.session.commit()
        assert host.runtime == MINQLX


def test_host_stores_minqlxtended(app):
    with app.app_context():
        host = Host(name="tended-host", provider="vultr", runtime=MINQLXTENDED)
        db.session.add(host)
        db.session.commit()
        assert host.runtime == MINQLXTENDED


def test_to_dict_exposes_runtime(app):
    with app.app_context():
        host = Host(name="dict-host", provider="vultr", runtime=MINQLXTENDED)
        db.session.add(host)
        db.session.commit()
        assert host.to_dict()["runtime"] == MINQLXTENDED


def test_a_null_runtime_cannot_reach_the_database(app):
    """The column is NOT NULL with a server_default, so the 'NULL reads as
    minqlx' fallback in to_dict() is unreachable through the ORM. That is a
    stronger guarantee than the fallback itself: a host row can never be
    missing its runtime. The fallback stays for rows arriving from outside
    the ORM (a raw DB file from an older schema)."""
    import sqlalchemy.exc

    with app.app_context():
        host = Host(name="null-host", provider="vultr")
        db.session.add(host)
        db.session.commit()

        host.runtime = None
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_backup_export_includes_runtime(app):
    from ui.task_logic.backup_db_export import _host_row

    with app.app_context():
        host = Host(name="export-host", provider="vultr", runtime=MINQLXTENDED)
        db.session.add(host)
        db.session.commit()
        assert _host_row(host)["runtime"] == MINQLXTENDED


def test_backup_import_of_an_old_backup_lands_on_minqlx(app):
    """backup_db_import builds optional columns with row.get(name, default), so
    a backup taken before this column existed must restore as minqlx."""
    from ui.task_logic.backup_db_import import _host_from_row

    with app.app_context():
        host = _host_from_row({
            "id": 1, "name": "old-backup-host", "provider": "vultr",
            "status": HostStatus.ACTIVE.value,
        })
        assert host.runtime == MINQLX


def test_backup_import_round_trips_minqlxtended(app):
    from ui.task_logic.backup_db_import import _host_from_row

    with app.app_context():
        host = _host_from_row({
            "id": 2, "name": "new-backup-host", "provider": "vultr",
            "runtime": "minqlxtended", "status": HostStatus.ACTIVE.value,
        })
        assert host.runtime == MINQLXTENDED


def test_update_host_route_cannot_change_runtime(app, client):
    """The runtime lock is structural: PUT /api/hosts/<id> only handles 'name'.
    This test fails loudly if someone ever widens it."""
    with app.app_context():
        host = Host(name="locked-host", provider="vultr", runtime=MINQLX,
                    status=HostStatus.ACTIVE)
        db.session.add(host)
        db.session.commit()
        host_id = host.id
        token = create_access_token(identity="testuser")

    response = client.put(
        f"/api/hosts/{host_id}",
        json={"runtime": "minqlxtended"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400

    with app.app_context():
        assert db.session.get(Host, host_id).runtime == MINQLX


def test_update_host_name_leaves_runtime_alone(app, client):
    with app.app_context():
        host = Host(name="rename-me", provider="vultr", runtime=MINQLXTENDED,
                    status=HostStatus.ACTIVE)
        db.session.add(host)
        db.session.commit()
        host_id = host.id
        token = create_access_token(identity="testuser")

    client.put(
        f"/api/hosts/{host_id}",
        json={"name": "renamed", "runtime": "minqlx"},
        headers={"Authorization": f"Bearer {token}"},
    )

    with app.app_context():
        assert db.session.get(Host, host_id).runtime == MINQLXTENDED
