# ui/task_logic/ssh_command.py
#
# One read-only shell command on a host over plain ssh, for checks that run
# inside a web request. Replaces an Ansible ad-hoc run for those: Ansible
# spends 3-4s of CPU per call starting its own Python and shipping the module,
# which on a small controller turned a "Check for Updates" of a few hosts into
# 30s timeouts. ssh itself takes about a second, and a ControlMaster socket
# kept for a minute makes a repeated check of the same host take ~0.1s.

import logging
import os
import shlex
import subprocess
import tempfile

from ui.task_logic.access_permission_sync import _ssh_target_for_host

log = logging.getLogger(__name__)

CONTROL_PERSIST_SECONDS = 60


def _control_dir():
    # Unix socket paths are capped at ~104 bytes; %C below is a 40-char hash.
    path = os.path.join(tempfile.gettempdir(), 'qlsm-ssh')
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def build_host_ssh_command(host, command, connect_timeout=15, become=True):
    """argv running `command` (a shell string) on `host`, as root via
    `sudo -n` when `become` (what Ansible's --become did)."""
    remote = f"sudo -n sh -c {shlex.quote(command)}" if become else command
    return [
        'ssh',
        '-i', os.path.abspath(host.ssh_key_path),
        '-p', str(host.ssh_port),
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        '-o', 'LogLevel=ERROR',
        '-o', f'ConnectTimeout={connect_timeout}',
        '-o', 'ControlMaster=auto',
        '-o', f'ControlPath={_control_dir()}/%C',
        '-o', f'ControlPersist={CONTROL_PERSIST_SECONDS}',
        '-l', host.ssh_user,
        _ssh_target_for_host(host),
        remote,
    ]


def run_host_ssh_command(host, command, timeout=30, connect_timeout=15, become=True):
    """Runs `command` on `host` and returns (success, stdout, stderr).

    Bounded by `timeout` seconds overall so a hung connection cannot hold a
    web thread; `connect_timeout` is the SSH connect budget inside it, so an
    unreachable host still reports ssh's own message.
    """
    if not host:
        return False, "", "Internal Error: Host object not provided"
    if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
        return False, "", "Host details missing (IP, SSH key, or user)."

    try:
        argv = build_host_ssh_command(host, command, connect_timeout=connect_timeout, become=become)
    except Exception as e:
        log.exception(f"Could not build the ssh command for host {host.name}")
        return False, "", str(e)

    log.info(f"Executing ssh command for host {host.name}: {command!r}")
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log.warning(f"ssh command for host {host.name} timed out after {timeout}s")
        return False, "", f"Timed out after {timeout}s"
    except Exception as e:
        log.exception(f"ssh command for host {host.name} failed to run")
        return False, "", str(e)

    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or f"Command failed with exit code {result.returncode}"
        log.warning(f"ssh command for host {host.name} failed (rc={result.returncode}): {stderr[:300]}")
        return False, result.stdout or "", stderr
    return True, result.stdout or "", result.stderr or ""
