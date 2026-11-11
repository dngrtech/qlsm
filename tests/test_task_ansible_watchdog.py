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


@pytest.mark.parametrize('value, ok', [
    (60, True), (180, True), (3600, True),
    (59, False), (3601, False), (0, False), (True, False), ('180', False), (180.0, False),
])
def test_dead_confirm_is_validated_with_a_floor_of_one_minute(value, ok):
    from ui.routes.host_routes import _validate_watchdog_config

    config, error = _validate_watchdog_config({'dead_confirm': value})

    if ok:
        assert error is None and config == {'dead_confirm': value}
    else:
        assert config is None and 'dead_confirm' in error['message']


def test_dead_confirm_reaches_the_playbook_and_is_saved(app, mock_run_playbook, mock_get_current_job):
    mock_run_playbook.return_value = (True, 'ok', '')
    with app.app_context():
        host = create_host(name='wd-dead-confirm', provider='vultr', status=HostStatus.CONFIGURING)

        assert configure_host_watchdog_logic(host.id, True, {'dead_confirm': 300}) is True

        assert mock_run_playbook.call_args.kwargs['extravars']['watchdog_dead_confirm'] == 300
        assert json.loads(get_host(host.id).watchdog_config) == {'dead_confirm': 300}


@pytest.mark.parametrize('extra, expected', [({}, '180'), ({'watchdog_dead_confirm': 300}, '300')])
def test_unit_template_passes_dead_confirm_to_the_script(extra, expected):
    import os
    from jinja2 import Environment, FileSystemLoader

    templates = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ansible', 'templates')
    unit = Environment(loader=FileSystemLoader(templates)).get_template('ql-watchdog.service.j2').render(
        watchdog_dir='/opt/ql-watchdog', **extra)

    assert f'Environment=QL_WATCHDOG_DEAD_CONFIRM={expected}\n' in unit
