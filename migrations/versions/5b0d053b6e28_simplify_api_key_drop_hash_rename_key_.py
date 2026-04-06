"""simplify api_key drop hash rename key_plain to key

Revision ID: 5b0d053b6e28
Revises: 6e6df04af542
Create Date: 2026-02-25 15:32:45.791112

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5b0d053b6e28'
down_revision = '6e6df04af542'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite doesn't support ALTER COLUMN well, so use batch mode to
    # recreate the table. Only the api_key table is affected.
    with op.batch_alter_table('api_key', schema=None) as batch_op:
        batch_op.add_column(sa.Column('key', sa.String(length=64), nullable=False, server_default=''))
        batch_op.create_unique_constraint('uq_api_key_key', ['key'])
        batch_op.drop_column('key_hash')
        batch_op.drop_column('key_plain')


def downgrade():
    with op.batch_alter_table('api_key', schema=None) as batch_op:
        batch_op.add_column(sa.Column('key_plain', sa.VARCHAR(length=64), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('key_hash', sa.VARCHAR(length=256), nullable=False, server_default=''))
        batch_op.drop_constraint('uq_api_key_key', type_='unique')
        batch_op.drop_column('key')
