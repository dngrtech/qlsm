"""Builds one archive (optionally encrypted) containing the full
exportable state of this QLSM instance: manifest, database export, and
every file tree from backup_files.backup_file_trees().
"""
import datetime
import io
import json
import zipfile

from ui.backup_crypto import encrypt_archive
from ui.task_logic.backup_db_export import serialize_database
from ui.task_logic.backup_files import backup_archive_file_trees, backup_file_trees, walk_tree

BACKUP_MANIFEST_FORMAT_VERSION = 1


def _read_app_version():
    try:
        with open('VERSION', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return 'unknown'


def _build_manifest():
    return {
        'type': 'qlsm-global-backup',
        'format_version': BACKUP_MANIFEST_FORMAT_VERSION,
        'qlsm_version': _read_app_version(),
        'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
    }


def build_backup_zip_bytes(trees=None):
    """Build the plaintext ZIP (manifest + db_export.json + file trees)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            'manifest.json',
            json.dumps(_build_manifest(), indent=2, sort_keys=True) + '\n',
        )
        archive.writestr(
            'db_export.json',
            json.dumps(serialize_database(), indent=2, sort_keys=True) + '\n',
        )
        if trees is None:
            trees = backup_file_trees()
        for prefix, root, skip in trees:
            for rel_path, full_path in walk_tree(root, skip):
                archive.write(full_path, f'files/{prefix}/{rel_path}')
    buffer.seek(0)
    return buffer.read()


def build_backup_archive(password):
    """Return (blob, filename) for the downloadable .qlsmbak file."""
    with backup_archive_file_trees() as trees:
        zip_bytes = build_backup_zip_bytes(trees)
    blob = encrypt_archive(zip_bytes, password)
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    return blob, f'qlsm-backup-{timestamp}.qlsmbak'
