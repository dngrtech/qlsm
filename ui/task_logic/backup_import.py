"""Restores a .qlsmbak archive: wipes this QLSM instance's database and
managed file trees, then reloads everything from the archive.

Destructive by design — the route layer (ui/routes/backup_routes.py) is
responsible for requiring an explicit confirmation before calling this.
Every filesystem mutation goes through a stage-then-atomic-rename swap
(mirroring ui/routes/preset_import_routes.py's existing pattern): the old
contents of each managed directory are moved aside rather than deleted,
and only deleted for good once the whole restore — including the database
reload — has committed. On any failure, everything already swapped is
rolled back from those moved-aside copies before the error propagates.
"""
import datetime
import io
import json
import logging
import os
import shutil
import tempfile
import zipfile

from ui import db
from ui.backup_crypto import BackupDecryptError, decrypt_archive, encrypt_archive
from ui.task_logic.backup_db_import import BackupImportError, replace_database
from ui.task_logic.backup_export import BACKUP_MANIFEST_FORMAT_VERSION, build_backup_zip_bytes
from ui.task_logic.backup_files import backup_archive_file_trees, is_restore_child

BACKUP_SNAPSHOTS_DIR = 'backup_snapshots'
MAX_RETAINED_SNAPSHOTS = 3
logger = logging.getLogger(__name__)


class BackupRestoreError(ValueError):
    """Raised for any archive/state the caller should treat as a 400."""


def _parse_archive(blob, password):
    try:
        zip_bytes = decrypt_archive(blob, password)
    except BackupDecryptError as e:
        raise BackupRestoreError(str(e)) from e

    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
        bad_entry = archive.testzip()
    except zipfile.BadZipFile as e:
        raise BackupRestoreError('Not a valid QLSM backup file.') from e
    if bad_entry:
        raise BackupRestoreError(f'Backup archive is corrupted (bad entry: {bad_entry}).')

    try:
        manifest = json.loads(archive.read('manifest.json'))
    except (KeyError, json.JSONDecodeError) as e:
        raise BackupRestoreError('Backup archive is missing a valid manifest.json.') from e
    if manifest.get('type') != 'qlsm-global-backup':
        raise BackupRestoreError('This file is not a QLSM global backup.')
    if manifest.get('format_version') != BACKUP_MANIFEST_FORMAT_VERSION:
        raise BackupRestoreError('Backup was made with an incompatible QLSM backup format.')

    try:
        db_data = json.loads(archive.read('db_export.json'))
    except (KeyError, json.JSONDecodeError) as e:
        raise BackupRestoreError('Backup archive is missing a valid db_export.json.') from e

    return manifest, db_data, archive


def _prune_old_snapshots():
    names = sorted(
        name for name in os.listdir(BACKUP_SNAPSHOTS_DIR)
        if name.startswith('pre-restore-') and name.endswith('.qlsmbak')
    )
    for name in names[:-MAX_RETAINED_SNAPSHOTS]:
        os.remove(os.path.join(BACKUP_SNAPSHOTS_DIR, name))


