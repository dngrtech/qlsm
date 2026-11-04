"""add python_deps_path to qlinstance

Revision ID: 20261104130000
Revises: 20261104120000
Create Date: 2026-11-04 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261104130000'
down_revision = '20261104120000'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('python_deps_path', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.drop_column('python_deps_path')
