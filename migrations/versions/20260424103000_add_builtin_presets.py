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
LEGACY_DEFAULT_DIR = os.path.join(PRESETS_DIR, 'default')
BUILTIN_DEFAULT_DIR = os.path.join(PRESETS_DIR, '_builtin', 'default')


def _migrate_default_folder():
    os.makedirs(os.path.dirname(BUILTIN_DEFAULT_DIR), exist_ok=True)
    if os.path.isdir(LEGACY_DEFAULT_DIR) and not os.path.exists(BUILTIN_DEFAULT_DIR):
        shutil.move(LEGACY_DEFAULT_DIR, BUILTIN_DEFAULT_DIR)


def upgrade():
    with op.batch_alter_table('config_preset', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'is_builtin',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('0'),
        ))

    _migrate_default_folder()

    conn = op.get_bind()
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
