from unittest.mock import patch

from ui.database import create_host
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
