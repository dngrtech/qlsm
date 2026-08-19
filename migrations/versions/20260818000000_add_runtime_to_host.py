"""add runtime to host

Revision ID: 20260818000000
Revises: 20260810000000
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa


revision = "20260818000000"
down_revision = "20260810000000"
branch_labels = None
depends_on = None


def upgrade():
    # server_default backfills every existing row to 'minqlx' in the same
    # statement, which is correct: minqlx is the only runtime that has ever
    # been deployed.
    with op.batch_alter_table("host", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "runtime",
                sa.String(length=20),
                server_default="minqlx",
                nullable=False,
            )
        )


def downgrade():
    with op.batch_alter_table("host", schema=None) as batch_op:
        batch_op.drop_column("runtime")
