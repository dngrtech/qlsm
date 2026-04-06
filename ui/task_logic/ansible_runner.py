import json
import logging
import os
import select
import subprocess

from ui import db
from ui.models import InstanceStatus
from .common import append_log

log = logging.getLogger(__name__)


class SimpleAnsibleResult:
    """Simple class to mimic ansible-runner's result structure"""
    def __init__(self, rc, stdout, stderr=None):
        self.rc = rc
        self._stdout = stdout
        self._stderr = stderr or ""
        self.status = "successful" if rc == 0 else "failed"

    def stdout(self):
        return self._stdout


def _drain_remaining(process, stdout_lines, stderr_lines):
    """Drain any remaining output from subprocess pipes after process exits."""
    for line in process.stdout:
        stdout_lines.append(line)
        log.debug("ansible-out: %s", line.rstrip())
    for line in process.stderr:
        stderr_lines.append(line)
        log.debug("ansible-err: %s", line.rstrip())


def _stream_output(process):
    """Stream subprocess stdout/stderr via select(), returning collected output."""
    stdout_lines = []
    stderr_lines = []
    try:
        while True:
            reads = [process.stdout.fileno(), process.stderr.fileno()]
            ret = select.select(reads, [], [])

            for fd in ret[0]:
                if fd == process.stdout.fileno():
                    read = process.stdout.readline()
                    if read:
                        log.debug("ansible-out: %s", read.rstrip())
                        stdout_lines.append(read)
                if fd == process.stderr.fileno():
                    read = process.stderr.readline()
                    if read:
                        log.debug("ansible-err: %s", read.rstrip())
                        stderr_lines.append(read)

            if process.poll() is not None:
                break

        # Drain any remaining buffered output after process exits
        _drain_remaining(process, stdout_lines, stderr_lines)
    finally:
        process.stdout.close()
        process.stderr.close()

    return "".join(stdout_lines), "".join(stderr_lines)


def _run_ansible_playbook(instance, playbook_name, extravars=None):
    """
    Helper function to run an Ansible playbook via direct subprocess call.
    Accepts the instance object directly.
    """
    if not instance:
        log.error("Instance object not provided to _run_ansible_playbook.")
        return None, "Internal Error: Instance object not provided"

    host = instance.host
    if not host:
        log.error(f"Host not found for instance {instance.id}.")
        append_log(instance, "Task failed: Associated host not found.")
        instance.status = InstanceStatus.ERROR
        return None, "Host not found"

    if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
        log.error(f"Host {host.id} is missing required details (IP, SSH key path, or user) for Ansible.")
        append_log(instance, "Task failed: Host details missing (IP, SSH key, or user).")
        instance.status = InstanceStatus.ERROR
        return None, "Host details missing"

    playbook_path = os.path.abspath(f'ansible/playbooks/{playbook_name}')
    inventory_path = os.path.abspath('ansible/inventory/')

    base_extravars = {
        'id': instance.id,
        'ansible_ssh_user': host.ssh_user,
        'ansible_ssh_private_key_file': os.path.abspath(host.ssh_key_path)
    }
    if extravars:
        base_extravars.update(extravars)

    log.info(f"Running ansible-playbook for instance {instance.id}...")
    log.debug(f"Playbook: {playbook_path}")
    log.debug(f"Inventory: {inventory_path}")
    log.debug(f"Extravars (before JSON): {base_extravars}")

    env = os.environ.copy()
    env['ANSIBLE_PIPELINING'] = 'True'
    env['ANSIBLE_REMOTE_TMP'] = '/tmp'
    env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
    env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'
    env['ANSIBLE_REMOTE_TEMP'] = '/tmp'

    cmd = ['ansible-playbook', playbook_path, '-i', inventory_path, '-l', host.name]

    if base_extravars:
        json_extravars = json.dumps(base_extravars)
        log.debug(f"Passing extra vars as JSON: {json_extravars}")
        cmd.extend(['-e', json_extravars])

    try:
        log.info(f"Executing Ansible: {' '.join(cmd)}")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1)

        stdout_content, stderr_content = _stream_output(process)

        rc = process.returncode
        log.info(f"Ansible playbook finished with return code: {rc}")

        runner_result = SimpleAnsibleResult(rc, stdout_content, stderr_content)
        log.info(f"Ansible playbook finished. Status: {runner_result.status}, RC: {runner_result.rc}")
        return runner_result, None

    except Exception as e:
        error_msg = f"Error running ansible-playbook with Popen: {e}"
        log.exception(error_msg)
        return None, error_msg


def _run_host_ansible_playbook(host, playbook_name, extravars=None, capture_output=False):
    """
    Helper function to run an Ansible playbook via direct subprocess call, targeting a Host.
    Accepts the host object directly.
    """
    if not host:
        log.error("Host object not provided to _run_host_ansible_playbook.")
        return None, "Internal Error: Host object not provided"

    if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
        log.error(f"Host {host.id} is missing required details (IP, SSH key path, or user) for Ansible.")
        return None, "Host details missing (IP, SSH key, or user)."

    playbook_path = os.path.abspath(f'ansible/playbooks/{playbook_name}')
    inventory_path = os.path.abspath('ansible/inventory/')

    base_extravars = {
        'target_host_name': host.name,
        'ansible_ssh_user': host.ssh_user,
        'ansible_ssh_private_key_file': os.path.abspath(host.ssh_key_path)
    }
    if extravars:
        base_extravars.update(extravars)

    log.info(f"Running ansible-playbook for host {host.id} ({host.name})...")
    log.debug(f"Playbook: {playbook_path}")
    log.debug(f"Inventory: {inventory_path}")
    log.debug(f"Extravars (before JSON): {base_extravars}")

    env = os.environ.copy()
    env['ANSIBLE_PIPELINING'] = 'True'
    env['ANSIBLE_REMOTE_TMP'] = '/tmp'
    env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
    env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'

    cmd = ['ansible-playbook', playbook_path, '-i', inventory_path, '-l', host.name]

    if base_extravars:
        json_extravars = json.dumps(base_extravars)
        log.debug(f"Passing extra vars as JSON: {json_extravars}")
        cmd.extend(['-e', json_extravars])

    try:
        log.info(f"Executing Ansible for host {host.name}: {' '.join(cmd)}")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1)

        if not capture_output:
            stdout_content, stderr_content = _stream_output(process)
        else:
            stdout_content, stderr_content = process.communicate()

        rc = process.wait()

        log.info(f"Ansible playbook for host {host.name} finished with return code: {rc}")

        runner_result = SimpleAnsibleResult(rc, stdout_content, stderr_content)
        log.info(f"Ansible playbook for host {host.name} finished. Status: {runner_result.status}, RC: {runner_result.rc}")

        return runner_result.rc == 0, runner_result.stdout(), runner_result._stderr

    except Exception as e:
        error_msg = f"Error running host ansible-playbook with Popen: {e}"
        log.exception(error_msg)
        return False, "", str(e)
