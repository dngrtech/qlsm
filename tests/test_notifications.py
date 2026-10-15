"""Stored notifications: ui/notifications.py, ctx.notify/resolve, /api/notifications."""
import datetime

import pytest

from ui import db
from ui.addons.context import AddonContext
from ui.models import Notification
from ui.notifications import notify, resolve
from tests.helpers import auth_headers, make_user


# --- notify / resolve ---

def test_notify_stores_a_row(app):
    with app.app_context():
        row = notify('core', 'warning', 'Disk almost full', body='92 % used', link='/servers')
        stored = db.session.get(Notification, row.id)
        assert stored.source == 'core'
        assert stored.severity == 'warning'
        assert stored.title == 'Disk almost full'
        assert stored.body == '92 % used'
        assert stored.link == '/servers'
        assert stored.key is None
        assert stored.resolved_at is None
        assert stored.read_at is None


def test_notify_without_key_never_dedupes(app):
    with app.app_context():
        notify('core', 'info', 'Same title')
        notify('core', 'info', 'Same title')
        assert Notification.query.count() == 2


def test_notify_with_key_updates_the_open_row(app):
    with app.app_context():
        first = notify('core', 'warning', 'CPU high', body='71 %', key='cpu')
        second = notify('core', 'critical', 'CPU overloaded', body='97 %', key='cpu')
        assert second.id == first.id
        assert Notification.query.count() == 1
        row = Notification.query.one()
        assert row.severity == 'critical'
        assert row.title == 'CPU overloaded'
        assert row.body == '97 %'


def test_repeat_of_a_read_notification_stays_read_unless_it_escalates(app):
    with app.app_context():
        row = notify('core', 'warning', 'CPU high', key='cpu')
        row.read_at = datetime.datetime.utcnow()
        db.session.commit()

        notify('core', 'warning', 'CPU high', key='cpu')
        assert Notification.query.one().read_at is not None

        notify('core', 'critical', 'CPU overloaded', key='cpu')
        assert Notification.query.one().read_at is None


def test_notify_after_resolve_opens_a_new_row(app):
    with app.app_context():
        first = notify('core', 'warning', 'Host unreachable', key='host-1')
        assert resolve('core', 'host-1') == 1
        second = notify('core', 'warning', 'Host unreachable', key='host-1')
        assert second.id != first.id
        assert Notification.query.count() == 2
        assert db.session.get(Notification, first.id).resolved_at is not None
        assert db.session.get(Notification, second.id).resolved_at is None


def test_resolve_is_scoped_to_source(app):
    with app.app_context():
        mine = notify('addon-a', 'warning', 'A', key='shared-key')
        theirs = notify('addon-b', 'warning', 'B', key='shared-key')
        assert mine.id != theirs.id
        assert resolve('addon-a', 'shared-key') == 1
        assert db.session.get(Notification, mine.id).resolved_at is not None
        assert db.session.get(Notification, theirs.id).resolved_at is None


def test_resolve_twice_resolves_once(app):
    with app.app_context():
        notify('core', 'warning', 'A', key='k')
        assert resolve('core', 'k') == 1
        assert resolve('core', 'k') == 0
        assert resolve('core', 'never-opened') == 0


def test_notify_prunes_rows_older_than_30_days(app):
    with app.app_context():
        old = datetime.datetime.utcnow() - datetime.timedelta(days=31)
        recent = datetime.datetime.utcnow() - datetime.timedelta(days=29)
        db.session.add(Notification(source='core', severity='info', title='old',
                                    created_at=old, updated_at=old))
        db.session.add(Notification(source='core', severity='info', title='recent',
                                    created_at=recent, updated_at=recent))
        db.session.commit()

        notify('core', 'info', 'new')
        titles = {n.title for n in Notification.query.all()}
        assert titles == {'recent', 'new'}


@pytest.mark.parametrize('kwargs', [
    {'severity': 'fatal'},
    {'title': ''},
    {'link': 'https://example.com/'},
    {'link': '//example.com/'},
    {'link': 'servers'},
])
def test_notify_rejects_bad_input(app, kwargs):
    args = {'severity': 'info', 'title': 'T', **kwargs}
    with app.app_context():
        with pytest.raises(ValueError):
            notify('core', args.pop('severity'), args.pop('title'), **args)
        assert Notification.query.count() == 0


def test_notify_truncates_long_title_and_body(app):
    with app.app_context():
        row = notify('core', 'info', 'x' * 500, body='y' * 5000)
        assert len(row.title) == 120
        assert len(row.body) == 1000


# --- AddonContext ---

