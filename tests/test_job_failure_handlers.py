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


@patch('ui.task_lock.release_lock')
def test_instance_failure_handler_releases_lock(mock_release):
    """Instance failure handler must release the entity lock."""
    from ui.task_logic.job_failure_handlers import instance_job_failure_handler

    mock_job = MagicMock()
    mock_job.id = 'test-job-789'
    mock_job.args = [1]
    mock_job.meta = {'lock_token': 'tok-abc'}

    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
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
    })
    with app.app_context():
        db.create_all()
        host = Host(id=1, name='test', provider='vultr', status=HostStatus.PROVISIONING)
        db.session.add(host)
        db.session.commit()

    with patch('ui.create_app', return_value=app):
        host_job_failure_handler(mock_job, None, RuntimeError, RuntimeError("boom"), None)

    mock_release.assert_called_once_with('host', 1, 'tok-xyz')
