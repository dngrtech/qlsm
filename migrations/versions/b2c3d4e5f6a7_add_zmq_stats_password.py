"""add zmq_stats_password to QLInstance

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-08 21:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'  # After add_zmq_rcon_fields
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('zmq_stats_password', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.drop_column('zmq_stats_password')
