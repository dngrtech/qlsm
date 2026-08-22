"""Shared rules for 99k LAN rate compatibility."""
from ui.runtime import MINQLXTENDED, host_runtime

SUPPORTED_LAN_RATE_OS_TYPES = frozenset({"debian"})
OS_TYPE_ALIASES = {
    "debian12": "debian",
}
UNKNOWN_99K_LAN_RATE_MESSAGE = "99k LAN rate is only supported on Debian hosts."
FORCED_LAN_RATE_MESSAGE = (
    "QLSM runs minqlxtended hosts at 99k LAN rate and does not offer 25k on "
    "this runtime, so this setting is fixed on."
)


def _normalized_os_type(host):
    os_type = getattr(host, "os_type", None)
    if not isinstance(os_type, str):
        return None
    normalized = os_type.strip().lower()
    if not normalized:
        return None
    return OS_TYPE_ALIASES.get(normalized, normalized)


def lan_rate_forced_on(host):
    """Whether QLSM fixes 99k LAN rate on for this host.

    This is a QLSM product decision, not something the engine does on its own:
    QLSM only ever configures minqlxtended instances with sv_lanForceRate 1, so
    25k is not a state it offers on that runtime. The toggle itself is real on
    both runtimes -- _build_qlds_args_string() has always emitted the cvar from
    the stored flag -- which is why the decision has to be enforced here.
    """
    return host_runtime(host) == MINQLXTENDED


def effective_lan_rate(instance):
    """The 99k LAN rate state QLSM actually configures for this instance.

    Derived rather than stored: instance.lan_rate_enabled keeps whatever the
    operator set, so a preset saved from a minqlxtended instance does not carry
    99k onto a minqlx host, where the toggle is the operator's to choose. Every
    surface that shows the setting must render this value, not the column, or
    the UI and the emitted cvar drift apart.
    """
    if lan_rate_forced_on(getattr(instance, 'host', None)):
        return True
    return bool(getattr(instance, 'lan_rate_enabled', False))


def host_requires_os_check(host):
    """Returns True if the legacy iptables-based 99k LAN Rate path is in use
    on this host, meaning the Debian-only OS restriction must be enforced.
    Returns False for hosts migrated to the LD_PRELOAD hook mechanism."""
    return not bool(getattr(host, "lan_rate_uses_hook", False))


def host_supports_lan_rate(host):
    """Return whether the host supports enabling 99k LAN rate."""
    if lan_rate_forced_on(host):
        # Already on by policy. Reporting False here would make the UI offer to
        # "fix" a host that is running exactly what QLSM intends.
        return True
    if not host_requires_os_check(host):
        return True
    # Legacy path: keep existing Debian-only check.
    return _normalized_os_type(host) in SUPPORTED_LAN_RATE_OS_TYPES


def lan_rate_unsupported_message(host):
    """Return the user-facing reason the toggle is not the operator's to set on
    this host, or None when it is freely settable."""
    if lan_rate_forced_on(host):
        return FORCED_LAN_RATE_MESSAGE
    if not host_requires_os_check(host):
        return None
    # Legacy hosts: Debian-only restriction with migration hint for Ubuntu.
    os_type = _normalized_os_type(host)
    if os_type in SUPPORTED_LAN_RATE_OS_TYPES:
        return None
    if os_type == "ubuntu":
        return (
            "99k LAN Rate currently requires Debian on this host. To enable it "
            "on Ubuntu (and other OSes), run 'Re-run Host Setup' from the host "
            "actions menu — this migrates the host to the new LD_PRELOAD hook "
            "mechanism that works on any OS."
        )
    return UNKNOWN_99K_LAN_RATE_MESSAGE


def would_enable_unsupported_lan_rate(host, current_enabled, requested_enabled):
    """Return True when the requested change would enable 99k on Ubuntu."""
    return (
        not host_supports_lan_rate(host)
        and not bool(current_enabled)
        and bool(requested_enabled)
    )
