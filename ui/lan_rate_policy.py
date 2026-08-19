"""Shared rules for 99k LAN rate compatibility."""
from ui.runtime import MINQLXTENDED, host_runtime

SUPPORTED_LAN_RATE_OS_TYPES = frozenset({"debian"})
OS_TYPE_ALIASES = {
    "debian12": "debian",
}
UNKNOWN_99K_LAN_RATE_MESSAGE = "99k LAN rate is only supported on Debian hosts."
ALWAYS_ON_LAN_RATE_MESSAGE = (
    "99k LAN rate is always on for minqlxtended hosts — the runtime treats "
    "every client as a LAN address itself, so this setting cannot be changed."
)


def _normalized_os_type(host):
    os_type = getattr(host, "os_type", None)
    if not isinstance(os_type, str):
        return None
    normalized = os_type.strip().lower()
    if not normalized:
        return None
    return OS_TYPE_ALIASES.get(normalized, normalized)


def lan_rate_always_on(host):
    """Whether the runtime provides 99k LAN rate unconditionally.

    minqlxtended hooks Sys_IsLANAddress with no cvar gate, and QLSM excludes
    force_rate.so on it (ui/runtime.py) because a second patch of the same
    prologue can exit the server. Neither the hook path nor the legacy iptables
    path can change the behaviour there, so the toggle is inert in both
    directions -- note the reconfigure task still runs (and still restarts the
    server) if something writes the field anyway; see docs/technical.md.
    """
    return host_runtime(host) == MINQLXTENDED


def host_requires_os_check(host):
    """Returns True if the legacy iptables-based 99k LAN Rate path is in use
    on this host, meaning the Debian-only OS restriction must be enforced.
    Returns False for hosts migrated to the LD_PRELOAD hook mechanism."""
    return not bool(getattr(host, "lan_rate_uses_hook", False))


def host_supports_lan_rate(host):
    """Return whether the host supports enabling 99k LAN rate."""
    if lan_rate_always_on(host):
        # Fixed on, not unsupported: reporting False here would make the UI
        # offer to "fix" a host that already has it.
        return True
    if not host_requires_os_check(host):
        return True
    # Legacy path: keep existing Debian-only check.
    return _normalized_os_type(host) in SUPPORTED_LAN_RATE_OS_TYPES


def lan_rate_unsupported_message(host):
    """Return the user-facing incompatibility message for the host, or None."""
    if lan_rate_always_on(host):
        return ALWAYS_ON_LAN_RATE_MESSAGE
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
