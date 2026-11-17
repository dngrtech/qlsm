"""add host_runtime_upgrade_operation

Revision ID: 20261104120000
Revises: 20261101120000
Create Date: 2026-11-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20261104120000'
down_revision = '20261101120000'
branch_labels = None
depends_on = None

# Literal copy of ui.models_runtime_upgrade.ACTIVE_OPERATION_WHERE: a migration
# must not change meaning when the model module changes later.
ACTIVE_OPERATION_WHERE = "state NOT IN ('succeeded', 'rolled_back', 'failed_preparation')"


def upgrade():
    op.create_table(
        'host_runtime_upgrade_operation',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('host_id', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False),
        sa.Column('phase', sa.String(length=64), nullable=True),
        sa.Column('inputs_json', sa.Text(), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=True),
        sa.Column('answers_json', sa.Text(), nullable=True),
        sa.Column('original_runtime', sa.String(length=20), nullable=True),
        sa.Column('original_host_status', sa.String(length=32), nullable=True),
        sa.Column('original_instance_states_json', sa.Text(), nullable=True),
        sa.Column('snapshot_path', sa.String(length=500), nullable=True),
        sa.Column('snapshot_complete', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('instance_outcomes_json', sa.Text(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('rq_job_id', sa.String(length=64), nullable=True),
        sa.Column('fencing_token', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recovery_required', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_host_runtime_upgrade_operation_host_id',
                    'host_runtime_upgrade_operation', ['host_id'], unique=False)
    op.create_index('uq_runtime_upgrade_active_host',
                    'host_runtime_upgrade_operation', ['host_id'], unique=True,
                    sqlite_where=sa.text(ACTIVE_OPERATION_WHERE))


def downgrade():
    op.drop_index('uq_runtime_upgrade_active_host', table_name='host_runtime_upgrade_operation')
    op.drop_index('ix_host_runtime_upgrade_operation_host_id',
                  table_name='host_runtime_upgrade_operation')
    op.drop_table('host_runtime_upgrade_operation')
