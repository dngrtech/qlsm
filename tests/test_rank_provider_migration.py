"""The migration must exist and must match the model.

tests/conftest.py builds its schema with db.create_all(), so every other test in
this repo passes whether or not a migration exists. Production runs
`flask db upgrade`. Without this test a missing migration ships green and the
deployed app raises `no such table: rank_provider_config` on first use.
"""
import sqlalchemy as sa

from ui import db
from ui.models import RankProviderConfig


def test_model_table_name_and_columns():
    table = RankProviderConfig.__table__
    assert table.name == 'rank_provider_config'
    assert set(table.columns.keys()) == {
        'id', 'instance_id', 'provider_type', 'base_url', 'api_key',
        'game_type', 'extra', 'enabled', 'created_at', 'last_updated',
    }


def test_instance_id_is_unique_and_cascades():
    column = RankProviderConfig.__table__.columns['instance_id']
    assert column.nullable is False
    fk = list(column.foreign_keys)[0]
    assert fk.ondelete == 'CASCADE'
    assert column.unique or any(
        isinstance(c, sa.UniqueConstraint) and list(c.columns) == [column]
        for c in RankProviderConfig.__table__.constraints
    )


def test_migration_creates_and_drops_the_table(app):
    """Exactly one revision, up and back down.

    Scoped on purpose. `command.upgrade(cfg, 'head')` against a dropped schema
    replays the whole chain from the root, and three of those revisions do real
    work outside the database — 20260120120110_migrate_presets_to_filesystem,
    20260424103000_add_builtin_presets and
    7cf046f62e03_convert_ssh_key_paths_to_relative all touch `configs/` on disk.
    That makes a unit test slow and couples it to the working directory's
    configs/ tree for no extra signal. `flask db heads` in Step 7 already covers
    the "is the chain branched" question.

    Stamping first means this test no longer proves the chain is unbroken. That
    is deliberate: the full chain belongs in a deploy, not here.
    """
    import os

    from alembic import command
    from alembic.config import Config

    # Resolve from __file__, not the cwd: Config('migrations/alembic.ini')
    # only works when pytest happens to run from the repo root.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    migrations_dir = os.path.join(repo_root, 'migrations')

    with app.app_context():
        # conftest.py already built the whole schema with db.create_all(), which
        # includes rank_provider_config. Drop just that one table so the new
        # revision has something to do.
        RankProviderConfig.__table__.drop(db.engine, checkfirst=True)

        cfg = Config(os.path.join(migrations_dir, 'alembic.ini'))
        cfg.set_main_option('script_location', migrations_dir)
        # No sqlalchemy.url here on purpose: migrations/env.py:39 overwrites it
        # with get_engine_url() from the Flask app's engine, so setting it is a
        # no-op that implies a control this test does not have.

        # The schema now matches 20260918030000. Stamp it so `upgrade` runs the
        # one new revision instead of replaying the chain from the root.
        command.stamp(cfg, '20260918030000')

        command.upgrade(cfg, '20260920120000')
        inspector = sa.inspect(db.engine)
        assert 'rank_provider_config' in inspector.get_table_names()

        command.downgrade(cfg, '20260918030000')
        inspector = sa.inspect(db.engine)
        assert 'rank_provider_config' not in inspector.get_table_names()
