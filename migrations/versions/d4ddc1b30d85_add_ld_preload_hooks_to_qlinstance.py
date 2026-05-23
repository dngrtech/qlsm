"""add ld_preload_hooks to qlinstance

Revision ID: d4ddc1b30d85
Revises: 741ab13ff3a5
Create Date: 2026-05-22 20:30:07.434142

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4ddc1b30d85'
down_revision = '741ab13ff3a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ld_preload_hooks', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.drop_column('ld_preload_hooks')
