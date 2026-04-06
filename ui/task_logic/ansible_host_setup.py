import logging
import os
import subprocess
from rq import get_current_job

# Import database and models - requires app context
from ui import db
from ui.models import Host, HostStatus # Need Host and HostStatus
from .common import append_log # Import from the common module
# Note: No need to import _run_ansible_playbook as this task uses direct subprocess calls

log = logging.getLogger(__name__)

def setup_host_ansible_logic(host_id):
    """
    Task logic to perform initial host setup using Ansible after Terraform provisioning.
    """
    job = get_current_job()
    log.info(f"Starting task setup_host_ansible for host_id: {host_id} (Job ID: {job.id})")
    host = None

    try:
        host = db.session.get(Host, host_id)
        if not host:
            log.error(f"Host with id {host_id} not found for Ansible setup.")
            # Cannot log to host if not found, job will fail.
            return f"Error: Host {host_id} not found."

        # Verify host is in the expected state
        if host.status != HostStatus.PROVISIONED_PENDING_SETUP:
            log.warning(f"Host {host_id} is not in PROVISIONED_PENDING_SETUP state (current: {host.status.value}). Skipping Ansible setup.")
            append_log(host, f"Task skipped: Host status is {host.status.value}, expected PROVISIONED_PENDING_SETUP.")
            # Commit log? Or just return? Let's commit the log.
            db.session.commit()
            return f"Task skipped: Host {host_id} status is {host.status.value}."

        append_log(host, f"Task started: setup_host_ansible (Job ID: {job.id})")
        db.session.commit() # Commit initial log

        # --- Check Host Details ---
        if not host.ip_address or not host.ssh_key_path or not host.ssh_user:
            log.error(f"Host {host.id} is missing required details (IP, SSH key path, or user) for Ansible setup.")
            append_log(host, "Task failed: Host details missing (IP, SSH key, or user).")
            host.status = HostStatus.ERROR
            db.session.commit()
            return "Error: Host details missing"

        # --- Wait for SSH Connection ---
        log.info(f"Waiting for SSH connection to become available on {host.ip_address}...")
        append_log(host, f"Waiting for SSH connection to {host.ip_address}...")

        # Determine inventory snippet path (same logic as playbook execution below)
        inventory_snippet_path = None
        if host.provider == 'vultr':
             inventory_snippet_path = os.path.abspath(f"ansible/inventory/{host.name}_vultr_host.yml")
        # Add elif for other providers if needed

        if not inventory_snippet_path or not os.path.exists(inventory_snippet_path):
             log.error(f"Ansible inventory snippet not found for host {host.id} at expected path: {inventory_snippet_path} during SSH wait.")
             append_log(host, f"Host setup failed: Ansible inventory snippet not found at {inventory_snippet_path}")
             host.status = HostStatus.ERROR
             db.session.commit()
             return f"Error: Ansible inventory snippet not found for host {host.id}"

        # Use the inventory file for the wait command
        wait_command_args = [
            'ansible',
            '-i', inventory_snippet_path, # Use the generated inventory file
            host.name, # Target the host name defined within the inventory file
            # User and key are now implicitly handled by the inventory file
            '-m', 'wait_for_connection',
            '-a', 'timeout=300 delay=10' # Wait up to 5 minutes (300s), check every 10s
        ]
        log.info(f"Executing Ansible wait command: {' '.join(wait_command_args)}")
        try:
            wait_result = subprocess.run(wait_command_args,
                                         check=True, capture_output=True, text=True, env=os.environ)
            log.debug(f"Ansible wait stdout:\n{wait_result.stdout}")
            if wait_result.stderr:
                log.warning(f"Ansible wait stderr:\n{wait_result.stderr}")
            append_log(host, f"SSH connection established successfully.")
            log.info(f"SSH connection to {host.ip_address} established.")
            db.session.commit() # Commit log

        except FileNotFoundError:
            log.error("ansible executable not found during wait_for_connection.")
            append_log(host, "Host setup failed: ansible executable not found.")
            host.status = HostStatus.ERROR
            db.session.commit()
            return "Error: ansible not found"
        except subprocess.CalledProcessError as wait_err:
            log.error(f"Failed to establish SSH connection within timeout: {wait_err}")
            log.error(f"Stderr:\n{wait_err.stderr}")
            log.error(f"Stdout:\n{wait_err.stdout}")
            append_log(host, f"Failed to establish SSH connection! RC: {wait_err.returncode}\nStderr:\n{wait_err.stderr}\nStdout:\n{wait_err.stdout}")
            host.status = HostStatus.ERROR
            db.session.commit()
            return f"Error waiting for SSH connection (RC: {wait_err.returncode})"
        except Exception as wait_ex:
            log.exception(f"Unexpected error waiting for SSH connection: {wait_ex}")
            append_log(host, f"Host setup failed with unexpected error during SSH wait: {wait_ex}")
            host.status = HostStatus.ERROR
            db.session.commit()
            return f"Unexpected error waiting for SSH connection: {wait_ex}"

        # --- Run Ansible Host Setup Playbook ---
        log.info(f"Running initial host setup playbook for host {host_id} ({host.ip_address})")
        append_log(host, f"Running initial host setup playbook (setup_host.yml)...")
        db.session.commit() # Commit log before running playbook

        ansible_playbook_path = os.path.abspath('ansible/playbooks/setup_host.yml')
        # Use the generated inventory snippet file for the playbook run
        # Construct expected inventory snippet path based on convention in main.tf
        inventory_snippet_path = None
        if host.provider == 'vultr':
             inventory_snippet_path = os.path.abspath(f"ansible/inventory/{host.name}_vultr_host.yml")
        # Add elif for other providers if needed

        if not inventory_snippet_path or not os.path.exists(inventory_snippet_path):
             log.error(f"Ansible inventory snippet not found for host {host.id} at expected path: {inventory_snippet_path}")
             append_log(host, f"Host setup failed: Ansible inventory snippet not found at {inventory_snippet_path}")
             host.status = HostStatus.ERROR
             db.session.commit()
             return f"Error: Ansible inventory snippet not found for host {host.id}"

        ansible_command_args = [
            'ansible-playbook',
            '-i', inventory_snippet_path,
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

            process = subprocess.Popen(ansible_command_args,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       text=True,
                                       env=env,
                                       bufsize=1)

            from .ansible_runner import _stream_output
            stdout_content, stderr_content = _stream_output(process)

            rc = process.returncode
            log.info(f"Ansible setup playbook finished with return code: {rc}")

            # Check return code AFTER streaming finishes
            if rc != 0:
                 # Raise an error to be caught by the CalledProcessError handler below
                 raise subprocess.CalledProcessError(rc, ansible_command_args, output=stdout_content, stderr=stderr_content)

            # Log combined output to DB on success
            append_log(host, f"Ansible setup playbook successful.\nStdout:\n{stdout_content}\nStderr:\n{stderr_content}")

            # --- Final Success ---
            host.status = HostStatus.ACTIVE
            append_log(host, f"Task finished successfully. Host is ACTIVE.")
            db.session.commit()
            log.info(f"Finished task setup_host_ansible for host_id: {host_id}. Status: ACTIVE")
            return f"Host {host_id} setup complete. Status: ACTIVE"

        except FileNotFoundError:
            log.error("ansible-playbook executable not found during host setup.")
            append_log(host, "Host setup failed: ansible-playbook executable not found.")
            host.status = HostStatus.ERROR
            db.session.commit()
            return "Error: ansible-playbook not found"
        except subprocess.CalledProcessError as ansible_err:
            log.error(f"Ansible setup playbook failed: {ansible_err}")
            log.error(f"Stderr:\n{ansible_err.stderr}")
            log.error(f"Stdout:\n{ansible_err.stdout}")
            append_log(host, f"Ansible setup playbook failed! RC: {ansible_err.returncode}\nStderr:\n{ansible_err.stderr}\nStdout:\n{ansible_err.stdout}")
            host.status = HostStatus.ERROR
            db.session.commit()
            return f"Error during Ansible host setup (RC: {ansible_err.returncode})"
        except Exception as ansible_ex:
            log.exception(f"Unexpected error running Ansible setup playbook: {ansible_ex}")
            append_log(host, f"Host setup failed with unexpected error: {ansible_ex}")
            host.status = HostStatus.ERROR
            db.session.commit()
            return f"Unexpected error during Ansible host setup: {ansible_ex}"

    except Exception as e:
        log.exception(f"Unhandled exception in setup_host_ansible_logic for host_id {host_id}: {e}")
        if host: # Check if host object was retrieved
            try:
                # Avoid overwriting specific error status if already set
                if host.status != HostStatus.ERROR:
                    host.status = HostStatus.ERROR
                append_log(host, f"Task failed with unhandled exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                 log.error(f"Failed to update host status/log on unhandled exception: {commit_err}")
        return f"Error during host {host_id} Ansible setup: {e}"
