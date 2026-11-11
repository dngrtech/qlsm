import json

import pytest
from unittest.mock import patch, MagicMock
from ui.task_logic.ansible_watchdog import configure_host_watchdog_logic, enable_default_watchdog
from ui.models import HostStatus
from ui.database import create_host, get_host


@pytest.fixture
def mock_run_playbook():
    with patch('ui.task_logic.ansible_watchdog._run_host_ansible_playbook') as mock:
        yield mock


@pytest.fixture
def mock_get_current_job():
    with patch('ui.task_logic.ansible_watchdog.get_current_job') as mock:
        mock_job = MagicMock()
        mock_job.id = 'test-watchdog-job-id'
        mock.return_value = mock_job
        yield mock


def test_configure_host_watchdog_enable(app, mock_run_playbook, mock_get_current_job):
    mock_run_playbook.return_value = (True, "mock stdout", "")

    with app.app_context():
        host = create_host(name='test-host-watchdog', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

        result = configure_host_watchdog_logic(host_id, True, {'strikes': 5, 'forensics': False})

        assert result is True
        mock_run_playbook.assert_called_once()
        args, kwargs = mock_run_playbook.call_args
        assert kwargs['playbook_name'] == 'configure_watchdog.yml'
        assert kwargs['extravars'] == {
            'watchdog_enabled': True,
            'watchdog_strikes': 5,
            'watchdog_forensics': False,
        }

        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ACTIVE
        assert updated_host.watchdog_enabled is True
        assert json.loads(updated_host.watchdog_config) == {'strikes': 5, 'forensics': False}


def test_configure_host_watchdog_disable(app, mock_run_playbook, mock_get_current_job):
    mock_run_playbook.return_value = (True, "mock stdout", "")

    with app.app_context():
        host = create_host(name='test-host-watchdog2', provider='vultr', status=HostStatus.ACTIVE,
                            watchdog_enabled=True, watchdog_config=json.dumps({'strikes': 5}))
        host_id = host.id

        result = configure_host_watchdog_logic(host_id, False)

        assert result is True
        mock_run_playbook.assert_called_once()
        args, kwargs = mock_run_playbook.call_args
        assert kwargs['extravars'] == {'watchdog_enabled': False}

        updated_host = get_host(host_id)
        assert updated_host.watchdog_enabled is False
        assert updated_host.watchdog_config is None


def test_configure_host_watchdog_ansible_failure(app, mock_run_playbook, mock_get_current_job):
    mock_run_playbook.return_value = (False, "mock stdout", "error running playbook")

    with app.app_context():
        host = create_host(name='test-host-watchdog3', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

        result = configure_host_watchdog_logic(host_id, True)

        assert result is False
        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ERROR
        assert updated_host.watchdog_enabled is False  # Not persisted on failure


def test_configure_host_watchdog_host_not_found(app):
    with app.app_context():
        result = configure_host_watchdog_logic(99999, True)
        assert result is False


def test_enable_default_watchdog_turns_it_on_with_default_settings(app, mock_run_playbook):
    mock_run_playbook.return_value = (True, 'ok', '')
    with app.app_context():
        host = create_host(name='wd-default', provider='vultr', status=HostStatus.PROVISIONED_PENDING_SETUP)

        assert enable_default_watchdog(host) is True

        assert host.watchdog_enabled is True
        assert host.watchdog_config is None
        assert 'ql-watchdog enabled' in host.logs
        kwargs = mock_run_playbook.call_args.kwargs
        assert kwargs['playbook_name'] == 'configure_watchdog.yml'
        assert kwargs['extravars'] == {'watchdog_enabled': True}


@pytest.mark.parametrize('outcome', [
    (False, '', 'apt failed'),
    (None, 'Host details missing'),
    RuntimeError('ssh exploded'),
])
def test_enable_default_watchdog_failure_never_fails_host_setup(app, mock_run_playbook, outcome):
    if isinstance(outcome, Exception):
        mock_run_playbook.side_effect = outcome
    else:
        mock_run_playbook.return_value = outcome
    with app.app_context():
        host = create_host(name='wd-default-fail', provider='vultr', status=HostStatus.PROVISIONED_PENDING_SETUP)

        assert enable_default_watchdog(host) is False

        assert host.watchdog_enabled is False
        assert host.status == HostStatus.PROVISIONED_PENDING_SETUP
        assert 'Could not enable ql-watchdog' in host.logs
