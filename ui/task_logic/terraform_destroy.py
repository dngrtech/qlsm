import logging
import os
import subprocess # Still needed for cleanup attempt
import json       # For parsing Terraform JSON output
import shutil     # For checking if terraform executable exists and file operations
import re         # For sanitizing workspace names
from pathlib import Path # For handling file paths
from rq import get_current_job

# Import database and models - requires app context
from ui import db
from ui.models import Host, HostStatus
from .common import append_log # Import from the common module
from .terraform_runner import _run_terraform_command # Import the runner helper

log = logging.getLogger(__name__)

def destroy_host_logic(host_id):
    """
    Task logic to destroy a host using Terraform CLI and Workspaces.
    """
    job = get_current_job()
    log.info(f"Starting task destroy_host for host_id: {host_id} (Job ID: {job.id})")
    host = None
    terraform_root_dir = None
    workspace_name = None
    ssh_key_path = None # Store key path for deletion later
    inventory_snippet_path = None # Store inventory path for deletion later
    original_dir = os.getcwd()

    # Check if terraform executable exists
    if not shutil.which("terraform"):
        log.error("Terraform executable not found in PATH.")
        # Try to update host status if possible
        try:
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
            log.error(f"Host with id {host_id} not found for destruction.")
            return f"Error: Host {host_id} not found."

        append_log(host, f"Task started: destroy_host (Job ID: {job.id})")
        host.status = HostStatus.DELETING
        db.session.commit() # Commit status change and initial log
        log.info(f"Host {host_id} status set to DELETING.")

        # --- Get Required Info ---
        workspace_name = host.workspace_name
        ssh_key_path = host.ssh_key_path # Get key path before potential deletion
        host_name_for_files = host.name # Get name for file cleanup before deletion

        # --- Terraform Workflow (skipped if no workspace was ever created) ---
        if not workspace_name:
            # Host never reached Terraform provisioning (e.g. stuck in PROVISIONING/ERROR
            # before workspace creation). Nothing to destroy remotely — skip to cleanup.
            log.warning(f"Host {host_id} has no workspace name. Skipping Terraform destroy.")
            append_log(host, "No Terraform workspace found — skipping destroy, cleaning up local resources.")
        else:
            if not host.provider:
                raise ValueError("Provider not found for host. Cannot determine Terraform directory.")

            # --- Determine Terraform Root Directory ---
            if host.provider == 'vultr':
                terraform_root_dir = os.path.abspath('terraform/vultr-root')
                # Construct expected inventory snippet path based on convention in main.tf
                inventory_snippet_path = os.path.abspath(f"ansible/inventory/{host_name_for_files}_vultr_host.yml")
            # Add elif for other providers if needed
            else:
                raise ValueError(f"Unsupported provider: {host.provider}")

            if not os.path.isdir(terraform_root_dir):
                raise FileNotFoundError(f"Terraform root directory not found: {terraform_root_dir}")

            # --- Execute Terraform Workflow ---
            # 1. Init (might be needed if state backend is configured)
            _, error = _run_terraform_command(host, ['init', '-input=false', '-no-color'], terraform_root_dir)
            if error:
                host.status = HostStatus.ERROR
                db.session.commit()
                return f"Error during terraform init: {error}"

            # 2. Select Workspace (check if it exists first)
            _, error = _run_terraform_command(host, ['workspace', 'select', workspace_name], terraform_root_dir)
            if error:
                # If workspace doesn't exist, maybe it was already destroyed? Log and proceed to cleanup.
                log.warning(f"Workspace '{workspace_name}' not found during destroy. Assuming already destroyed or error state.")
                append_log(host, f"Warning: Workspace '{workspace_name}' not found. Proceeding with cleanup.")
                # Skip destroy and workspace delete commands, go straight to file/DB cleanup
                # Do not set ERROR status here, as this is considered a success path (already destroyed)
            else:
                # 3. Destroy (only if workspace was selected successfully)
                # Construct variables needed for destroy command
                destroy_vars = [
                    f"-var=instance_name={host.name}",
                    f"-var=vultr_region={host.region}",
                    f"-var=vultr_plan={host.machine_size}" # Assuming machine_size maps directly to plan ID
                    # Add other vars if needed by the destroy process
                ]
                _, error = _run_terraform_command(host, ['destroy', '-auto-approve', '-input=false', '-no-color'] + destroy_vars, terraform_root_dir)
                if error:
                    # Check if the error is because the instance is already gone (404)
                    if 'status":404' in error or 'not found' in error.lower():
                        log.warning(f"Terraform destroy failed because resource is already gone. Cleaning up state.")
                        append_log(host, "Resource already deleted externally. Cleaning up Terraform state...")

                        # Remove the resource from Terraform state
                        _, state_rm_error = _run_terraform_command(host, ['state', 'rm', 'module.vultr_host_instance.vultr_instance.this'], terraform_root_dir)
                        if state_rm_error and 'No matching objects found' not in state_rm_error:
                            log.warning(f"Error removing vultr_instance from state: {state_rm_error}")

                        # Also try to remove SSH key resource if it exists
                        _, _ = _run_terraform_command(host, ['state', 'rm', 'vultr_ssh_key.instance_ssh_key'], terraform_root_dir)

                        # Run destroy again to clean up any remaining resources (like local files, tls keys)
                        _, retry_error = _run_terraform_command(host, ['destroy', '-auto-approve', '-input=false', '-no-color'] + destroy_vars, terraform_root_dir)
                        if retry_error:
                            log.warning(f"Retry destroy had errors (may be OK): {retry_error}")
                            append_log(host, f"Cleanup destroy completed with warnings: {retry_error}")
                    else:
                        host.status = HostStatus.ERROR
                        db.session.commit()
                        return f"Error during terraform destroy: {error}"

                # 4. Select Default Workspace and Delete Old Workspace
                _, error = _run_terraform_command(host, ['workspace', 'select', 'default'], terraform_root_dir)
                if error:
                    # Log error but don't necessarily fail the whole process if cleanup is next
                    log.error(f"Error selecting default workspace after destroy: {error}")
                    append_log(host, f"Warning: Failed to select default workspace: {error}")
                    # Don't set ERROR status here, proceed to workspace delete attempt

                _, error = _run_terraform_command(host, ['workspace', 'delete', workspace_name], terraform_root_dir)
                if error:
                    # Log error but don't necessarily fail the whole process if cleanup is next
                    log.error(f"Error deleting workspace {workspace_name} after destroy: {error}")
                    append_log(host, f"Warning: Failed to delete workspace {workspace_name}: {error}")
                    # Don't set ERROR status here, proceed to file/DB cleanup

        # --- Cleanup and Finalize ---
        append_log(host, "Terraform destroy/cleanup successful. Removing associated files and DB record...")

        # Delete SSH key file if it exists and path was recorded
        if ssh_key_path and os.path.exists(ssh_key_path):
            try:
                os.remove(ssh_key_path)
                append_log(host, f"Deleted SSH key file: {ssh_key_path}")
                log.info(f"Deleted SSH key file: {ssh_key_path}")
            except OSError as e:
                log.error(f"Error deleting SSH key file {ssh_key_path}: {e}")
                append_log(host, f"Warning: Failed to delete SSH key file {ssh_key_path}: {e}")

        # Delete Ansible inventory snippet file if it exists and path was determined
        if inventory_snippet_path and os.path.exists(inventory_snippet_path):
             try:
                 os.remove(inventory_snippet_path)
                 append_log(host, f"Deleted Ansible inventory snippet: {inventory_snippet_path}")
                 log.info(f"Deleted Ansible inventory snippet: {inventory_snippet_path}")
             except OSError as e:
                 log.error(f"Error deleting Ansible inventory snippet {inventory_snippet_path}: {e}")
                 append_log(host, f"Warning: Failed to delete Ansible inventory snippet {inventory_snippet_path}: {e}")

        # Commit the final log messages before deleting the host record and config dir
        db.session.commit()

        # --- Remove local config directory ---
        local_config_dir_path = Path(f"configs/{host_name_for_files}")
        cleanup_log_msg = ""
        try:
            if local_config_dir_path.exists() and local_config_dir_path.is_dir():
                shutil.rmtree(local_config_dir_path)
                cleanup_log_msg = f"Successfully removed local host config directory: {local_config_dir_path}"
                log.info(cleanup_log_msg)
            else:
                cleanup_log_msg = f"Local host config directory not found or not a directory, skipping removal: {local_config_dir_path}"
                log.warning(cleanup_log_msg)
        except OSError as e:
            cleanup_log_msg = f"Error removing local host config directory {local_config_dir_path}: {e}"
            log.error(cleanup_log_msg)
        # Append cleanup log message *before* deleting the host record
        append_log(host, cleanup_log_msg)
        db.session.commit() # Commit log message

        # Delete the host record from the database
        log.info(f"Deleting host record {host_id} ({host_name_for_files}) from database.")
        db.session.delete(host)
        db.session.commit()
        log.info(f"Finished task destroy_host for host_id: {host_id}. Host record '{host_name_for_files}' deleted.")

        return f"Host {host_id} ({host_name_for_files}) destruction complete and record deleted."

    except Exception as e:
        log.exception(f"Unhandled exception in destroy_host_logic for host_id {host_id}: {e}")
        if host and host.status != HostStatus.ERROR: # Avoid overwriting specific error status
            try:
                host.status = HostStatus.ERROR
                append_log(host, f"Task failed with unhandled exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update host status/log on unhandled exception: {commit_err}")
        return f"Error during host {host_id} destruction: {e}"
    finally:
        os.chdir(original_dir)
