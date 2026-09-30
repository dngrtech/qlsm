"""add rank_provider_config

Revision ID: 20260920120000
Revises: 20260918030000
Create Date: 2026-09-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260920120000'
down_revision = '20260918030000'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rank_provider_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('provider_type', sa.String(length=32), nullable=False),
        sa.Column('base_url', sa.String(length=255), nullable=True),
        sa.Column('api_key', sa.String(length=255), nullable=True),
        sa.Column('game_type', sa.String(length=16), nullable=True),
        sa.Column('extra', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['instance_id'], ['ql_instance.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instance_id'),
    )


def downgrade():
    op.drop_table('rank_provider_config')
