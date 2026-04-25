import importlib

import pytest
import sqlalchemy as sa


migration = importlib.import_module('migrations.versions.20260424103000_add_builtin_presets')


def test_migrate_default_folder_moves_legacy_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy_default = tmp_path / 'configs' / 'presets' / 'default'
    legacy_default.mkdir(parents=True)
    (legacy_default / 'server.cfg').write_text('set sv_hostname "legacy"\n')

    migration._migrate_default_folder()

    migrated = tmp_path / 'configs' / 'presets' / '_builtin' / 'default' / 'server.cfg'
    assert not legacy_default.exists()
    assert migrated.read_text() == 'set sv_hostname "legacy"\n'


def test_migrate_default_folder_rejects_nonempty_builtin_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy_default = tmp_path / 'configs' / 'presets' / 'default'
    legacy_default.mkdir(parents=True)
    (legacy_default / 'server.cfg').write_text('set sv_hostname "legacy"\n')
    builtin_root = tmp_path / 'configs' / 'presets' / '_builtin'
    builtin_root.mkdir()
    (builtin_root / 'user-file.txt').write_text('do not mix')

    with pytest.raises(RuntimeError, match='already exists and is not empty'):
        migration._migrate_default_folder()

    assert legacy_default.exists()
    assert (builtin_root / 'user-file.txt').exists()


def test_migration_rejects_user_preset_named_internal_namespace():
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE config_preset (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100),
                is_builtin BOOLEAN NOT NULL DEFAULT 0
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO config_preset (name, is_builtin)
            VALUES ('_builtin', 0)
        """))

        with pytest.raises(RuntimeError, match="user preset named '_builtin'"):
            migration._ensure_no_internal_namespace_collision(conn)
