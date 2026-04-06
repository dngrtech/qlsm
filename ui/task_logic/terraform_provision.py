import logging
import os
import subprocess # Still needed for cleanup attempt
import json       # For parsing Terraform JSON output
import shutil     # For checking if terraform executable exists
import re         # For sanitizing workspace names
from pathlib import Path # For handling file paths
from rq import get_current_job

# Import database and models - requires app context
from ui import db, rq
from ui.models import Host, HostStatus
from .common import append_log # Import from the common module
from .terraform_runner import _run_terraform_command, run_terraform_with_retry # Import the runner helpers

log = logging.getLogger(__name__)

def provision_host_logic(host_id, lock_token=None):
    """
    Task logic to provision a host using Terraform CLI and Workspaces.
    """
    job = get_current_job()
    log.info(f"Starting task provision_host for host_id: {host_id} (Job ID: {job.id})")
    host = None
    terraform_root_dir = None
    workspace_name = None
    original_dir = os.getcwd() # Remember original directory

    # Check if terraform executable exists
    if not shutil.which("terraform"):
        log.error("Terraform executable not found in PATH.")
        # Try to update host status if possible
        try:
            # Need app context to access db here if outside RQ worker context
            host = db.session.get(Host, host_id)
            if host:
                host.status = HostStatus.ERROR
                append_log(host, "Task failed: Terraform executable not found in PATH.")
                db.session.commit()
        except Exception as db_err:
            log.error(f"Failed to update host status after Terraform executable check: {db_err}")
        return "Error: Terraform executable not found."

    try:
        host = db.session.get(Host, host_id)
        if not host:
            log.error(f"Host with id {host_id} not found.")
            return f"Error: Host {host_id} not found."

        append_log(host, f"Task started: provision_host (Job ID: {job.id})")
        host.status = HostStatus.PROVISIONING
        db.session.commit() # Commit status change and initial log
        log.info(f"Host {host_id} status set to PROVISIONING.")

        # --- Determine Terraform Root Directory ---
        if host.provider == 'vultr':
            terraform_root_dir = os.path.abspath('terraform/vultr-root')
        # Add elif for other providers like 'gcp' if needed
        # elif host.provider == 'gcp':
        #     terraform_root_dir = os.path.abspath('terraform/gcp-root') # Example
        else:
            raise ValueError(f"Unsupported provider: {host.provider}")

        if not os.path.isdir(terraform_root_dir):
             raise FileNotFoundError(f"Terraform root directory not found: {terraform_root_dir}")

        # --- Generate and Set Workspace Name ---
        # Sanitize host name for workspace: lowercase, replace spaces/underscores with hyphens, remove other non-alphanumeric
        sanitized_name = re.sub(r'[^\w-]', '', host.name.lower().replace(' ', '-').replace('_', '-'))
        workspace_name = f"host-{host.id}-{sanitized_name}"[:60] # Keep it reasonably short
        host.workspace_name = workspace_name
        append_log(host, f"Generated Terraform workspace name: {workspace_name}")
        db.session.commit()

        # --- Execute Terraform Workflow ---
        # 1. Init
        _, error = _run_terraform_command(host, ['init', '-input=false', '-no-color'], terraform_root_dir)
        if error:
            host.status = HostStatus.ERROR
            db.session.commit()
            return f"Error during terraform init: {error}"

        # 2. Create and Select Workspace
        _, error = _run_terraform_command(host, ['workspace', 'select', workspace_name], terraform_root_dir)
        if error:
            # If workspace doesn't exist, try creating it
            log.warning(f"Workspace '{workspace_name}' not found, attempting to create.")
            append_log(host, f"Workspace '{workspace_name}' not found, attempting to create.")
            _, error = _run_terraform_command(host, ['workspace', 'new', workspace_name], terraform_root_dir)
            if error:
                host.status = HostStatus.ERROR
                db.session.commit()
                return f"Error creating/selecting Terraform workspace: {error}"
            # Re-select after creation just to be sure
            _, error = _run_terraform_command(host, ['workspace', 'select', workspace_name], terraform_root_dir)
            if error:
                host.status = HostStatus.ERROR
                db.session.commit()
                return f"Error selecting Terraform workspace after creation: {error}"


        # 3. Apply
        # TODO: Get startup script path properly - using placeholder for now
        # This should ideally come from config or be determined dynamically
        startup_script_rel_path = "terraform/startup_scripts/ansible_client_setup.sh"
        apply_vars = [
            f"-var=instance_name={host.name}",
            f"-var=vultr_region={host.region}",
            f"-var=vultr_plan={host.machine_size}" # Assuming machine_size maps directly to plan ID
            # startup_script_path is now hardcoded in main.tf, no longer passed as a var
            # Add -var for instance_tags if needed
        ]
        _, error = run_terraform_with_retry(host, ['apply', '-auto-approve', '-input=false', '-no-color'] + apply_vars, terraform_root_dir)
        if error:
            # Set error status if apply fails (retry already attempted by helper)
            host.status = HostStatus.ERROR
            db.session.commit()
            return f"Error during terraform apply: {error}"

        # 4. Get Outputs
        outputs, error = run_terraform_with_retry(host, ['output', '-json'], terraform_root_dir, parse_json=True)
        if error:
            # Set error status if output fails (retry already attempted by helper)
            host.status = HostStatus.ERROR
            db.session.commit()
            return f"Error getting Terraform outputs: {error}"

        # --- Update Host Record ---
        ip_address = outputs.get('main_ip', {}).get('value')
        ssh_key_path = outputs.get('private_key_path', {}).get('value')

        if not ip_address or not ssh_key_path:
             append_log(host, "Error: Failed to retrieve IP address or SSH key path from Terraform output.")
             host.status = HostStatus.ERROR
             db.session.commit()
             return "Error: Missing IP address or SSH key path in Terraform output"

        host.ip_address = ip_address
        # Store SSH key path relative to app root so the path is portable
        # across different deployment environments (bare metal vs Docker).
        # os.path.abspath() in callers resolves it against CWD at runtime.
        app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        try:
            ssh_key_path = os.path.relpath(ssh_key_path, app_root)
        except ValueError:
            pass  # relpath raises ValueError on Windows across drives; keep absolute
        host.ssh_key_path = ssh_key_path
        host.status = HostStatus.PROVISIONED_PENDING_SETUP # Set status before enqueuing next task
        append_log(host, f"Terraform provisioning successful. IP: {host.ip_address}, Key: {host.ssh_key_path}. Status: {host.status.value}")
        db.session.commit() # Commit IP, Key path, and new status

        # --- Enqueue Ansible Setup Task ---
        try:
            # Import dynamically to avoid circular dependency at module level if tasks.py imports this file
            from ui.tasks import setup_host_ansible
            # Use the imported rq object's queue directly
            q = rq.get_queue()
            # Add a 60-second delay before the job starts
            q.enqueue(setup_host_ansible, args=[host.id], kwargs={'lock_token': lock_token}, job_timeout=1200, delay=60)
            append_log(host, f"Enqueued setup_host_ansible task for host {host.id} with a 60s delay.")
            log.info(f"Enqueued setup_host_ansible task for host {host.id} with a 60s delay.")
            db.session.commit() # Commit log message
        except ImportError:
            log.error("Could not import setup_host_ansible task. Is it defined in ui/tasks.py?") # Keep ImportError check
            append_log(host, "Error: Failed to enqueue Ansible setup task (ImportError).")
            host.status = HostStatus.ERROR # Set error status if enqueuing fails
            db.session.commit()
            return "Error: Failed to enqueue Ansible setup task."
        except Exception as queue_err:
            log.exception(f"Failed to enqueue setup_host_ansible task: {queue_err}")
            append_log(host, f"Error: Failed to enqueue Ansible setup task: {queue_err}")
            host.status = HostStatus.ERROR # Set error status if enqueuing fails
            db.session.commit()
            return f"Error: Failed to enqueue Ansible setup task: {queue_err}"

        # --- Final Success (Terraform Part) ---
        log.info(f"Finished Terraform part of provision_host for host_id: {host_id}. Status: {host.status.value}")
        return f"Host {host_id} Terraform provisioning complete. Status: {host.status.value}. Ansible setup task enqueued."

    except Exception as e:
        log.exception(f"Unhandled exception in provision_host_logic for host_id {host_id}: {e}")
        if host and host.status != HostStatus.ERROR: # Avoid overwriting specific error status
            try:
                host.status = HostStatus.ERROR
                append_log(host, f"Task failed with unhandled exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                 log.error(f"Failed to update host status/log on unhandled exception: {commit_err}")

        # Attempt to clean up workspace if created and error occurred
        if workspace_name and terraform_root_dir and host and host.status == HostStatus.ERROR:
            try:
                log.warning(f"Attempting to clean up Terraform workspace '{workspace_name}' due to error.")
                append_log(host, f"Attempting Terraform workspace cleanup: {workspace_name}")
                # Don't use helper here, just run cleanup commands best-effort
                subprocess.run(['terraform', 'workspace', 'select', 'default'], cwd=terraform_root_dir, check=False, capture_output=True)
                subprocess.run(['terraform', 'workspace', 'delete', workspace_name], cwd=terraform_root_dir, check=False, capture_output=True)
                append_log(host, f"Terraform workspace '{workspace_name}' cleanup attempted.")
                log.info(f"Terraform workspace '{workspace_name}' cleanup attempted.")
                db.session.commit() # Commit log message about cleanup attempt
            except Exception as cleanup_err:
                log.error(f"Failed during Terraform workspace cleanup: {cleanup_err}")
                try: # Try to log cleanup failure
                    append_log(host, f"Error during workspace cleanup: {cleanup_err}")
                    db.session.commit()
                except: pass # Ignore errors logging cleanup failure

        return f"Error during host {host_id} provisioning: {e}"
    finally:
        # Change back to original directory if needed (though RQ workers might not care)
        os.chdir(original_dir)
