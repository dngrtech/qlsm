"""add cpu affinity fields

Revision ID: 20260430000000
Revises: c940478a96df
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa


revision = '20260430000000'
down_revision = 'c940478a96df'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpu_count', sa.Integer(), nullable=True))
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpu_affinity', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('ql_instance', schema=None) as batch_op:
        batch_op.drop_column('cpu_affinity')
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.drop_column('cpu_count')
