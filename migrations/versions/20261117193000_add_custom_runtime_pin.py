"""Pin Custom host runtime releases."""

import sqlalchemy as sa
from alembic import op

revision = '20261117193000'
down_revision = '20261110120000'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('host', sa.Column('runtime_provider_id', sa.String(80), nullable=True))
    op.add_column('host', sa.Column('runtime_release_sha256', sa.String(64), nullable=True))
    op.add_column('host', sa.Column('runtime_plugin_api', sa.String(20), nullable=True))


def downgrade():
    with op.batch_alter_table('host') as host:
        host.drop_column('runtime_plugin_api')
        host.drop_column('runtime_release_sha256')
        host.drop_column('runtime_provider_id')
