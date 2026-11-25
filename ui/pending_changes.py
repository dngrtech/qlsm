"""Pending (not yet restarted) instance changes.

A config save or plugin update without a restart syncs files to the host but
leaves the running QLDS on the old ones (status UPDATED). This module records
*what* changed so the operator can review it before restarting, and drops
the record once a restart makes the files live.

The diff is taken on the controller when the files are staged, before the
sync job runs, so it is recorded then as *staged* (synced=False) and hidden.
The sync job that gets the files to the host publishes every staged record
of the instance in the same commit as UPDATED (publish_pending_changes). A
failed or never-queued sync leaves them staged: the next sync of the same
instance carries those files too, and publishes them.

Records are computed on the controller from ``configs/<host>/<id>/``: a
snapshot before the files are overwritten, another after, diffed here. Text
files get a unified diff (capped), binaries and oversized files a hash only.
"""
import difflib
import hashlib
import json
import os

from sqlalchemy import delete, update

from ui import db
from ui.models import AppSetting, PendingInstanceChange

DEFER_RESTARTS_SETTING = 'defer_restarts'

SOURCE_CONFIG_SAVE = 'config_save'
SOURCE_PLUGIN_UPDATE = 'plugin_update'
SOURCE_WORKSHOP_UPDATE = 'workshop_update'

# A file larger than this is compared by hash only.
MAX_TEXT_BYTES = 512 * 1024
# Per-file cap on the stored unified diff.
MAX_DIFF_CHARS = 20000


# --- Global setting -------------------------------------------------------

def get_defer_restarts():
    """True when saves should default to "no restart". Default False."""
    row = db.session.get(AppSetting, DEFER_RESTARTS_SETTING)
    return bool(row and row.value == 'true')


def set_defer_restarts(enabled):
    """Create/update the setting. Does not commit."""
    value = 'true' if enabled else 'false'
    row = db.session.get(AppSetting, DEFER_RESTARTS_SETTING)
    if row:
        row.value = value
    else:
        db.session.add(AppSetting(key=DEFER_RESTARTS_SETTING, value=value))


# --- Snapshots and diffs --------------------------------------------------

def _read_entry(path):
    with open(path, 'rb') as f:
        data = f.read()
    sha = hashlib.sha256(data).hexdigest()
    text = None
    if len(data) <= MAX_TEXT_BYTES and b'\x00' not in data:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = None
    return {'sha256': sha, 'size': len(data), 'text': text}


def snapshot_dir(base_dir, prefix=''):
    """{relative/posix/path: {sha256, size, text|None}} for every file under
    base_dir. Missing directory -> {}. ``prefix`` is prepended to each key."""
    snapshot = {}
    if not os.path.isdir(base_dir):
        return snapshot
    for root, _dirs, files in os.walk(base_dir):
        for name in files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, base_dir).replace(os.sep, '/')
            try:
                snapshot[prefix + rel] = _read_entry(full)
            except OSError:
                continue
    return snapshot


def _unified_diff(path, before_text, after_text):
    lines = list(difflib.unified_diff(
        (before_text or '').splitlines(keepends=True),
        (after_text or '').splitlines(keepends=True),
        fromfile=f'a/{path}',
        tofile=f'b/{path}',
        n=3,
    ))
    diff = ''.join(line if line.endswith('\n') else line + '\n' for line in lines)
    if len(diff) > MAX_DIFF_CHARS:
        return diff[:MAX_DIFF_CHARS], True
    return diff, False


def diff_snapshots(before, after):
    """List of changed files between two snapshots, sorted by path."""
    changes = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old and new and old['sha256'] == new['sha256']:
            continue
        if old is None:
            kind = 'added'
        elif new is None:
            kind = 'removed'
        else:
            kind = 'modified'
        entry = {
            'path': path,
            'change': kind,
            'sha256_before': old['sha256'] if old else None,
            'sha256_after': new['sha256'] if new else None,
            'diff': None,
            'truncated': False,
            'binary': False,
        }
        old_text = old['text'] if old else ''
        new_text = new['text'] if new else ''
        if old_text is None or new_text is None:
            entry['binary'] = True
        else:
            entry['diff'], entry['truncated'] = _unified_diff(path, old_text, new_text)
        changes.append(entry)
    return changes


# --- Records --------------------------------------------------------------

def record_pending_change(instance_id, source, files, settings=None, synced=True):
    """Add one record if anything changed. Does not commit. Returns the row
    or None. `synced=False` stages it until publish_pending_changes()."""
    settings = settings or []
    if not files and not settings:
        return None
    row = PendingInstanceChange(
        instance_id=instance_id,
        source=source,
        changes_json=json.dumps({'files': files, 'settings': settings}),
        synced=synced,
    )
    db.session.add(row)
    return row


def publish_pending_changes(instance_id):
    """Mark the instance's staged records synced: their files just reached
    the host. Does not commit."""
    db.session.execute(
        update(PendingInstanceChange)
        .where(PendingInstanceChange.instance_id == instance_id)
        .where(PendingInstanceChange.synced.is_(False))
        .values(synced=True)
    )


def clear_pending_changes(instance_id, synced_only=False):
    """Drop the instance's records (it was restarted). Does not commit.

    A restart that syncs the instance's files first (restart, deploy, a
    config apply with restart) loads staged changes too and drops all.
    `synced_only` is for a restart that does not sync (an observed external
    restart, start, a LAN rate or hooks run): staged files are not on the
    host yet, so their records stay for the sync that carries them."""
    stmt = delete(PendingInstanceChange).where(PendingInstanceChange.instance_id == instance_id)
    if synced_only:
        stmt = stmt.where(PendingInstanceChange.synced.is_(True))
    db.session.execute(stmt)


def list_pending_changes(instance_id):
    rows = (
        PendingInstanceChange.query
        .filter_by(instance_id=instance_id, synced=True)
        .order_by(PendingInstanceChange.created_at.asc(), PendingInstanceChange.id.asc())
        .all()
    )
    return [row.to_dict() for row in rows]
