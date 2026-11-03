import logging
import os
import subprocess

from ui import db
from ui.models import Host
from ui.standalone_ssh import _parse_os_release

log = logging.getLogger(__name__)


def _read_os_release(host):
    if not host.ssh_key_path or not host.ip_address or not host.ssh_user:
        return None
    cmd = [
        'ssh',
        '-i', os.path.abspath(host.ssh_key_path),
        '-p', str(host.ssh_port),
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=8',
        '-l', host.ssh_user,
        host.ip_address,
        'cat /etc/os-release',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Could not read os-release on host %s: %s", host.name, exc)
        return None
    if result.returncode != 0:
        log.warning("Could not read os-release on host %s: %s", host.name, result.stderr.strip())
        return None
    return result.stdout


def detect_host_os_version(host):
    """Return the host's /etc/os-release VERSION_ID, or None if it can't be read."""
    content = _read_os_release(host)
    if not content:
        return None
    return _parse_os_release(content).get('VERSION_ID', '').strip() or None


def backfill_host_os_version_logic(host_id):
    """Fill Host.os_version for a host created before the column existed.

    Self hosts are skipped: their OS is detected from inside the QLSM
    container, which can report the container's OS instead of the host's.
    """
    host = db.session.get(Host, host_id)
    if host is None or host.os_version or host.provider == 'self':
        return None
    version = detect_host_os_version(host)
    if version:
        host.os_version = version
        db.session.commit()
    return version
