"""pending_instance_change.synced

A deferred change is staged first and shown only once its sync reached the
host. Existing rows were recorded after their sync, so they default to true.

Revision ID: 20261125120000
Revises: 20261120120000
Create Date: 2026-11-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261125120000'
down_revision = '20261120120000'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pending_instance_change', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('synced', sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade():
    with op.batch_alter_table('pending_instance_change', schema=None) as batch_op:
        batch_op.drop_column('synced')
