"""add builtin presets

Revision ID: 20260424103000
Revises: c1f4e5a6b7c8
Create Date: 2026-04-24 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
import os
import shutil


# revision identifiers, used by Alembic.
revision = '20260424103000'
down_revision = 'c1f4e5a6b7c8'
branch_labels = None
depends_on = None


PRESETS_DIR = os.path.join('configs', 'presets')
BUILTIN_PRESETS_DIR = os.path.join(PRESETS_DIR, '_builtin')
LEGACY_DEFAULT_DIR = os.path.join(PRESETS_DIR, 'default')
BUILTIN_DEFAULT_DIR = os.path.join(BUILTIN_PRESETS_DIR, 'default')


def _migrate_default_folder():
    if os.path.isdir(LEGACY_DEFAULT_DIR) and os.path.exists(BUILTIN_DEFAULT_DIR):
        raise RuntimeError(
            "Cannot migrate default preset: both configs/presets/default and "
            "configs/presets/_builtin/default exist. Preserve the legacy default "
            "folder manually, remove the conflicting destination, then rerun migrations."
        )
    if os.path.isdir(LEGACY_DEFAULT_DIR) and os.path.isdir(BUILTIN_PRESETS_DIR):
        existing_entries = os.listdir(BUILTIN_PRESETS_DIR)
        if existing_entries:
            raise RuntimeError(
                "Cannot migrate default preset: configs/presets/_builtin already "
                "exists and is not empty. Rename the existing _builtin user preset "
                "folder, then rerun migrations."
            )
    os.makedirs(BUILTIN_PRESETS_DIR, exist_ok=True)
    if os.path.isdir(LEGACY_DEFAULT_DIR) and not os.path.exists(BUILTIN_DEFAULT_DIR):
        shutil.move(LEGACY_DEFAULT_DIR, BUILTIN_DEFAULT_DIR)


def _ensure_no_internal_namespace_collision(conn):
    existing = conn.execute(
        sa.text("""
            SELECT id FROM config_preset
            WHERE lower(name) = '_builtin' AND is_builtin = 0
            LIMIT 1
        """)
    ).first()
    if existing:
        raise RuntimeError(
            "Cannot migrate built-in presets: a user preset named '_builtin' "
            "already exists. Rename or delete that preset before running migrations."
        )


def upgrade():
    with op.batch_alter_table('config_preset', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'is_builtin',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('0'),
        ))

    conn = op.get_bind()
    _ensure_no_internal_namespace_collision(conn)
    _migrate_default_folder()

    conn.execute(
        sa.text("""
            UPDATE config_preset
            SET path = :path, is_builtin = 1
            WHERE name = 'default'
        """),
        {'path': BUILTIN_DEFAULT_DIR},
    )


def downgrade():
    with op.batch_alter_table('config_preset', schema=None) as batch_op:
        batch_op.drop_column('is_builtin')
