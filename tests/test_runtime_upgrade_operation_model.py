"""HostRuntimeUpgradeOperation: columns, defaults and the one-active-operation rule."""
import os
import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from ui import create_app, db
from ui.models import Host, HostStatus
from ui.models_runtime_upgrade import (
    ACTIVE_OPERATION_INDEX,
    NONTERMINAL_STATES,
    TERMINAL_STATES,
    HostRuntimeUpgradeOperation,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _host(name='h1'):
    host = Host(name=name, provider='vultr', status=HostStatus.ACTIVE)
    db.session.add(host)
    db.session.commit()
    return host


def _op(host, state='preparing', **fields):
    op = HostRuntimeUpgradeOperation(host_id=host.id, state=state, **fields)
    db.session.add(op)
    db.session.commit()
    return op


def test_defaults(app):
    with app.app_context():
        op = _op(_host())
        assert len(op.id) == 32 and int(op.id, 16) >= 0
        assert op.snapshot_complete is False
        assert op.recovery_required is False
        assert op.fencing_token == 0
        assert op.created_at is not None and op.updated_at is not None
        assert op.is_terminal is False


def test_every_orchestrator_column_exists(app):
    expected = {
        'id', 'host_id', 'state', 'phase', 'inputs_json', 'fingerprint', 'answers_json',
        'original_runtime', 'original_host_status', 'original_instance_states_json',
        'snapshot_path', 'snapshot_complete', 'instance_outcomes_json', 'last_error',
        'rq_job_id', 'fencing_token', 'recovery_required', 'created_at', 'updated_at',
    }
    assert expected <= set(HostRuntimeUpgradeOperation.__table__.columns.keys())


def test_invalid_state_rejected(app):
    with app.app_context():
        with pytest.raises(ValueError):
            HostRuntimeUpgradeOperation(host_id=1, state='bogus')


@pytest.mark.parametrize('first', NONTERMINAL_STATES)
def test_second_nonterminal_operation_for_host_rejected(app, first):
    with app.app_context():
        host = _host()
        _op(host, state=first)
        with pytest.raises(IntegrityError):
            _op(host, state='preparing')
        db.session.rollback()


def test_terminal_operations_do_not_block(app):
    with app.app_context():
        host = _host()
        for state in TERMINAL_STATES:
            _op(host, state=state)
        _op(host, state='preparing')
        assert HostRuntimeUpgradeOperation.query.filter_by(host_id=host.id).count() == 4


def test_finishing_an_operation_releases_the_host(app):
    with app.app_context():
        host = _host()
        first = _op(host, state='converting')
        first.state = 'rolled_back'
        db.session.commit()
        _op(host, state='preparing')


def test_other_hosts_are_independent(app):
    with app.app_context():
        _op(_host('a'), state='installing')
        _op(_host('b'), state='installing')


def test_migration_creates_table_and_partial_index(tmp_path):
    """Applies only this migration: the oldest revisions assume `flask init-db`
    tables, so the chain cannot run from an empty database."""
    from flask_migrate import stamp, upgrade

    db_path = tmp_path / 'migrated.db'
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'RCON_ENABLED': False,
    })
    migrations = os.path.join(REPO_ROOT, 'migrations')
    try:
        with app.app_context():
            db.create_all()
            HostRuntimeUpgradeOperation.__table__.drop(db.engine)
            stamp(directory=migrations, revision='20261101120000')
            upgrade(directory=migrations, revision='20261104120000')
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    conn = sqlite3.connect(db_path)
    try:
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (ACTIVE_OPERATION_INDEX,)).fetchone()[0]
        assert 'UNIQUE' in sql.upper() and 'WHERE' in sql.upper()
        conn.execute("INSERT INTO host (name, provider, status, runtime, ssh_port, is_standalone) "
                     "VALUES ('h', 'vultr', 'ACTIVE', 'minqlx', 22, 0)")
        insert = ("INSERT INTO host_runtime_upgrade_operation "
                  "(id, host_id, state, created_at, updated_at) "
                  "VALUES (?, 1, ?, '2026-11-04', '2026-11-04')")
        conn.execute(insert, ('a' * 32, 'rolled_back'))
        conn.execute(insert, ('b' * 32, 'preparing'))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ('c' * 32, 'recovery_required'))
        row = conn.execute("SELECT snapshot_complete, fencing_token, recovery_required "
                           "FROM host_runtime_upgrade_operation WHERE id=?",
                           ('b' * 32,)).fetchone()
        assert row == (0, 0, 0)
    finally:
        conn.close()