def test_ctx_notify_and_resolve_bind_the_addon_id(app, tmp_path):
    ctx = AddonContext('sample-addon', {}, str(tmp_path))
    with app.app_context():
        row = ctx.notify('critical', 'Something broke', body='details', link='/addons/sample-addon', key='k1')
        assert row.source == 'sample-addon'
        # Another source's row with the same key is not touched by this addon.
        other = notify('core', 'warning', 'Core thing', key='k1')
        assert ctx.resolve('k1') == 1
        assert db.session.get(Notification, row.id).resolved_at is not None
        assert db.session.get(Notification, other.id).resolved_at is None


# --- routes ---

def _seed(app):
    with app.app_context():
        a = notify('core', 'info', 'first')
        b = notify('core', 'warning', 'second')
        c = notify('core', 'critical', 'third')
        c.read_at = datetime.datetime.utcnow()
        db.session.commit()
        return a.id, b.id, c.id


@pytest.mark.parametrize('method,path', [
    ('get', '/api/notifications'),
    ('post', '/api/notifications/1/read'),
    ('post', '/api/notifications/read-all'),
])
def test_routes_require_auth(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401


def test_list_returns_newest_first_with_unread_count(client, app):
    make_user(app, 'notifuser', 'password123')
    headers = auth_headers(app, 'notifuser')
    _seed(app)
    response = client.get('/api/notifications', headers=headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert [n['title'] for n in data['notifications']] == ['third', 'second', 'first']
    assert data['unread_count'] == 2
    first = data['notifications'][0]
    assert set(first) >= {'id', 'source', 'severity', 'title', 'body', 'link', 'key',
                          'created_at', 'updated_at', 'resolved_at', 'read_at'}


def test_list_unread_filter_and_limit(client, app):
    make_user(app, 'notifuser', 'password123')
    headers = auth_headers(app, 'notifuser')
    _seed(app)
    response = client.get('/api/notifications?unread=1&limit=1', headers=headers)
    data = response.get_json()['data']
    assert [n['title'] for n in data['notifications']] == ['second']
    assert data['unread_count'] == 2


def test_mark_one_read(client, app):
    make_user(app, 'notifuser', 'password123')
    headers = auth_headers(app, 'notifuser')
    a_id, _, _ = _seed(app)
    response = client.post(f'/api/notifications/{a_id}/read', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data']['read_at'] is not None
    with app.app_context():
        assert db.session.get(Notification, a_id).read_at is not None


def test_mark_missing_read_is_404(client, app):
    make_user(app, 'notifuser', 'password123')
    headers = auth_headers(app, 'notifuser')
    response = client.post('/api/notifications/999/read', headers=headers)
    assert response.status_code == 404


def test_mark_all_read(client, app):
    make_user(app, 'notifuser', 'password123')
    headers = auth_headers(app, 'notifuser')
    _seed(app)
    response = client.post('/api/notifications/read-all', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data']['updated'] == 2
    with app.app_context():
        assert Notification.query.filter(Notification.read_at.is_(None)).count() == 0


# --- a failed commit must not wedge the session ---

def _fail_next_commit(monkeypatch):
    """Make the next commit fail inside its flush, like SQLite's 'database is
    locked'. A flush error leaves the session refusing all further work
    (PendingRollbackError) until someone rolls it back."""
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    session = db.session()

    def fail_once(sess, flush_context, instances):
        event.remove(session, 'before_flush', fail_once)
        raise OperationalError('INSERT', {}, Exception('database is locked'))

    event.listen(session, 'before_flush', fail_once)


def _fail_next_commit_call(monkeypatch):
    """Make the next db.session.commit() raise before committing, for a write
    with nothing to flush (resolve() is a bulk UPDATE)."""
    from sqlalchemy.exc import OperationalError

    real_commit = db.session.commit

    def commit():
        monkeypatch.setattr(db.session, 'commit', real_commit)
        raise OperationalError('COMMIT', {}, Exception('database is locked'))

    monkeypatch.setattr(db.session, 'commit', commit)


def test_notify_rolls_back_a_failed_commit(app, monkeypatch):
    with app.app_context():
        _fail_next_commit(monkeypatch)
        with pytest.raises(Exception, match='database is locked'):
            notify('core', 'warning', 'first try')
        # The session is usable again and the failed row is gone.
        row = notify('core', 'warning', 'second try')
        assert [n.title for n in Notification.query.all()] == ['second try']
        assert row.id is not None


def test_resolve_rolls_back_a_failed_commit(app, monkeypatch):
    with app.app_context():
        notify('core', 'warning', 'open', key='k')
        _fail_next_commit_call(monkeypatch)
        with pytest.raises(Exception, match='database is locked'):
            resolve('core', 'k')
        assert Notification.query.one().resolved_at is None
        assert resolve('core', 'k') == 1
