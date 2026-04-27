"""Backfill qlfilter_status UNKNOWN -> NOT_INSTALLED for active hosts

QLFilter cannot be configured during host creation — it is only enabled
explicitly by the user after a host is set up. Any host with UNKNOWN
qlfilter_status that is ACTIVE was set up before this status was tracked
correctly; NOT_INSTALLED is the accurate state for those hosts.

Revision ID: 20260427000000
Revises: 20260424103000
Create Date: 2026-04-27
"""
from alembic import op
from sqlalchemy import text

revision = '20260427000000'
down_revision = '20260424103000'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(text(
        "UPDATE host SET qlfilter_status = 'NOT_INSTALLED'"
        " WHERE qlfilter_status = 'UNKNOWN' OR qlfilter_status IS NULL"
    ))


def downgrade():
    # Cannot recover original UNKNOWN/NULL values — this is intentional.
    pass
