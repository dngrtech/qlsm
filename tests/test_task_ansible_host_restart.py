from unittest.mock import patch

from ui.database import create_host, get_host
from ui.models import HostStatus
from ui.task_logic.ansible_host_restart import restart_host_ansible_logic


@patch('ui.task_logic.ansible_host_restart._run_host_ansible_playbook', return_value=(True, 'ok', ''))
def test_restart_self_host_does_not_require_redis_server(mock_run, app):
    with app.app_context():
        host = create_host(
            name='self-restart-host',
            provider='self',
            status=HostStatus.ACTIVE,
            is_standalone=True,
        )

        assert restart_host_ansible_logic(host.id) is True
        assert mock_run.call_args.kwargs['extravars']['critical_services'] == ['ssh']


@patch('ui.task_logic.ansible_host_restart._host_recovered_after_reboot', return_value=True, create=True)
@patch('ui.task_logic.ansible_host_restart._run_host_ansible_playbook', return_value=(False, '', 'ssh timed out'))
def test_failed_restart_playbook_marks_host_active_when_recovery_probe_succeeds(mock_run, mock_recovered, app):
    with app.app_context():
        host = create_host(
            name='recovered-restart-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            is_standalone=True,
            ssh_user='debian',
            ssh_key_path='/tmp/test-key',
            ssh_port=22,
            ip_address='203.0.113.10',
        )

        assert restart_host_ansible_logic(host.id) is True

        refreshed = get_host(host.id)
        assert refreshed.status == HostStatus.ACTIVE
        assert 'recovered after reboot probe' in refreshed.logs
        mock_recovered.assert_called_once()


@patch('ui.task_logic.ansible_host_restart._host_recovered_after_reboot', return_value=False, create=True)
@patch('ui.task_logic.ansible_host_restart._run_host_ansible_playbook', return_value=(False, '', 'ssh timed out'))
def test_failed_restart_playbook_keeps_error_when_recovery_probe_fails(mock_run, mock_recovered, app):
    with app.app_context():
        host = create_host(
            name='failed-restart-host',
            provider='standalone',
            status=HostStatus.ACTIVE,
            is_standalone=True,
            ssh_user='debian',
            ssh_key_path='/tmp/test-key',
            ssh_port=22,
            ip_address='203.0.113.11',
        )

        assert restart_host_ansible_logic(host.id) is False

        refreshed = get_host(host.id)
        assert refreshed.status == HostStatus.ERROR
        mock_recovered.assert_called_once()
