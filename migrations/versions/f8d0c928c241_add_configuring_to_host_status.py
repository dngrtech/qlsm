"""add_configuring_to_host_status

Revision ID: f8d0c928c241
Revises: 250d60ffff75
Create Date: 2026-03-04 10:43:38.410146

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8d0c928c241'
down_revision = '250d60ffff75'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite stores enums as VARCHAR — no schema change needed.
    # This migration documents the addition of CONFIGURING to HostStatus.
    pass


def downgrade():
    pass
