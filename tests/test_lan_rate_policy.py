from types import SimpleNamespace

from ui.lan_rate_policy import (
    host_supports_lan_rate,
    lan_rate_unsupported_message,
    would_enable_unsupported_lan_rate,
)


def test_host_supports_lan_rate_for_debian():
    assert host_supports_lan_rate(SimpleNamespace(os_type='debian')) is True


def test_host_supports_lan_rate_for_ubuntu():
    assert host_supports_lan_rate(SimpleNamespace(os_type='ubuntu')) is False


def test_would_enable_unsupported_lan_rate_allows_disabling():
    host = SimpleNamespace(os_type='ubuntu')
    assert would_enable_unsupported_lan_rate(
        host,
        current_enabled=True,
        requested_enabled=False,
    ) is False


def test_lan_rate_unsupported_message_matches_product_copy():
    assert (
        lan_rate_unsupported_message(SimpleNamespace(os_type='ubuntu'))
        == '99k LAN rate is not compatible with Ubuntu.'
    )
