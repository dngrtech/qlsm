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
    # Dropping the column re-upgrades every row to 'minqlx' via the
    # server_default on the next upgrade. A host actually running a
    # non-minqlx runtime would then read back as minqlx, and the next
    # terraform apply -- including a routine resize -- would reinstall its
    # OS to match. Refuse instead of silently corrupting that host.
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM host WHERE runtime != 'minqlx'")
    ).scalar()
    if count:
        raise RuntimeError(
            f"{count} host(s) run a non-minqlx runtime. Dropping Host.runtime would "
            "silently reset them to minqlx, and the next terraform apply would "
            "reinstall their OS. Delete or recreate those hosts before downgrading."
        )
    with op.batch_alter_table("host", schema=None) as batch_op:
        batch_op.drop_column("runtime")
