"""Shared rules for 99k LAN rate compatibility."""

UBUNTU_99K_LAN_RATE_MESSAGE = "99k LAN rate is not compatible with Ubuntu."


def host_supports_lan_rate(host):
    """Return whether the host supports enabling 99k LAN rate."""
    return getattr(host, "os_type", None) != "ubuntu"


def lan_rate_unsupported_message(host):
    """Return the user-facing incompatibility message for the host."""
    _ = host
    return UBUNTU_99K_LAN_RATE_MESSAGE


def would_enable_unsupported_lan_rate(host, current_enabled, requested_enabled):
    """Return True when the requested change would enable 99k on Ubuntu."""
    return (
        not host_supports_lan_rate(host)
        and not bool(current_enabled)
        and bool(requested_enabled)
    )
