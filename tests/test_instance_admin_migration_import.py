import importlib.util
import os

import sqlalchemy as sa

MIGRATION = os.path.join(
    'migrations', 'versions', '20260912000000_add_instance_admin_table.py'
)


def _load():
    spec = importlib.util.spec_from_file_location('mig_instance_admin', MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parses_only_numeric_levels():
    module = _load()
    parsed = module.parse_numeric_admin_lines(
        "# comment\n"
        "76561198012345678|3\n"
        "76561198087654321|admin\n"
        "76561199580544522|mod\n"
        "76561198111111111|9\n"
        "76561198222222222|2 # trailing\n"
        "junk\n"
    )
    assert parsed == {"76561198012345678": 3, "76561198222222222": 2}


def test_imports_rows_for_each_instance(tmp_path):
    module = _load()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE host (id INTEGER PRIMARY KEY, name TEXT)'))
        conn.execute(sa.text('CREATE TABLE ql_instance (id INTEGER PRIMARY KEY, host_id INTEGER)'))
        conn.execute(sa.text(
            'CREATE TABLE instance_admin (id INTEGER PRIMARY KEY, instance_id INTEGER, '
            'steam_id64 TEXT, level INTEGER, created_at DATETIME)'
        ))
        conn.execute(sa.text("INSERT INTO host (id, name) VALUES (1, 'host-a')"))
        conn.execute(sa.text('INSERT INTO ql_instance (id, host_id) VALUES (7, 1)'))

        config_dir = tmp_path / 'host-a' / '7'
        config_dir.mkdir(parents=True)
        (config_dir / 'access.txt').write_text(
            "76561198012345678|3\n76561198087654321|admin\n", encoding='utf-8'
        )

        written = module.import_existing_admins(conn, configs_root=str(tmp_path))
        assert written == 1
        rows = conn.execute(sa.text('SELECT steam_id64, level FROM instance_admin')).fetchall()
        assert [(r[0], r[1]) for r in rows] == [('76561198012345678', 3)]


def test_missing_access_txt_is_skipped_but_reported(tmp_path, capsys):
    """Best-effort, never fatal -- but the skip has to be visible in the upgrade
    output, otherwise an instance silently loses its admins."""
    module = _load()
    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE host (id INTEGER PRIMARY KEY, name TEXT)'))
        conn.execute(sa.text('CREATE TABLE ql_instance (id INTEGER PRIMARY KEY, host_id INTEGER)'))
        conn.execute(sa.text(
            'CREATE TABLE instance_admin (id INTEGER PRIMARY KEY, instance_id INTEGER, '
            'steam_id64 TEXT, level INTEGER, created_at DATETIME)'
        ))
        conn.execute(sa.text("INSERT INTO host (id, name) VALUES (1, 'gone')"))
        conn.execute(sa.text('INSERT INTO ql_instance (id, host_id) VALUES (3, 1)'))
        assert module.import_existing_admins(conn, configs_root=str(tmp_path)) == 0

    output = capsys.readouterr().out
    assert 'skipped unreadable' in output
    assert '1 instance(s), 0 access.txt read, 0 row(s) written' in output
