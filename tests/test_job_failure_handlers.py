import pytest
from unittest.mock import MagicMock, patch
from ui import create_app, db
from ui.models import Host, HostStatus, QLInstance, InstanceStatus


def test_host_failure_handler_updates_provisioning_to_error():
    """host_job_failure_handler must set ERROR for PROVISIONING hosts."""
    from ui.task_logic.job_failure_handlers import host_job_failure_handler

    mock_job = MagicMock()
    mock_job.id = 'test-job-123'
    mock_job.args = [1]
    mock_job.meta = {}

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        host = Host(id=1, name='test', provider='vultr', status=HostStatus.PROVISIONING)
        db.session.add(host)
        db.session.commit()

    with patch('ui.create_app', return_value=app):
        host_job_failure_handler(mock_job, None, RuntimeError, RuntimeError("boom"), None)

    with app.app_context():
        host = db.session.get(Host, 1)
        assert host.status == HostStatus.ERROR


def test_host_failure_handler_updates_rebooting_to_error():
    """host_job_failure_handler must handle REBOOTING state."""
    from ui.task_logic.job_failure_handlers import host_job_failure_handler

    mock_job = MagicMock()
    mock_job.id = 'test-job-456'
    mock_job.args = [1]
    mock_job.meta = {}

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        host = Host(id=1, name='test', provider='vultr', status=HostStatus.REBOOTING)
        db.session.add(host)
        db.session.commit()

    with patch('ui.create_app', return_value=app):
        host_job_failure_handler(mock_job, None, RuntimeError, RuntimeError("boom"), None)

    with app.app_context():
        host = db.session.get(Host, 1)
        assert host.status == HostStatus.ERROR


def test_host_failure_handler_updates_setup_pending_to_error():
    """host_job_failure_handler must handle PROVISIONED_PENDING_SETUP state."""
    from ui.task_logic.job_failure_handlers import host_job_failure_handler

    mock_job = MagicMock()
    mock_job.id = 'test-job-setup-pending'
    mock_job.args = [1]
    mock_job.meta = {}

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        host = Host(id=1, name='test', provider='vultr', status=HostStatus.PROVISIONED_PENDING_SETUP)
        db.session.add(host)
        db.session.commit()

    with patch('ui.create_app', return_value=app):
        host_job_failure_handler(mock_job, None, RuntimeError, RuntimeError("boom"), None)

    with app.app_context():
        host = db.session.get(Host, 1)
        assert host.status == HostStatus.ERROR


@patch('ui.task_lock.lock_superseded', return_value=False)
@patch('ui.task_lock.release_lock')
def test_instance_failure_handler_releases_lock(mock_release, _superseded):
    """Instance failure handler must release the entity lock."""
    from ui.task_logic.job_failure_handlers import instance_job_failure_handler

    mock_job = MagicMock()
    mock_job.id = 'test-job-789'
    mock_job.args = [1]
    mock_job.meta = {'lock_token': 'tok-abc'}

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        host = Host(id=1, name='host', provider='vultr', status=HostStatus.ACTIVE)
        inst = QLInstance(id=1, name='test', host_id=1, port=27960, hostname='test-host', status=InstanceStatus.DEPLOYING)
        db.session.add(host)
        db.session.add(inst)
        db.session.commit()

    with patch('ui.create_app', return_value=app):
        instance_job_failure_handler(mock_job, None, RuntimeError, RuntimeError("boom"), None)

    mock_release.assert_called_once_with('instance', 1, 'tok-abc')


@patch('ui.task_lock.release_lock')
def test_host_failure_handler_releases_lock(mock_release):
    """Host failure handler must release the entity lock."""
    from ui.task_logic.job_failure_handlers import host_job_failure_handler

    mock_job = MagicMock()
    mock_job.id = 'test-job-abc'
    mock_job.args = [1]
    mock_job.meta = {'lock_token': 'tok-xyz'}

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        host = Host(id=1, name='test', provider='vultr', status=HostStatus.PROVISIONING)
        db.session.add(host)
        db.session.commit()

    with patch('ui.create_app', return_value=app):
        host_job_failure_handler(mock_job, None, RuntimeError, RuntimeError("boom"), None)

    mock_release.assert_called_once_with('host', 1, 'tok-xyz')


