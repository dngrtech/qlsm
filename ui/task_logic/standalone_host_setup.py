import logging
import os
import subprocess
from rq import get_current_job

from ui import db
from ui.models import Host, HostStatus
from .common import append_log

log = logging.getLogger(__name__)


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
        inventory_path = _generate_standalone_inventory(host)
        if not inventory_path:
            append_log(host, "Task failed: Could not generate Ansible inventory file.")
            host.status = HostStatus.ERROR
            db.session.commit()
            return "Error: Failed to generate inventory file"

        append_log(host, f"Generated inventory file: {inventory_path}")
        db.session.commit()

        # Wait for SSH connection
        log.info(f"Waiting for SSH connection to {host.ip_address}:{host.ssh_port}...")
        append_log(host, f"Waiting for SSH connection to {host.ip_address}:{host.ssh_port}...")
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
        inventory_dir = os.path.abspath('ansible/inventory')
        os.makedirs(inventory_dir, exist_ok=True)

        inventory_filename = f"{host.name}_standalone_host.yml"
        inventory_path = os.path.join(inventory_dir, inventory_filename)

        inventory_content = f"""all:
  hosts:
    {host.name}:
      ansible_host: {host.ip_address}
      ansible_user: {host.ssh_user}
      ansible_ssh_private_key_file: {os.path.abspath(host.ssh_key_path)}
      ansible_port: {host.ssh_port}
      ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
"""

        with open(inventory_path, 'w') as f:
            f.write(inventory_content)

        log.info(f"Generated standalone inventory file: {inventory_path}")
        return inventory_path

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


def _run_setup_playbook(host, inventory_path):
    """Run the Ansible setup playbook with standalone-specific variables."""
    ansible_playbook_path = os.path.abspath('ansible/playbooks/setup_host.yml')

    # Pass is_standalone=true and ssh_port to the playbook
    ansible_command_args = [
        'ansible-playbook',
        '-i', inventory_path,
        '-e', f'is_standalone=true',
        '-e', f'ssh_port={host.ssh_port}',
    ]
    if host.timezone:
        ansible_command_args += ['-e', f'host_timezone={host.timezone}']
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
