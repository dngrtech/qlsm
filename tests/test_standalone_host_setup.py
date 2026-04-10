from types import SimpleNamespace
from unittest.mock import patch

from ui.task_logic.standalone_host_setup import _generate_standalone_inventory


def _host(provider):
    return SimpleNamespace(id=1, name='test-host', provider=provider)


@patch('ui.task_logic.standalone_host_setup.generate_standalone_inventory', return_value='/tmp/self.yml')
@patch('ui.task_logic.standalone_host_setup.detect_docker_host_ip', return_value='172.18.0.1')
def test_generate_inventory_uses_gateway_for_self_host(mock_detect_ip, mock_generate_inventory):
    host = _host('self')

    assert _generate_standalone_inventory(host) == '/tmp/self.yml'
    mock_detect_ip.assert_called_once_with()
    mock_generate_inventory.assert_called_once_with(host, ansible_host='172.18.0.1')


@patch('ui.task_logic.standalone_host_setup.generate_standalone_inventory', return_value='/tmp/standalone.yml')
@patch('ui.task_logic.standalone_host_setup.detect_docker_host_ip')
def test_generate_inventory_skips_gateway_detection_for_standalone_host(
    mock_detect_ip, mock_generate_inventory
):
    host = _host('standalone')

    assert _generate_standalone_inventory(host) == '/tmp/standalone.yml'
    mock_detect_ip.assert_not_called()
    mock_generate_inventory.assert_called_once_with(host, ansible_host=None)
