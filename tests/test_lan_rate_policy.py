from types import SimpleNamespace

from ui.lan_rate_policy import (
    host_supports_lan_rate,
    lan_rate_unsupported_message,
    would_enable_unsupported_lan_rate,
    UNKNOWN_99K_LAN_RATE_MESSAGE,
)


def test_host_supports_lan_rate_for_debian():
    assert host_supports_lan_rate(SimpleNamespace(os_type='debian')) is True


def test_host_supports_lan_rate_for_legacy_debian12():
    assert host_supports_lan_rate(SimpleNamespace(os_type='debian12')) is True
    assert would_enable_unsupported_lan_rate(
        SimpleNamespace(os_type='debian12'),
        current_enabled=False,
        requested_enabled=True,
    ) is False


def test_host_supports_lan_rate_for_ubuntu():
    assert host_supports_lan_rate(SimpleNamespace(os_type='ubuntu')) is False


def test_host_supports_lan_rate_for_unknown_os():
    assert host_supports_lan_rate(SimpleNamespace(os_type=None)) is False
    assert host_supports_lan_rate(SimpleNamespace(os_type='centos')) is False


def test_would_enable_unsupported_lan_rate_allows_disabling():
    host = SimpleNamespace(os_type='ubuntu')
    assert would_enable_unsupported_lan_rate(
        host,
        current_enabled=True,
        requested_enabled=False,
    ) is False


def test_would_enable_unsupported_lan_rate_blocks_unknown_os():
    host = SimpleNamespace(os_type=None)
    assert would_enable_unsupported_lan_rate(
        host,
        current_enabled=False,
        requested_enabled=True,
    ) is True


def test_lan_rate_unsupported_message_matches_product_copy():
    msg = lan_rate_unsupported_message(SimpleNamespace(os_type='ubuntu'))
    assert msg is not None and msg != ""
    assert "Re-run Host Setup" in msg
    assert "host actions menu" in msg


def test_lan_rate_unsupported_message_is_generic_for_unknown_os():
    assert lan_rate_unsupported_message(SimpleNamespace(os_type=None)) == UNKNOWN_99K_LAN_RATE_MESSAGE


from unittest.mock import MagicMock

from ui.lan_rate_policy import (
    host_requires_os_check,
)


def _host(os_type, lan_rate_uses_hook):
    h = MagicMock()
    h.os_type = os_type
    h.lan_rate_uses_hook = lan_rate_uses_hook
    return h


def test_host_requires_os_check_false_when_migrated():
    assert host_requires_os_check(_host("ubuntu", True)) is False
    assert host_requires_os_check(_host("debian", True)) is False


def test_host_requires_os_check_true_when_legacy():
    assert host_requires_os_check(_host("ubuntu", False)) is True
    assert host_requires_os_check(_host("debian", False)) is True


def test_host_supports_lan_rate_true_for_any_os_when_migrated():
    assert host_supports_lan_rate(_host("ubuntu", True)) is True
    assert host_supports_lan_rate(_host("anything-else", True)) is True


def test_lan_rate_unsupported_message_empty_when_migrated():
    assert lan_rate_unsupported_message(_host("ubuntu", True)) in (None, "")


def test_lan_rate_unsupported_message_actionable_for_legacy_ubuntu():
    msg = lan_rate_unsupported_message(_host("ubuntu", False))
    assert msg is not None and msg != ""
    assert "Re-run Host Setup" in msg
    assert "host actions menu" in msg
