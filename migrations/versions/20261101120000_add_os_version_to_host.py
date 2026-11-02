"""add os_version to host

Revision ID: 20261101120000
Revises: 20261015120000
Create Date: 2026-11-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261101120000'
down_revision = '20261015120000'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.add_column(sa.Column('os_version', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.drop_column('os_version')
