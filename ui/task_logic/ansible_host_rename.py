# ui/task_logic/ansible_host_rename.py

import glob
import logging
import os
import re
from rq import get_current_job
from flask import current_app

from ui import db
from ui.models import Host, HostStatus
from .common import append_log
from ui.database import get_host, update_host
from .ansible_runner import _run_host_ansible_playbook


log = logging.getLogger(__name__)


def _rename_config_folder(old_name, new_name):
    """
    Rename the config folder when a host is renamed.

    Configs are stored at: configs/{host_name}/

    Returns: (success: bool, error_message: str or None)
    """
    configs_dir = os.path.abspath('configs')
    old_path = os.path.join(configs_dir, old_name)
    new_path = os.path.join(configs_dir, new_name)

    log.info(f"Checking for config folder to rename: {old_path} -> {new_path}")

    # If old config folder doesn't exist, that's fine - no configs to rename
    if not os.path.exists(old_path):
        log.info(f"No config folder found at {old_path}, skipping rename")
        return True, None

    # If new path already exists, that's a problem
    if os.path.exists(new_path):
        error_msg = f"Config folder already exists at {new_path}"
        log.error(error_msg)
        return False, error_msg

    try:
        os.rename(old_path, new_path)
        log.info(f"Renamed config folder from {old_path} to {new_path}")
        return True, None
    except Exception as e:
        error_msg = f"Error renaming config folder: {str(e)}"
        log.exception(error_msg)
        return False, error_msg


def _update_inventory_file(old_name, new_name, host):
    """
    Update the inventory file when a host is renamed.

    This function:
    1. Renames the inventory file from old_name to new_name
    2. Updates the hostname reference inside the inventory content

    Returns: (success: bool, error_message: str or None)
    """
    inventory_dir = os.path.abspath('ansible/inventory')

    # Find inventory file regardless of suffix (_vultr_host.yml, _standalone_host.yml, etc.)
    matches = glob.glob(os.path.join(inventory_dir, f"{old_name}_*.yml"))
    if not matches:
        error_msg = f"Inventory file not found for host '{old_name}' in {inventory_dir}"
        log.error(error_msg)
        return False, error_msg
    if len(matches) > 1:
        error_msg = f"Multiple inventory files found for host '{old_name}': {matches}. Cannot determine which to rename."
        log.error(error_msg)
        return False, error_msg

    old_path = matches[0]
    suffix = os.path.basename(old_path)[len(old_name):]  # e.g. "_standalone_host.yml"
    new_path = os.path.join(inventory_dir, f"{new_name}{suffix}")

    log.info(f"Updating inventory file: {old_path} -> {new_path}")

    try:
        # Read the old inventory content
        with open(old_path, 'r') as f:
            content = f.read()

        # Rewrite only the host entry name at the start of a YAML or INI inventory line.
        # This supports standalone YAML inventories ("    old-name:") and Vultr-style INI lines
        # ("old-name ansible_host=...") without touching SSH key paths like
        # "/path/to/old-name_standalone_id_rsa" elsewhere in the file.
        updated_content = re.sub(
            rf'^(?P<indent>\s*){re.escape(old_name)}(?P<delimiter>:|\s)',
            rf'\g<indent>{new_name}\g<delimiter>',
            content,
            flags=re.MULTILINE,
        )

        # Write the updated content to the new path
        with open(new_path, 'w') as f:
            f.write(updated_content)

        log.info(f"Created new inventory file at {new_path}")

        # Remove the old inventory file
        os.remove(old_path)
        log.info(f"Removed old inventory file at {old_path}")

        return True, None

    except Exception as e:
        error_msg = f"Error updating inventory file: {str(e)}"
        log.exception(error_msg)
        return False, error_msg


def rename_host_logic(host_id, old_name, new_name):
    """
    Handle host rename: update inventory file and run Ansible playbook.

    This task is called AFTER the database has been updated with the new name.
    It:
    1. Updates the inventory file (rename + update content)
    2. Runs the rename_host.yml playbook to update the remote server's hostname
    """
    host = get_host(host_id)
    if not host:
        current_app.logger.error(f"rename_host_logic: Host with ID {host_id} not found.")
        return False

    original_logs = host.logs or ""
    update_host(host.id, logs=f"Initiating host rename from '{old_name}' to '{new_name}'...\n{original_logs}")

    job = get_current_job()
    job_id = job.id if job else "unknown_job"

    try:
        # Step 1: Update the inventory file
        current_app.logger.info(f"Step 1: Updating inventory file for host rename: {old_name} -> {new_name}")

        success, error_msg = _update_inventory_file(old_name, new_name, host)
        if not success:
            current_app.logger.error(f"Failed to update inventory file: {error_msg}")
            update_host(
                host.id,
                status=HostStatus.ERROR,
                logs=f"Host rename failed: Could not update inventory file. {error_msg}\n{original_logs}"
            )
            return False

        update_host(host.id, logs=f"Inventory file updated successfully.\n{host.logs or original_logs}")

        # Step 2: Rename the config folder (if it exists)
        current_app.logger.info(f"Step 2: Renaming config folder for host: {old_name} -> {new_name}")

        success, error_msg = _rename_config_folder(old_name, new_name)
        if not success:
            current_app.logger.error(f"Failed to rename config folder: {error_msg}")
            update_host(
                host.id,
                status=HostStatus.ERROR,
                logs=f"Host rename failed: Could not rename config folder. {error_msg}\n{original_logs}"
            )
            return False

        # Refresh host object to get updated logs
        host = get_host(host_id)
        update_host(host.id, logs=f"Config folder renamed successfully.\n{host.logs or original_logs}")

        # Step 3: Run the Ansible playbook to rename the host on the remote server
        current_app.logger.info(f"Step 3: Running rename_host.yml playbook for host {new_name}")

        playbook_name = "rename_host.yml"
        extra_vars = {
            "target_host": new_name,  # Target the host by its new name (inventory already updated)
            "new_host_name": new_name
        }

        # Refresh host object to get updated state
        host = get_host(host_id)

        success, stdout, stderr = _run_host_ansible_playbook(
            host=host,
            playbook_name=playbook_name,
            extravars=extra_vars
        )

        if success:
            current_app.logger.info(f"Host {old_name} renamed to {new_name} successfully.")
            update_host(
                host.id,
                status=HostStatus.ACTIVE,
                logs=f"Host renamed successfully from '{old_name}' to '{new_name}'.\n{original_logs}"
            )
            return True
        else:
            current_app.logger.error(f"Failed to rename host {old_name} to {new_name}. Error: {stderr}")
            update_host(
                host.id,
                status=HostStatus.ERROR,
                logs=f"Host rename via Ansible failed. Error: {stderr}\n{original_logs}"
            )
            return False

    except Exception as e:
        current_app.logger.exception(f"Unexpected error in rename_host_logic for host {host_id}: {e}")
        error_message = f"Unexpected Python error during host rename task (Job ID: {job_id}): {str(e)}"
        update_host(host.id, status=HostStatus.ERROR, logs=f"{error_message}\n{original_logs}")
        return False
