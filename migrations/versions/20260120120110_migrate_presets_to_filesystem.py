"""Migrate presets to filesystem storage

This migration:
1. Creates /configs/presets/ directory
2. Copies /configs/default/ contents to /configs/presets/default/
3. For each existing DB preset, creates folder and writes config files
4. Adds `path` column to config_preset table
5. Populates path values
6. Drops old content columns (server_cfg, mappool, access, workshop, factory)

Revision ID: 20260120120110
Revises: 4253d4fa556f
Create Date: 2026-01-20 12:01:10.000000

"""
from alembic import op
import sqlalchemy as sa
import os
import shutil


# revision identifiers, used by Alembic.
revision = '20260120120110'
down_revision = '4253d4fa556f'
branch_labels = None
depends_on = None

# Base path for configs (relative to project root)
CONFIGS_DIR = 'configs'
PRESETS_DIR = os.path.join(CONFIGS_DIR, 'presets')
DEFAULT_SOURCE_DIR = os.path.join(CONFIGS_DIR, 'default')
DEFAULT_PRESET_DIR = os.path.join(PRESETS_DIR, 'default')

# Config file mapping: DB column name -> filename
CONFIG_FILE_MAP = {
    'server_cfg': 'server.cfg',
    'mappool': 'mappool.txt',
    'access': 'access.txt',
    'workshop': 'workshop.txt',
    'factory': 'factory.factories'
}


def upgrade():
    # Step 1: Create presets directory
    os.makedirs(PRESETS_DIR, exist_ok=True)
    print(f"Created presets directory: {PRESETS_DIR}")

    # Step 2: Copy default configs to presets/default/
    if os.path.exists(DEFAULT_SOURCE_DIR):
        if os.path.exists(DEFAULT_PRESET_DIR):
            shutil.rmtree(DEFAULT_PRESET_DIR)
        shutil.copytree(DEFAULT_SOURCE_DIR, DEFAULT_PRESET_DIR)
        print(f"Copied default configs to: {DEFAULT_PRESET_DIR}")
    else:
        # Create empty default preset folder if source doesn't exist
        os.makedirs(DEFAULT_PRESET_DIR, exist_ok=True)
        print(f"Warning: Default source dir not found, created empty: {DEFAULT_PRESET_DIR}")

    # Step 3: Add path column (nullable initially for migration)
    with op.batch_alter_table('config_preset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('path', sa.String(255), nullable=True))

    # Step 4: Migrate existing presets from DB to filesystem
    # Use raw SQL to read existing data before dropping columns
    conn = op.get_bind()

    # Check if old columns exist before trying to read them
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('config_preset')]

    if 'server_cfg' in columns:
        # Read all existing presets
        presets = conn.execute(sa.text(
            "SELECT id, name, server_cfg, mappool, access, workshop, factory FROM config_preset"
        )).fetchall()

        for preset in presets:
            preset_id, name, server_cfg, mappool, access, workshop, factory = preset

            # Create preset folder
            preset_path = os.path.join(PRESETS_DIR, name)
            os.makedirs(preset_path, exist_ok=True)

            # Write config files
            content_map = {
                'server.cfg': server_cfg,
                'mappool.txt': mappool,
                'access.txt': access,
                'workshop.txt': workshop,
                'factory.factories': factory
            }

            for filename, content in content_map.items():
                if content:
                    filepath = os.path.join(preset_path, filename)
                    with open(filepath, 'w') as f:
                        f.write(content)

            # Update path column
            conn.execute(
                sa.text("UPDATE config_preset SET path = :path WHERE id = :id"),
                {"path": preset_path, "id": preset_id}
            )
            print(f"Migrated preset '{name}' to: {preset_path}")

        # Step 5: Drop old content columns
        with op.batch_alter_table('config_preset', schema=None) as batch_op:
            batch_op.drop_column('server_cfg')
            batch_op.drop_column('mappool')
            batch_op.drop_column('access')
            batch_op.drop_column('workshop')
            batch_op.drop_column('factory')

    # Step 6: Make path column non-nullable
    with op.batch_alter_table('config_preset', schema=None) as batch_op:
        batch_op.alter_column('path', nullable=False)

    print("Migration complete: Presets migrated to filesystem storage")


def downgrade():
    # Add back the content columns
    with op.batch_alter_table('config_preset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('server_cfg', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('mappool', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('access', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('workshop', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('factory', sa.Text(), nullable=True))

    # Read content from filesystem and restore to DB
    conn = op.get_bind()
    presets = conn.execute(sa.text("SELECT id, name, path FROM config_preset")).fetchall()

    for preset in presets:
        preset_id, name, preset_path = preset

        content_values = {}
        file_map = {
            'server_cfg': 'server.cfg',
            'mappool': 'mappool.txt',
            'access': 'access.txt',
            'workshop': 'workshop.txt',
            'factory': 'factory.factories'
        }

        for db_col, filename in file_map.items():
            filepath = os.path.join(preset_path, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    content_values[db_col] = f.read()
            else:
                content_values[db_col] = None

        conn.execute(
            sa.text("""
                UPDATE config_preset
                SET server_cfg = :server_cfg, mappool = :mappool, access = :access,
                    workshop = :workshop, factory = :factory
                WHERE id = :id
            """),
            {**content_values, "id": preset_id}
        )
        print(f"Restored preset '{name}' content to database")

    # Drop path column
    with op.batch_alter_table('config_preset', schema=None) as batch_op:
        batch_op.drop_column('path')

    # Note: Filesystem folders are intentionally NOT deleted on downgrade
    # to prevent data loss. Manual cleanup may be required.
    print("Downgrade complete: Presets restored to database storage")
    print("Note: Preset folders in configs/presets/ were NOT deleted. Manual cleanup may be required.")
