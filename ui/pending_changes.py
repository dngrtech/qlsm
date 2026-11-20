"""Pending (not yet restarted) instance changes.

A config save or plugin update without a restart syncs files to the host but
leaves the running QLDS on the old ones (status UPDATED). This module records
*what* changed so the operator can review it before restarting, and drops
the record once a restart makes the files live.

Records are computed on the controller from ``configs/<host>/<id>/``: a
snapshot before the files are overwritten, another after, diffed here. Text
files get a unified diff (capped), binaries and oversized files a hash only.
"""
import difflib
import hashlib
import json
import os

from sqlalchemy import delete

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

def record_pending_change(instance_id, source, files, settings=None):
    """Add one record if anything changed. Does not commit. Returns the row
    or None."""
    settings = settings or []
    if not files and not settings:
        return None
    row = PendingInstanceChange(
        instance_id=instance_id,
        source=source,
        changes_json=json.dumps({'files': files, 'settings': settings}),
    )
    db.session.add(row)
    return row


def clear_pending_changes(instance_id):
    """Drop every record for the instance (it was restarted). Does not commit."""
    db.session.execute(
        delete(PendingInstanceChange).where(PendingInstanceChange.instance_id == instance_id)
    )


def list_pending_changes(instance_id):
    rows = (
        PendingInstanceChange.query
        .filter_by(instance_id=instance_id)
        .order_by(PendingInstanceChange.created_at.asc(), PendingInstanceChange.id.asc())
        .all()
    )
    return [row.to_dict() for row in rows]
