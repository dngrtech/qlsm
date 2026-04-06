import pytest
from ui import create_app, db
from sqlalchemy import text

def test_sqlite_wal_mode_enabled(tmp_path):
    """WAL journal mode must be set on SQLite connections."""
    db_path = tmp_path / "test.db"
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
    })
    with app.app_context():
        db.create_all()
        result = db.session.execute(text("PRAGMA journal_mode")).scalar()
        assert result == 'wal', f"Expected 'wal', got '{result}'"

def test_sqlite_busy_timeout_set(tmp_path):
    """busy_timeout must be set to 5000ms on SQLite connections."""
    db_path = tmp_path / "test.db"
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
    })
    with app.app_context():
        db.create_all()
        result = db.session.execute(text("PRAGMA busy_timeout")).scalar()
        assert result == 5000, f"Expected 5000, got {result}"
