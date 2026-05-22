"""add redis_unix_socket to host

Revision ID: 741ab13ff3a5
Revises: 20260502000000
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa

revision = '741ab13ff3a5'
down_revision = '20260502000000'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('host') as batch_op:
        batch_op.add_column(
            sa.Column('redis_unix_socket', sa.Boolean(), nullable=False, server_default='0')
        )


def downgrade():
    with op.batch_alter_table('host') as batch_op:
        batch_op.drop_column('redis_unix_socket')
