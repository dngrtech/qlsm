import pytest
from unittest.mock import patch, MagicMock
from ui.task_logic.ansible_host_auto_restart import configure_host_auto_restart_logic
from ui.models import HostStatus
from ui.database import create_host, get_host

@pytest.fixture
def mock_run_playbook():
    with patch('ui.task_logic.ansible_host_auto_restart._run_host_ansible_playbook') as mock:
        yield mock

@pytest.fixture
def mock_get_current_job():
    with patch('ui.task_logic.ansible_host_auto_restart.get_current_job') as mock:
        mock_job = MagicMock()
        mock_job.id = 'test-auto-restart-job-id'
        mock.return_value = mock_job
        yield mock

def test_configure_host_auto_restart_success(app, mock_run_playbook, mock_get_current_job):
    mock_run_playbook.return_value = (True, "mock stdout", "")
    app.config['ANSIBLE_PLAYBOOKS_DIR'] = '/mock/dir'
    
    with app.app_context():
        host = create_host(name='test-host-restart', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

        result = configure_host_auto_restart_logic(host_id, '*-*-* 04:00:00')
        
        assert result is True
        mock_run_playbook.assert_called_once()
        args, kwargs = mock_run_playbook.call_args
        assert kwargs['extravars'] == {'on_calendar': '*-*-* 04:00:00'}
        
        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ACTIVE
        assert updated_host.auto_restart_schedule == '*-*-* 04:00:00'
        assert 'Auto-restart configured successfully' in updated_host.logs


def test_configure_host_auto_restart_remove_schedule(app, mock_run_playbook, mock_get_current_job):
    mock_run_playbook.return_value = (True, "mock stdout", "")
    app.config['ANSIBLE_PLAYBOOKS_DIR'] = '/mock/dir'
    
    with app.app_context():
        host = create_host(name='test-host-restart2', provider='vultr', status=HostStatus.ACTIVE,
                           auto_restart_schedule='*-*-* 04:00:00')
        host_id = host.id

        result = configure_host_auto_restart_logic(host_id, None)

        assert result is True
        mock_run_playbook.assert_called_once()
        args, kwargs = mock_run_playbook.call_args
        assert kwargs['extravars'] == {}

        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ACTIVE
        assert updated_host.auto_restart_schedule is None
        assert 'Auto-restart configured successfully' in updated_host.logs


def test_configure_host_auto_restart_ansible_failure(app, mock_run_playbook, mock_get_current_job):
    mock_run_playbook.return_value = (False, "mock stdout", "error running playbook")
    app.config['ANSIBLE_PLAYBOOKS_DIR'] = '/mock/dir'
    
    with app.app_context():
        host = create_host(name='test-host-restart3', provider='vultr', status=HostStatus.ACTIVE)
        host_id = host.id

        result = configure_host_auto_restart_logic(host_id, '*-*-* 04:00:00')
        
        assert result is False
        mock_run_playbook.assert_called_once()
        
        updated_host = get_host(host_id)
        assert updated_host.status == HostStatus.ERROR
        assert updated_host.auto_restart_schedule is None  # Not persisted on failure
        assert 'Auto-restart configuration failed' in updated_host.logs


def test_configure_host_auto_restart_host_not_found(app):
    with app.app_context():
        result = configure_host_auto_restart_logic(99999, '*-*-* 04:00:00')
        assert result is False
