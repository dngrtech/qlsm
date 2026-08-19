from types import SimpleNamespace

from ui.lan_rate_policy import (
    host_supports_lan_rate,
    lan_rate_always_on,
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


# Runtime-aware rules. The helper is named apart from _host() above because that
# one takes positional args and redefining it here would rebind it for every
# test in the module.
def _runtime_host(**overrides):
    base = {'os_type': 'ubuntu', 'lan_rate_uses_hook': True, 'runtime': 'minqlx'}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_minqlxtended_reports_lan_rate_as_always_on():
    """The runtime hooks Sys_IsLANAddress itself, unconditionally
    (src/server/hooks.c:142), so 99k is on whatever the toggle says."""
    assert lan_rate_always_on(_runtime_host(runtime='minqlxtended')) is True


def test_minqlx_never_reports_lan_rate_as_always_on():
    assert lan_rate_always_on(_runtime_host(runtime='minqlx')) is False
    assert lan_rate_always_on(_runtime_host(runtime=None)) is False


def test_minqlxtended_explains_why_the_toggle_is_fixed():
    message = lan_rate_unsupported_message(_runtime_host(runtime='minqlxtended'))
    assert 'minqlxtended' in message


def test_minqlxtended_still_counts_as_supporting_lan_rate():
    """Reporting it unsupported would make the UI offer to 'fix' something that
    is already on, and would block a saved instance config from round-tripping."""
    assert host_supports_lan_rate(_runtime_host(runtime='minqlxtended')) is True


def test_enabling_lan_rate_on_minqlxtended_is_never_blocked():
    assert would_enable_unsupported_lan_rate(
        _runtime_host(runtime='minqlxtended'), current_enabled=False, requested_enabled=True
    ) is False


def test_legacy_debian_behaviour_is_unchanged():
    legacy = _runtime_host(os_type='debian', lan_rate_uses_hook=False)
    assert host_supports_lan_rate(legacy) is True
    assert lan_rate_unsupported_message(legacy) is None
    assert lan_rate_always_on(legacy) is False


def test_legacy_ubuntu_still_gets_the_migration_hint():
    legacy = _runtime_host(os_type='ubuntu', lan_rate_uses_hook=False)
    assert host_supports_lan_rate(legacy) is False
    assert 'Re-run Host Setup' in lan_rate_unsupported_message(legacy)
