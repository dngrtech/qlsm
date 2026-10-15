"""Stored notifications: the one write path for core and addons.

Addons call these through ctx.notify()/ctx.resolve() in ui/addons/context.py,
which fill in `source` with the addon id; core calls them with
source='core'. Both commit, so a notification is visible to the web app as
soon as the call returns, whichever process made it (the status poller runs
apart from the web app).
"""
import datetime

from ui import db
from ui.models import Notification

SEVERITIES = ('info', 'warning', 'critical')
RETENTION_DAYS = 30
TITLE_MAX = 120
BODY_MAX = 1000
LINK_MAX = 500

_SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}


def _validate_link(link):
    """Only an in-app path is allowed: the bell routes it with the SPA router,
    and an absolute URL from an addon has no business in the navbar."""
    if link is None:
        return None
    if (not isinstance(link, str) or not link.startswith('/') or link.startswith('//')
            or len(link) > LINK_MAX):
        raise ValueError(f'notification link must be a relative path starting with "/": {link!r}')
    return link


def _commit():
    """Commit, or roll back and re-raise. The status poller keeps one session
    for its whole life, so a commit that fails (SQLite 'database is locked'
    while the web app writes) and is left un-rolled-back would fail every
    later cycle with PendingRollbackError until a restart."""
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _prune(now):
    cutoff = now - datetime.timedelta(days=RETENTION_DAYS)
    Notification.query.filter(Notification.updated_at < cutoff).delete(synchronize_session=False)


def notify(source, severity, title, body='', link=None, key=None):
    """Store a notification and return its row.

    With `key`, an open (unresolved) row from the same source with that key is
    updated in place instead of adding another one. A repeat leaves a row the
    operator has already read as read, unless the severity went up.
    """
    if severity not in SEVERITIES:
        raise ValueError(f'notification severity must be one of {SEVERITIES}: {severity!r}')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('notification title is required')
    link = _validate_link(link)
    title = title.strip()[:TITLE_MAX]
    body = (body or '')[:BODY_MAX]
    now = datetime.datetime.utcnow()

    row = None
    if key is not None:
        row = (Notification.query
               .filter_by(source=source, key=key, resolved_at=None)
               .order_by(Notification.id.desc())
               .first())

    if row is None:
        _prune(now)
        row = Notification(source=source, key=key, created_at=now)
        db.session.add(row)
    elif _SEVERITY_RANK[severity] > _SEVERITY_RANK.get(row.severity, 0):
        row.read_at = None

    row.severity = severity
    row.title = title
    row.body = body
    row.link = link
    row.updated_at = now
    _commit()
    return row


def resolve(source, key):
    """Mark the open row(s) of `source` with `key` resolved; return how many."""
    if key is None:
        # filter_by(key=None) would match every keyless row of the source.
        return 0
    now = datetime.datetime.utcnow()
    count = (Notification.query
             .filter_by(source=source, key=key, resolved_at=None)
             .update({'resolved_at': now}, synchronize_session=False))
    _commit()
    return count
