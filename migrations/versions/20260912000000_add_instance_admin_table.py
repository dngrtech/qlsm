"""add instance_admin table and import legacy access.txt levels

Revision ID: 20260912000000
Revises: 20260821010000
"""
import os
import re

import sqlalchemy as sa
from alembic import op

revision = '20260912000000'
down_revision = '20260821010000'
branch_labels = None
depends_on = None

# Kept local to the migration on purpose: it must keep parsing the format the
# files had on the day this ran, whatever ui/admin_permissions.py does later.
NUMERIC_LINE_RE = re.compile(r'^\s*(7656119\d{10})\s*\|\s*([0-5])\s*(#.*)?$')


def parse_numeric_admin_lines(text):
    """{steam_id: level} for QLSM's legacy "steamid|<0-5>" lines. Last wins."""
    entries = {}
    for line in (text or '').split('\n'):
        match = NUMERIC_LINE_RE.match(line)
        if match:
            entries[match.group(1)] = int(match.group(2))
    return entries


def import_existing_admins(connection, configs_root='configs'):
    """Copy legacy access.txt levels into instance_admin. Returns rows written.

    Best-effort on purpose: an unreadable access.txt is skipped, never fatal --
    aborting `flask db upgrade` over one file permission would block a deploy.
    The counts are printed so a skipped instance is visible in the upgrade
    output, and the UI carries the real safety: a SteamID in the managed-admins
    set with no row renders as "will be revoked on save" rather than vanishing.
    """
    rows = connection.execute(sa.text(
        'SELECT i.id AS instance_id, h.name AS host_name '
        'FROM ql_instance i JOIN host h ON h.id = i.host_id'
    )).fetchall()
    written = 0
    files_read = 0
    for row in rows:
        path = os.path.join(configs_root, row.host_name, str(row.instance_id), 'access.txt')
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            print(f'  instance_admin import: skipped unreadable {path}')
            continue
        files_read += 1
        for steam_id, level in parse_numeric_admin_lines(text).items():
            connection.execute(
                sa.text('INSERT INTO instance_admin (instance_id, steam_id64, level) '
                        'VALUES (:instance_id, :steam_id64, :level)'),
                {'instance_id': row.instance_id, 'steam_id64': steam_id, 'level': level},
            )
            written += 1
    print(f'  instance_admin import: {len(rows)} instance(s), {files_read} access.txt read, '
          f'{written} row(s) written')
    return written


def upgrade():
    op.create_table(
        'instance_admin',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('steam_id64', sa.String(length=20), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['instance_id'], ['ql_instance.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instance_id', 'steam_id64', name='uq_instance_admin_instance_steamid'),
    )
    op.create_index('ix_instance_admin_instance_id', 'instance_admin', ['instance_id'])
    import_existing_admins(op.get_bind())


def downgrade():
    op.drop_index('ix_instance_admin_instance_id', table_name='instance_admin')
    op.drop_table('instance_admin')
