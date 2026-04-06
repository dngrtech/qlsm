"""add_password_change_required_to_user

Revision ID: c1f4e5a6b7c8
Revises: 7cf046f62e03
Create Date: 2026-03-15 17:19:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1f4e5a6b7c8'
down_revision = '7cf046f62e03'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'password_change_required',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('0')
        ))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('password_change_required')
