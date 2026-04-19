"""Shared rules for 99k LAN rate compatibility."""

SUPPORTED_LAN_RATE_OS_TYPES = frozenset({"debian"})
UBUNTU_99K_LAN_RATE_MESSAGE = "99k LAN rate is not compatible with Ubuntu."
UNKNOWN_99K_LAN_RATE_MESSAGE = "99k LAN rate is only supported on Debian hosts."


def _normalized_os_type(host):
    os_type = getattr(host, "os_type", None)
    if not isinstance(os_type, str):
        return None
    normalized = os_type.strip().lower()
    return normalized or None


def host_supports_lan_rate(host):
    """Return whether the host supports enabling 99k LAN rate."""
    return _normalized_os_type(host) in SUPPORTED_LAN_RATE_OS_TYPES


def lan_rate_unsupported_message(host):
    """Return the user-facing incompatibility message for the host."""
    if _normalized_os_type(host) == "ubuntu":
        return UBUNTU_99K_LAN_RATE_MESSAGE
    return UNKNOWN_99K_LAN_RATE_MESSAGE


def would_enable_unsupported_lan_rate(host, current_enabled, requested_enabled):
    """Return True when the requested change would enable 99k on Ubuntu."""
    return (
        not host_supports_lan_rate(host)
        and not bool(current_enabled)
        and bool(requested_enabled)
    )