@patch('ui.task_lock.release_lock')
@patch('ui.task_lock.release_locks')
def test_host_failure_handler_releases_instance_locks_before_host_lock(
    mock_release_locks, mock_release
):
    from ui.task_logic.job_failure_handlers import host_job_failure_handler

    mock_job = MagicMock()
    mock_job.id = 'test-job-rerun-abandoned'
    mock_job.args = [1]
    mock_job.meta = {
        'lock_token': 'tok-rerun',
        'locked_instance_ids': [3, 1],
    }

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        host = Host(
            id=1,
            name='test',
            provider='vultr',
            status=HostStatus.CONFIGURING,
        )
        db.session.add(host)
        db.session.commit()

    events = []
    mock_release_locks.side_effect = lambda *args: events.append(
        ('instances', args)
    )
    mock_release.side_effect = lambda *args: events.append(('host', args))

    with patch('ui.create_app', return_value=app):
        host_job_failure_handler(
            mock_job,
            None,
            RuntimeError,
            RuntimeError('abandoned'),
            None,
        )

    assert events == [
        ('instances', ('instance', [3, 1], 'tok-rerun')),
        ('host', ('host', 1, 'tok-rerun')),
    ]


def _handler_app(status, instance_id=1):
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        db.session.add(Host(id=1, name='host', provider='vultr', status=HostStatus.ACTIVE))
        db.session.add(QLInstance(id=instance_id, name='test', host_id=1, port=27960,
                                  hostname='test-host', status=status))
        db.session.commit()
    return app


def _run_instance_handler(app, exc, token='tok'):
    from ui.task_logic.job_failure_handlers import instance_job_failure_handler

    job = MagicMock()
    job.id = 'job-1'
    job.args = [1]
    job.meta = {'lock_token': token} if token else {}
    with patch('ui.create_app', return_value=app):
        instance_job_failure_handler(job, None, type(exc), exc, None)


def _instance_status(app):
    with app.app_context():
        return db.session.get(QLInstance, 1).status


def _observation(active):
    from ui.task_logic.service_runtime import RuntimeObservation
    return {'27960': RuntimeObservation(status=None, invocation_id=None, active=active,
                                        service_started_at=None)}


@patch('ui.task_lock.release_lock')
@patch('ui.task_lock.lock_superseded', return_value=False)
def test_abandoned_job_active_service_sets_running(_superseded, _release):
    from rq.exceptions import AbandonedJobError

    app = _handler_app(InstanceStatus.CONFIGURING)
    with patch('ui.task_logic.interrupted_job_recovery.probe_host_runtime',
               return_value=_observation(True)):
        _run_instance_handler(app, AbandonedJobError('gone'))
    assert _instance_status(app) == InstanceStatus.RUNNING


@patch('ui.task_lock.release_lock')
@patch('ui.task_lock.lock_superseded', return_value=False)
def test_abandoned_job_unreachable_sets_error(_superseded, _release):
    from rq.exceptions import AbandonedJobError

    app = _handler_app(InstanceStatus.CONFIGURING)
    with patch('ui.task_logic.interrupted_job_recovery.probe_host_runtime', return_value=None):
        _run_instance_handler(app, AbandonedJobError('gone'))
    assert _instance_status(app) == InstanceStatus.ERROR


@patch('ui.task_lock.release_lock')
@patch('ui.task_lock.lock_superseded', return_value=False)
def test_non_abandon_exception_still_sets_error_without_probe(_superseded, _release):
    app = _handler_app(InstanceStatus.CONFIGURING)
    with patch('ui.task_logic.interrupted_job_recovery.probe_host_runtime') as probe:
        _run_instance_handler(app, RuntimeError('boom'))
    probe.assert_not_called()
    assert _instance_status(app) == InstanceStatus.ERROR


