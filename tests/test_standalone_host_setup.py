from types import SimpleNamespace
from unittest.mock import patch

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
