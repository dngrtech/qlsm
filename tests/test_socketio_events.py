from types import SimpleNamespace
from unittest.mock import patch


def _make_host(provider, ip='203.0.113.10'):
    return SimpleNamespace(provider=provider, ip_address=ip)


@patch(
    'ui.socketio_events.resolve_self_host_management_target',
    return_value='host.docker.internal',
)
def test_rcon_target_for_self_host_uses_management_target(mock_target):
    from ui.socketio_events import _rcon_target_for_host

    target = _rcon_target_for_host(_make_host('self'))

    assert target == 'host.docker.internal'
    mock_target.assert_called_once_with()


@patch('ui.socketio_events.resolve_self_host_management_target')
def test_rcon_target_for_standalone_host_uses_ip_address(mock_target):
    from ui.socketio_events import _rcon_target_for_host

    target = _rcon_target_for_host(_make_host('standalone', ip='10.0.0.1'))

    assert target == '10.0.0.1'
    mock_target.assert_not_called()


@patch('ui.socketio_events.resolve_self_host_management_target')
def test_rcon_target_for_cloud_host_uses_ip_address(mock_target):
    from ui.socketio_events import _rcon_target_for_host

    target = _rcon_target_for_host(_make_host('vultr', ip='45.76.1.100'))

    assert target == '45.76.1.100'
    mock_target.assert_not_called()
