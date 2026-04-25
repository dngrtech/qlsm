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


def test_migrate_default_folder_allows_already_migrated_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    migrated_default = tmp_path / 'configs' / 'presets' / '_builtin' / 'default'
    migrated_default.mkdir(parents=True)
    (migrated_default / 'server.cfg').write_text('set sv_hostname "builtin"\n')

    migration._migrate_default_folder()

    assert (migrated_default / 'server.cfg').read_text() == 'set sv_hostname "builtin"\n'


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


def test_restore_default_folder_moves_builtin_default_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    builtin_default = tmp_path / 'configs' / 'presets' / '_builtin' / 'default'
    builtin_default.mkdir(parents=True)
    (builtin_default / 'server.cfg').write_text('set sv_hostname "builtin"\n')

    migration._restore_default_folder()

    legacy_default = tmp_path / 'configs' / 'presets' / 'default' / 'server.cfg'
    assert not builtin_default.exists()
    assert legacy_default.read_text() == 'set sv_hostname "builtin"\n'


def test_migration_rejects_user_preset_named_internal_namespace():
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE config_preset (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100)
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO config_preset (name)
            VALUES ('_builtin')
        """))

        with pytest.raises(RuntimeError, match="user preset named '_builtin'"):
            migration._ensure_no_internal_namespace_collision(conn)


def test_default_row_markers_switch_between_builtin_and_legacy_paths():
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE config_preset (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100),
                path VARCHAR(255),
                is_builtin BOOLEAN NOT NULL DEFAULT 0
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO config_preset (name, path, is_builtin)
            VALUES ('default', 'configs/presets/default', 0)
        """))

        migration._mark_default_builtin(conn)
        row = conn.execute(sa.text("""
            SELECT path, is_builtin FROM config_preset WHERE name = 'default'
        """)).one()
        assert row.path == migration.BUILTIN_DEFAULT_DIR
        assert row.is_builtin in (1, True)

        migration._mark_default_legacy(conn)
        row = conn.execute(sa.text("""
            SELECT path, is_builtin FROM config_preset WHERE name = 'default'
        """)).one()
        assert row.path == migration.LEGACY_DEFAULT_DIR
