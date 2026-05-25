"""add lan_rate_uses_hook to host

Revision ID: ee8f7e103564
Revises: d4ddc1b30d85
Create Date: 2026-05-24 22:15:06.726275

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ee8f7e103564'
down_revision = 'd4ddc1b30d85'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'lan_rate_uses_hook',
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ))


def downgrade():
    with op.batch_alter_table('host', schema=None) as batch_op:
        batch_op.drop_column('lan_rate_uses_hook')
