"""add runtime_deps_isolated to host

Revision ID: 20261104140000
Revises: 20261104130000
Create Date: 2026-11-04 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261104140000'
down_revision = '20261104130000'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.add_column(sa.Column('runtime_deps_isolated', sa.Boolean(), nullable=False,
                                      server_default='0'))


def downgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.drop_column('runtime_deps_isolated')
