"""A setup task that dies must leave the host in ERROR, not in CONFIGURING."""
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from ui.database import create_host
from ui.models import Host, HostStatus
from ui.task_logic.common import record_host_error


def _locked():
    return OperationalError('UPDATE host SET logs=?', {}, Exception('database is locked'))


@patch('time.sleep')
def test_record_host_error_retries_after_a_locked_write(mock_sleep, app):
    from ui import db

    with app.app_context():
        host = create_host(name='record-error-host', provider='vultr', status=HostStatus.CONFIGURING)
        host_id = host.id
        real_commit = db.session.commit
        calls = {'n': 0}

        def flaky_commit():
            calls['n'] += 1
            if calls['n'] == 1:
                raise _locked()
            return real_commit()

        with patch.object(db.session, 'commit', side_effect=flaky_commit):
            assert record_host_error(host_id, 'boom') is True

        db.session.expire_all()
        stored = db.session.get(Host, host_id)
        assert stored.status == HostStatus.ERROR
        assert 'boom' in stored.logs
        assert calls['n'] == 2
        mock_sleep.assert_called_once()


@patch('time.sleep')
def test_record_host_error_gives_up_after_the_attempts(mock_sleep, app):
    from ui import db

    with app.app_context():
        host = create_host(name='record-error-host-2', provider='vultr', status=HostStatus.CONFIGURING)
        with patch.object(db.session, 'commit', side_effect=_locked()):
            assert record_host_error(host.id, 'boom', attempts=2) is False


def test_record_host_error_for_a_missing_host_is_a_noop(app):
    with app.app_context():
        assert record_host_error(999999, 'boom') is False


def test_standalone_setup_raises_and_marks_the_host_error(app):
    from ui.task_logic import standalone_host_setup as module

    with app.app_context():
        host = create_host(
            name='standalone-fails', provider='standalone', status=HostStatus.CONFIGURING,
            ip_address='203.0.113.7', is_standalone=True, ssh_port=22,
            ssh_key_path='/tmp/test_key', ssh_user='root',
        )
        host_id = host.id
        job = type('Job', (), {'id': 'job-1'})()
        with patch.object(module, 'get_current_job', return_value=job), \
                patch.object(module, '_generate_standalone_inventory', side_effect=RuntimeError('inventory exploded')):
            with pytest.raises(RuntimeError, match='inventory exploded'):
                module.setup_standalone_host_logic(host_id, rerun=True)

        from ui import db
        db.session.expire_all()
        stored = db.session.get(Host, host_id)
        assert stored.status == HostStatus.ERROR
        assert 'inventory exploded' in stored.logs
