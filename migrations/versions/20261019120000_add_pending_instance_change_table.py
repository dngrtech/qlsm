"""add pending_instance_change table

Changes synced to an instance without a restart, shown in the
"Updated" badge's popup and cleared when the instance restarts.

Revision ID: 20261019120000
Revises: 20260918030000
Create Date: 2026-10-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261019120000'
down_revision = '20260918030000'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pending_instance_change',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('changes_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['instance_id'], ['ql_instance.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pending_instance_change', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_pending_instance_change_instance_id'), ['instance_id'], unique=False
        )


def downgrade():
    with op.batch_alter_table('pending_instance_change', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pending_instance_change_instance_id'))
    op.drop_table('pending_instance_change')