def _write_safety_snapshot(trees):
    """Silently capture current state before any destructive step, purely
    as a recovery-of-last-resort if the restore fails partway. Never
    exposed in any UI list; best-effort only — must never block a
    restore. Written owner-only (0700 dir / 0600 file) since this is a
    plaintext-equivalent dump of every secret the instance holds — SSH
    keys, the Vultr API key, user credentials — same as any backup made
    without a password."""
    try:
        os.makedirs(BACKUP_SNAPSHOTS_DIR, mode=0o700, exist_ok=True)
        os.chmod(BACKUP_SNAPSHOTS_DIR, 0o700)  # mode= above only applies on creation
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')
        snapshot_path = os.path.join(BACKUP_SNAPSHOTS_DIR, f'pre-restore-{timestamp}.qlsmbak')
        fd = os.open(snapshot_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(encrypt_archive(build_backup_zip_bytes(trees), None))
        _prune_old_snapshots()
    except Exception:
        pass


def _extract_tree(archive, prefix, staging_dir):
    archive_prefix = f'files/{prefix}/'
    for info in archive.infolist():
        if info.is_dir() or not info.filename.startswith(archive_prefix):
            continue
        rel_path = info.filename[len(archive_prefix):]
        if not rel_path or '..' in rel_path.split('/'):
            raise BackupRestoreError(f'Backup archive contains an unsafe path entry: {info.filename!r}')
        target = os.path.join(staging_dir, *rel_path.split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with archive.open(info) as source, open(target, 'wb') as dest:
            shutil.copyfileobj(source, dest)
        mode = (info.external_attr >> 16) & 0o777  # mask strips setuid/setgid/sticky
        if mode:
            os.chmod(target, mode)


def _reserve_temp_path(root):
    """Reserve a unique name inside `root` without leaving anything on
    disk at that path — same trick as preset_import_routes._make_backup_path."""
    path = tempfile.mkdtemp(prefix='.qlsm-restore-old-', dir=root)
    os.rmdir(path)
    return path


def _remove_restore_path(path):
    """Best-effort cleanup that never hides a restore's primary result."""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        elif os.path.lexists(path):
            os.remove(path)
    except Exception as error:
        logger.warning('Failed to remove restore path %s: %s', path, error)


def _restore_displaced(root, displaced):
    for name, backup_path in reversed(displaced):
        target = os.path.join(root, name)
        _remove_restore_path(target)
        if backup_path:
            try:
                shutil.move(backup_path, target)
            except Exception as error:
                logger.warning(
                    'Failed to roll back restore path %s to %s: %s',
                    backup_path, target, error,
                )


def _swap_tree(root, staged_dir, skip=None):
    """Replace every direct child of `root` — except ones `skip` excludes
    — with the matching child from `staged_dir`. Excluded children (a
    nested tree handled by its own separate entry in backup_file_trees,
    like configs/presets under configs, or an app-shipped folder backup
    never touches at all, like presets/_builtin) are left exactly as they
    are: never moved, never staged over. Operating per-child rather than
    replacing `root` wholesale is what makes that possible — a single
    directory-level rename can't leave part of its own contents alone.

    Returns a list of (child_name, backup_path) pairs for rollback;
    backup_path is None for a child that didn't exist before this call.
    Caller must ensure `root`'s parent directory already exists.
    """
    os.makedirs(root, exist_ok=True)
    excluded = lambda name: is_restore_child(name) or (skip and skip(name))
    current_children = [
        name for name in os.listdir(root)
        if not excluded(name)
    ]

    displaced = []
    installed = []
    existing_names = set()
    try:
        for name in current_children:
            backup_path = _reserve_temp_path(root)
            shutil.move(os.path.join(root, name), backup_path)
            displaced.append((name, backup_path))
            existing_names.add(name)

        if os.path.isdir(staged_dir):
            for name in os.listdir(staged_dir):
                if excluded(name):
                    continue
                shutil.move(os.path.join(staged_dir, name), os.path.join(root, name))
                installed.append(name)
    except Exception:
        for name in reversed(installed):
            _remove_restore_path(os.path.join(root, name))
        _restore_displaced(root, displaced)
        raise

    return displaced + [
        (name, None) for name in installed if name not in existing_names
    ]


def restore_backup_archive(blob, password):
    """Wipe and reload this QLSM instance's database and managed file
    trees from an uploaded .qlsmbak archive. Keep the database transaction
    open until the staged file trees have been swapped successfully."""
    manifest, db_data, archive = _parse_archive(blob, password)
    with archive, backup_archive_file_trees() as trees:
        return _restore_parsed_archive(manifest, db_data, archive, trees)


def _restore_parsed_archive(manifest, db_data, archive, trees):
    _write_safety_snapshot(trees)

    staged_dirs = {}
    swapped = []
    committed = False
    try:
        for prefix, root, _skip in trees:
            os.makedirs(root, exist_ok=True)
            staging = tempfile.mkdtemp(prefix='.qlsm-restore-staging-', dir=root)
            staged_dirs[prefix] = staging
            _extract_tree(archive, prefix, staging)

        replace_database(db_data)

        for prefix, root, skip in trees:
            swapped_children = _swap_tree(root, staged_dirs[prefix], skip)
            swapped.append((root, swapped_children))

        db.session.commit()
        committed = True
    except Exception:
        try:
            db.session.rollback()
        except Exception as error:
            logger.warning('Failed to roll back database restore (%s).', type(error).__name__)
        for root, swapped_children in reversed(swapped):
            _restore_displaced(root, swapped_children)
        raise
    finally:
        for staging in staged_dirs.values():
            _remove_restore_path(staging)
        if committed:
            for _root, swapped_children in swapped:
                for _name, backup_path in swapped_children:
                    if backup_path:
                        _remove_restore_path(backup_path)

    return {
        'qlsm_version': manifest.get('qlsm_version'),
        'created_at': manifest.get('created_at'),
        'restart_required': True,
        'addon_state_restored': 'addon_states' in db_data,
    }
