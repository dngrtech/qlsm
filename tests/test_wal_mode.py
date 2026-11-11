import pytest
from ui import create_app, db
from sqlalchemy import text

def test_sqlite_wal_mode_enabled(tmp_path):
    """WAL journal mode must be set on SQLite connections."""
    db_path = tmp_path / "test.db"
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        result = db.session.execute(text("PRAGMA journal_mode")).scalar()
        assert result == 'wal', f"Expected 'wal', got '{result}'"

def _journal_mode(tmp_path):
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "test.db"}',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        return db.session.execute(text("PRAGMA journal_mode")).scalar()

def test_sqlite_journal_mode_override(tmp_path, monkeypatch):
    """SQLITE_JOURNAL_MODE selects another journal mode, for filesystems where
    WAL's shared memory does not work across processes (WSL1, network mounts)."""
    monkeypatch.setenv('SQLITE_JOURNAL_MODE', 'delete')
    assert _journal_mode(tmp_path) == 'delete'

def test_sqlite_journal_mode_unknown_value_falls_back_to_wal(tmp_path, monkeypatch):
    """An unsupported value is never spliced into the PRAGMA; WAL stays."""
    monkeypatch.setenv('SQLITE_JOURNAL_MODE', 'off; DROP TABLE user')
    assert _journal_mode(tmp_path) == 'wal'

def test_sqlite_busy_timeout_set(tmp_path):
    """busy_timeout must be set to 30000ms on SQLite connections."""
    db_path = tmp_path / "test.db"
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        result = db.session.execute(text("PRAGMA busy_timeout")).scalar()
        assert result == 30000, f"Expected 30000, got {result}"