@patch('ui.task_lock.release_lock')
@patch('ui.task_lock.lock_superseded', return_value=True)
def test_non_abandon_failure_with_superseded_lock_changes_nothing(_superseded, release):
    app = _handler_app(InstanceStatus.CONFIGURING)
    _run_instance_handler(app, RuntimeError('boom'))
    assert _instance_status(app) == InstanceStatus.CONFIGURING
    release.assert_not_called()


@patch('ui.task_lock.release_lock')
def test_retry_rechecks_superseded_lock_before_writing(release):
    """A newer operation can take the lock during a retry backoff; the stale
    callback must not overwrite its status with ERROR on the next attempt."""
    from sqlalchemy.exc import OperationalError
    import sqlite3
    from ui.task_logic import common

    app = _handler_app(InstanceStatus.CONFIGURING)
    superseded = iter([False, False, True])
    real_commit = db.session.commit
    commits = {'n': 0}

    def _commit():
        commits['n'] += 1
        if commits['n'] == 1:
            raise OperationalError('COMMIT', {}, sqlite3.OperationalError('database is locked'))
        return real_commit()

    with patch('ui.task_lock.lock_superseded', side_effect=lambda *a: next(superseded)), \
            patch.object(common.time, 'sleep'), \
            patch.object(db.session, 'commit', side_effect=_commit):
        _run_instance_handler(app, RuntimeError('boom'))

    assert _instance_status(app) == InstanceStatus.CONFIGURING
    release.assert_not_called()


@patch('ui.task_lock.lock_superseded', return_value=False)
def test_lock_released_even_when_error_status_cannot_be_saved(_superseded):
    from sqlalchemy.exc import OperationalError
    import sqlite3
    from ui.task_logic import common

    app = _handler_app(InstanceStatus.RESTARTING)
    locked = OperationalError('COMMIT', {}, sqlite3.OperationalError('database is locked'))
    with patch('ui.task_lock.release_lock') as release, \
            patch.object(common.time, 'sleep'), \
            patch.object(db.session, 'commit', side_effect=locked):
        _run_instance_handler(app, RuntimeError('boom'))

    release.assert_called_once_with('instance', 1, 'tok')


@patch('ui.task_lock.release_lock')
@patch('ui.task_lock.release_locks')
def test_host_retry_rechecks_superseded_lock_before_writing(_release_locks, _release):
    """A newer deletion takes the host lock and saves DELETING during the
    retry backoff; the old reboot callback must not overwrite it."""
    from sqlalchemy.exc import OperationalError
    import sqlite3
    from ui.task_logic import common
    from ui.task_logic.job_failure_handlers import host_job_failure_handler

    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'RCON_ENABLED': False})
    with app.app_context():
        db.create_all()
        db.session.add(Host(id=1, name='h', provider='vultr', status=HostStatus.REBOOTING))
        db.session.commit()

    job = MagicMock()
    job.id = 'reboot-job'
    job.args = [1]
    job.meta = {'lock_token': 'old'}
    superseded = iter([False, True, True])
    real_commit = db.session.commit
    commits = {'n': 0}

    def _commit():
        commits['n'] += 1
        if commits['n'] == 1:
            raise OperationalError('COMMIT', {}, sqlite3.OperationalError('database is locked'))
        return real_commit()

    with patch('ui.create_app', return_value=app), \
         patch('ui.task_lock.lock_superseded', side_effect=lambda *a: next(superseded)), \
         patch.object(common.time, 'sleep'), \
         patch.object(db.session, 'commit', side_effect=_commit):
        host_job_failure_handler(job, None, RuntimeError, RuntimeError('boom'), None)

    with app.app_context():
        assert db.session.get(Host, 1).status == HostStatus.REBOOTING
