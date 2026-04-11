import logging
import os
import subprocess
from rq import get_current_job

from ui import db
from ui.models import Host, HostStatus
from ui.task_logic.self_host_network import resolve_self_host_management_target
from .common import append_log
from .standalone_inventory import generate_standalone_inventory

log = logging.getLogger(__name__)
INVENTORY_MISMATCH_MARKERS = (
    "no inventory was parsed",
    "could not match supplied host pattern",
    "no hosts matched",
)


def _extract_inventory_mismatch_detail(stdout_content="", stderr_content=""):
    for source in (stderr_content or "", stdout_content or ""):
        for line in source.splitlines():
            stripped = line.strip()
            if stripped and any(marker in stripped.lower() for marker in INVENTORY_MISMATCH_MARKERS):
                return stripped
    return None


def setup_standalone_host_logic(host_id):
    """
    Task logic to set up a standalone host via Ansible (no Terraform provisioning).
    """
    job = get_current_job()
    log.info(f"Starting task setup_standalone_host for host_id: {host_id} (Job ID: {job.id})")
    host = None

    try:
        host = db.session.get(Host, host_id)
        if not host:
            log.error(f"Host with id {host_id} not found for standalone setup.")
            return f"Error: Host {host_id} not found."

        # Verify host is in the expected state
        if host.status != HostStatus.PROVISIONED_PENDING_SETUP:
            log.warning(f"Host {host_id} is not in PROVISIONED_PENDING_SETUP state (current: {host.status.value}).")
            append_log(host, f"Task skipped: Host status is {host.status.value}, expected PROVISIONED_PENDING_SETUP.")
            db.session.commit()
            return f"Task skipped: Host {host_id} status is {host.status.value}."

        append_log(host, f"Task started: setup_standalone_host (Job ID: {job.id})")
        db.session.commit()

        # Verify required host details
        if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
            log.error(f"Host {host.id} is missing required details for standalone setup.")
            append_log(host, "Task failed: Host details missing (IP, SSH key, or user).")
            host.status = HostStatus.ERROR
            db.session.commit()
            return "Error: Host details missing"

        # Generate inventory file for standalone host
        inventory_result = _generate_standalone_inventory(host)
        if not inventory_result:
            append_log(host, "Task failed: Could not generate Ansible inventory file.")
            host.status = HostStatus.ERROR
            db.session.commit()
            return "Error: Failed to generate inventory file"
        inventory_path, management_target = inventory_result

        append_log(host, f"Generated inventory file: {inventory_path}")
        append_log(host, f"Configured server address: {host.ip_address}")
        if host.provider == 'self':
            append_log(host, f"Resolved self-host management target: {management_target}")
            append_log(
                host,
                f"Waiting for SSH connection to self-host management target {management_target}:{host.ssh_port}...",
            )
        else:
            append_log(host, f"Waiting for SSH connection to {management_target}:{host.ssh_port}...")
        db.session.commit()

        # Wait for SSH connection
        log.info(f"Waiting for SSH connection to {management_target}:{host.ssh_port}...")
        db.session.commit()

        if not _wait_for_ssh(host, inventory_path):
            return f"Error waiting for SSH connection to host {host_id}"

        append_log(host, "SSH connection established successfully.")
        db.session.commit()

        # Run Ansible setup playbook
        log.info(f"Running host setup playbook for standalone host {host_id}")
        append_log(host, "Running initial host setup playbook (setup_host.yml)...")
        db.session.commit()

        if not _run_setup_playbook(host, inventory_path):
            return f"Error during Ansible host setup for host {host_id}"

        # Success
        host.status = HostStatus.ACTIVE
        append_log(host, "Task finished successfully. Host is ACTIVE.")
        db.session.commit()
        log.info(f"Finished task setup_standalone_host for host_id: {host_id}. Status: ACTIVE")
        return f"Standalone host {host_id} setup complete. Status: ACTIVE"

    except Exception as e:
        log.exception(f"Unhandled exception in setup_standalone_host_logic for host_id {host_id}: {e}")
        if host:
            try:
                if host.status != HostStatus.ERROR:
                    host.status = HostStatus.ERROR
                append_log(host, f"Task failed with unhandled exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update host status/log on unhandled exception: {commit_err}")
        return f"Error during standalone host {host_id} setup: {e}"


def _generate_standalone_inventory(host):
    """Generate Ansible inventory file for a standalone host."""
    try:
        if host.provider == 'self':
            ansible_host = resolve_self_host_management_target()
        else:
            ansible_host = host.ip_address
        inventory_path = generate_standalone_inventory(host, ansible_host=ansible_host)
        log.info(f"Generated standalone inventory file: {inventory_path}")
        return inventory_path, ansible_host
    except Exception as e:
        log.error(f"Failed to generate inventory file for host {host.id}: {e}")
        return None


