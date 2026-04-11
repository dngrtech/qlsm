from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from ui.models import HostStatus
from ui.task_logic.standalone_host_setup import _generate_standalone_inventory


def _host(provider):
    return SimpleNamespace(id=1, name='test-host', provider=provider, ip_address='203.0.113.10')


@patch('ui.task_logic.standalone_host_setup.generate_standalone_inventory', return_value='/tmp/self.yml')
@patch(
    'ui.task_logic.standalone_host_setup.resolve_self_host_management_target',
    return_value='host.docker.internal',
)
def test_generate_inventory_uses_management_target_for_self_host(mock_target, mock_generate_inventory):
    host = _host('self')

    assert _generate_standalone_inventory(host) == ('/tmp/self.yml', 'host.docker.internal')
    mock_target.assert_called_once_with()
    mock_generate_inventory.assert_called_once_with(host, ansible_host='host.docker.internal')


@patch('ui.task_logic.standalone_host_setup.generate_standalone_inventory', return_value='/tmp/standalone.yml')
@patch('ui.task_logic.standalone_host_setup.resolve_self_host_management_target')
def test_generate_inventory_keeps_connect_address_for_standalone_host(
    mock_target, mock_generate_inventory
):
    host = _host('standalone')

    assert _generate_standalone_inventory(host) == ('/tmp/standalone.yml', host.ip_address)
    mock_target.assert_not_called()
    mock_generate_inventory.assert_called_once_with(host, ansible_host=host.ip_address)


@patch('ui.task_logic.standalone_host_setup.db.session')
@patch('ui.task_logic.standalone_host_setup.append_log')
@patch('ui.task_logic.standalone_host_setup.subprocess.run')
def test_wait_for_ssh_fails_when_inventory_host_pattern_does_not_match(
    mock_run, mock_append_log, mock_session
):
    from ui.task_logic.standalone_host_setup import _wait_for_ssh

    host = SimpleNamespace(id=1, name='234234', status=HostStatus.PROVISIONED_PENDING_SETUP)
    mock_run.return_value = MagicMock(
        stdout='',
        stderr='[WARNING]: Could not match supplied host pattern, ignoring: 234234\n',
    )

    assert _wait_for_ssh(host, '/tmp/test.yml') is False
    assert host.status == HostStatus.ERROR
    mock_append_log.assert_called_once_with(
        host,
        'Host setup failed: [WARNING]: Could not match supplied host pattern, ignoring: 234234',
    )
    mock_session.commit.assert_called_once_with()
