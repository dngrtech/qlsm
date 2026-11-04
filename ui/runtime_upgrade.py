"""Eligibility rules for the one-click minqlx -> minqlxtended host upgrade."""
import re

from ui.runtime import MINQLX, normalize_runtime

UPGRADE_TARGET_RUNTIME = 'minqlxtended'

_MIN_UBUNTU = (24, 4)
_OS_DISPLAY = {'debian': 'Debian', 'ubuntu': 'Ubuntu'}


def _result(visible, enabled, reason=None):
    return {'visible': visible, 'enabled': enabled, 'reason': reason}


def _disabled(reason):
    return _result(True, False, reason)


def _parse_version(value):
    """'24.04' -> (24, 4); None if not a dotted numeric version."""
    if not isinstance(value, str) or not re.fullmatch(r'\d+(\.\d+)*', value.strip()):
        return None
    return tuple(int(part) for part in value.strip().split('.'))


def _enum_value(value):
    return getattr(value, 'value', value)


def upgrade_eligibility(host, *, assume_status=None):
    """Decide whether the upgrade action is shown and enabled for a host.

    Checks run in order (runtime, status, OS, instances); only the first
    failure is reported. ``assume_status`` replaces ``host.status`` for the
    status check only, for callers that hold the host in a transitional state
    under their own reservation.
    """
    from ui.models import HostStatus, InstanceStatus

    if normalize_runtime(host.runtime) != MINQLX:
        return _result(False, False)

    status = assume_status if assume_status is not None else host.status
    if status != HostStatus.ACTIVE:
        current = _enum_value(status)
        label = str(current).upper() if current else 'UNKNOWN'
        return _disabled(f'Host must be ACTIVE to upgrade; current status is {label}')

    os_type = (host.os_type or '').strip().lower()
    version = _parse_version(host.os_version)
    if not os_type or version is None:
        return _disabled('minqlxtended requires Ubuntu 24.04 or newer; OS version unknown')
    if os_type != 'ubuntu' or version < _MIN_UBUNTU:
        display = _OS_DISPLAY.get(os_type, host.os_type)
        return _disabled(
            f'minqlxtended requires Ubuntu 24.04 or newer; this host runs {display} {host.os_version}'
        )

    allowed = (InstanceStatus.RUNNING, InstanceStatus.STOPPED)
    for instance in host.instances:
        if instance.status not in allowed:
            label = str(_enum_value(instance.status)).upper()
            return _disabled(
                f'Instance {instance.name} is {label}; all instances must be RUNNING or STOPPED'
            )

    return _result(True, True)