def _wait_for_ssh(host, inventory_path):
    """Wait for SSH connection to become available."""
    wait_command_args = [
        'ansible',
        '-i', inventory_path,
        host.name,
        '-m', 'wait_for_connection',
        '-a', 'timeout=300 delay=10'
    ]

    log.info(f"Executing Ansible wait command: {' '.join(wait_command_args)}")
    try:
        wait_result = subprocess.run(
            wait_command_args,
            check=True, capture_output=True, text=True, env=os.environ
        )
        inventory_error = _extract_inventory_mismatch_detail(wait_result.stdout, wait_result.stderr)
        if inventory_error:
            log.error(f"Inventory mismatch while waiting for SSH on host {host.id}: {inventory_error}")
            append_log(host, f"Host setup failed: {inventory_error}")
            host.status = HostStatus.ERROR
            db.session.commit()
            return False
        log.debug(f"Ansible wait stdout:\n{wait_result.stdout}")
        if wait_result.stderr:
            log.warning(f"Ansible wait stderr:\n{wait_result.stderr}")
        return True

    except FileNotFoundError:
        log.error("ansible executable not found during wait_for_connection.")
        append_log(host, "Host setup failed: ansible executable not found.")
        host.status = HostStatus.ERROR
        db.session.commit()
        return False
    except subprocess.CalledProcessError as wait_err:
        log.error(f"Failed to establish SSH connection within timeout: {wait_err}")
        append_log(host, f"Failed to establish SSH connection! RC: {wait_err.returncode}\nStderr:\n{wait_err.stderr}")
        host.status = HostStatus.ERROR
        db.session.commit()
        return False
    except Exception as wait_ex:
        log.exception(f"Unexpected error waiting for SSH connection: {wait_ex}")
        append_log(host, f"Host setup failed with unexpected error during SSH wait: {wait_ex}")
        host.status = HostStatus.ERROR
        db.session.commit()
        return False


def _setup_playbook_extra_vars(host):
    extra_vars = {
        'is_standalone': 'true',
        'ssh_port': str(host.ssh_port),
        'firewall_mode': 'helper' if host.provider == 'self' else 'full',
    }
    if host.provider == 'self':
        extra_vars['use_host_redis'] = 'false'
    if host.timezone:
        extra_vars['host_timezone'] = host.timezone
    return extra_vars


def _run_setup_playbook(host, inventory_path):
    """Run the Ansible setup playbook with standalone-specific variables."""
    ansible_playbook_path = os.path.abspath('ansible/playbooks/setup_host.yml')

    ansible_command_args = [
        'ansible-playbook',
        '-i', inventory_path,
    ]
    for key, value in _setup_playbook_extra_vars(host).items():
        ansible_command_args += ['-e', f'{key}={value}']
    ansible_command_args.append(ansible_playbook_path)

    log.info(f"Executing Ansible command: {' '.join(ansible_command_args)}")

    try:
        env = os.environ.copy()
        env['ANSIBLE_PIPELINING'] = 'True'
        env['ANSIBLE_REMOTE_TMP'] = '/tmp'
        env['ANSIBLE_BECOME_FLAGS'] = '-H -S -n'
        env['ANSIBLE_ALLOW_WORLD_READABLE_TMPFILES'] = 'True'
        env['ANSIBLE_REMOTE_TEMP'] = '/tmp'

        process = subprocess.Popen(
            ansible_command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1
        )

        from .ansible_runner import _stream_output
        stdout_content, stderr_content = _stream_output(process)

        rc = process.returncode
        log.info(f"Ansible setup playbook finished with return code: {rc}")
        inventory_error = _extract_inventory_mismatch_detail(stdout_content, stderr_content)
        if inventory_error:
            log.error(f"Inventory mismatch during host setup playbook for host {host.id}: {inventory_error}")
            append_log(host, f"Host setup failed: {inventory_error}")
            host.status = HostStatus.ERROR
            db.session.commit()
            return False

        if rc != 0:
            raise subprocess.CalledProcessError(rc, ansible_command_args, output=stdout_content, stderr=stderr_content)

        append_log(host, f"Ansible setup playbook successful.\nStdout:\n{stdout_content}\nStderr:\n{stderr_content}")
        return True

    except FileNotFoundError:
        log.error("ansible-playbook executable not found during host setup.")
        append_log(host, "Host setup failed: ansible-playbook executable not found.")
        host.status = HostStatus.ERROR
        db.session.commit()
        return False
    except subprocess.CalledProcessError as ansible_err:
        log.error(f"Ansible setup playbook failed: {ansible_err}")
        append_log(host, f"Ansible setup playbook failed! RC: {ansible_err.returncode}\nStderr:\n{ansible_err.stderr}\nStdout:\n{ansible_err.stdout}")
        host.status = HostStatus.ERROR
        db.session.commit()
        return False
    except Exception as ansible_ex:
        log.exception(f"Unexpected error running Ansible setup playbook: {ansible_ex}")
        append_log(host, f"Host setup failed with unexpected error: {ansible_ex}")
        host.status = HostStatus.ERROR
        db.session.commit()
        return False
