"""add runtime to config_preset

Revision ID: 20260818000001
Revises: 20260818000000
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa


revision = "20260818000001"
down_revision = "20260818000000"
branch_labels = None
depends_on = None


def upgrade():
    # server_default backfills every existing preset row to 'minqlx' in the
    # same statement, which is correct: minqlx is the only runtime any
    # existing preset could have been saved from.
    with op.batch_alter_table("config_preset", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "runtime",
                sa.String(length=20),
                server_default="minqlx",
                nullable=False,
            )
        )


def downgrade():
    # Symmetric with the Host.runtime downgrade guard: a dropped column would
    # re-backfill to 'minqlx' on the next upgrade, silently losing a preset's
    # recorded runtime. Losing preset provenance isn't destructive the way
    # losing Host.runtime is, but guarding both the same way is cheap and
    # avoids a half-guarded pair implying the other one is safe to skip.
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM config_preset WHERE runtime != 'minqlx'")
    ).scalar()
    if count:
        raise RuntimeError(
            f"{count} preset(s) are recorded against a non-minqlx runtime. "
            "Dropping ConfigPreset.runtime would silently reset them to minqlx. "
            "Delete or recreate those presets before downgrading."
        )
    with op.batch_alter_table("config_preset", schema=None) as batch_op:
        batch_op.drop_column("runtime")
