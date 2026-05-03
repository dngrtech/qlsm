"""hostname_max_64

Revision ID: 20260502000000
Revises: 20260430000000
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa


revision = '20260502000000'
down_revision = '20260430000000'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import text
    conn = op.get_bind()
    long_rows = conn.execute(
        text("SELECT id, hostname FROM ql_instance WHERE length(hostname) > 64")
    ).fetchall()
    if long_rows:
        raise RuntimeError(
            f"Cannot migrate: {len(long_rows)} row(s) have hostname > 64 chars. "
            "Truncate or update them before running this migration."
        )
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.alter_column('hostname',
               existing_type=sa.VARCHAR(length=255),
               type_=sa.String(length=64),
               existing_nullable=False)


def downgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.alter_column('hostname',
               existing_type=sa.String(length=64),
               type_=sa.VARCHAR(length=255),
               existing_nullable=False)
