"""convert_ssh_key_paths_to_relative

Converts absolute ssh_key_path values in the host table to paths relative to
the project root (e.g. "terraform/ssh-keys/my-host_id_rsa").

This makes the stored path portable across deployment environments:
  - Bare metal at /opt/qlds-ui/ → resolved by os.path.abspath() at runtime
  - Docker at /app/             → resolved by os.path.abspath() at runtime

The migration is safe to run on fresh installs (no rows → no-op) and on
existing installs (strips the absolute prefix, leaving a relative path).

Downgrade restores the previous absolute path using the configured project root
at the time the downgrade runs (which is also runtime-correct).

Revision ID: 7cf046f62e03
Revises: f615fefa2f2e
Create Date: 2026-03-09 18:49:16.641304
"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '7cf046f62e03'
down_revision = 'f615fefa2f2e'
branch_labels = None
depends_on = None

# Determine project root at migration time.
# migrations/versions/this_file.py → ../../ == project root
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..'))


def upgrade():
    """Convert absolute ssh_key_path values to relative paths."""
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, ssh_key_path FROM host WHERE ssh_key_path IS NOT NULL")).fetchall()
    for row in rows:
        host_id, path = row[0], row[1]
        if path and os.path.isabs(path):
            try:
                relative = os.path.relpath(path, _PROJECT_ROOT)
                conn.execute(
                    text("UPDATE host SET ssh_key_path = :p WHERE id = :id"),
                    {"p": relative, "id": host_id}
                )
            except ValueError:
                # relpath raises ValueError on Windows for cross-drive paths; leave as-is
                pass


def downgrade():
    """Restore relative ssh_key_path values back to absolute paths."""
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, ssh_key_path FROM host WHERE ssh_key_path IS NOT NULL")).fetchall()
    for row in rows:
        host_id, path = row[0], row[1]
        if path and not os.path.isabs(path):
            absolute = os.path.normpath(os.path.join(_PROJECT_ROOT, path))
            conn.execute(
                text("UPDATE host SET ssh_key_path = :p WHERE id = :id"),
                {"p": absolute, "id": host_id}
            )
