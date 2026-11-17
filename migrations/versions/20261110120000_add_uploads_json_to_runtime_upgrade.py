"""add uploads_json to host_runtime_upgrade_operation

Revision ID: 20261110120000
Revises: 20261104140000
Create Date: 2026-11-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261110120000'
down_revision = '20261104140000'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('host_runtime_upgrade_operation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uploads_json', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('host_runtime_upgrade_operation', schema=None) as batch_op:
        batch_op.drop_column('uploads_json')
