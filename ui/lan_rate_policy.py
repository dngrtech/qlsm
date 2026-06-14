"""Shared rules for 99k LAN rate compatibility."""

SUPPORTED_LAN_RATE_OS_TYPES = frozenset({"debian"})
OS_TYPE_ALIASES = {
    "debian12": "debian",
}
UNKNOWN_99K_LAN_RATE_MESSAGE = "99k LAN rate is only supported on Debian hosts."


def _normalized_os_type(host):
    os_type = getattr(host, "os_type", None)
    if not isinstance(os_type, str):
        return None
    normalized = os_type.strip().lower()
    if not normalized:
        return None
    return OS_TYPE_ALIASES.get(normalized, normalized)


def host_requires_os_check(host):
    """Returns True if the legacy iptables-based 99k LAN Rate path is in use
    on this host, meaning the Debian-only OS restriction must be enforced.
    Returns False for hosts migrated to the LD_PRELOAD hook mechanism."""
    return not bool(getattr(host, "lan_rate_uses_hook", False))


def host_supports_lan_rate(host):
    """Return whether the host supports enabling 99k LAN rate."""
    if not host_requires_os_check(host):
        return True
    # Legacy path: keep existing Debian-only check.
    return _normalized_os_type(host) in SUPPORTED_LAN_RATE_OS_TYPES


def lan_rate_unsupported_message(host):
    """Return the user-facing incompatibility message for the host, or None."""
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
