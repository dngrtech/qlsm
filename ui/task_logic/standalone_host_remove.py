import logging
import os
import shutil
from pathlib import Path
from rq import get_current_job

from ui import db
from ui.models import Host, HostStatus
from ui.routes.self_host_helpers import remove_authorized_key
from .common import append_log
from .standalone_inventory import inventory_filename_for_host

log = logging.getLogger(__name__)


def remove_standalone_host_logic(host_id):
    """
    Task logic to remove a standalone host from inventory.
    This does NOT destroy the actual server - it only removes:
    - SSH key file
    - Ansible inventory file
    - Local config directory
    - Database record
    """
    job = get_current_job()
    log.info(f"Starting task remove_standalone_host for host_id: {host_id} (Job ID: {job.id})")
    host = None

    try:
        host = db.session.get(Host, host_id)
        if not host:
            log.error(f"Host with id {host_id} not found for removal.")
            return f"Error: Host {host_id} not found."

        host_name = host.name
        ssh_key_path = host.ssh_key_path

        # Set status to DELETING if not already
        if host.status != HostStatus.DELETING:
            host.status = HostStatus.DELETING
            db.session.commit()

        append_log(host, f"Task started: remove_standalone_host (Job ID: {job.id})")
        db.session.commit()

        # 1. Delete SSH key file
        if ssh_key_path and os.path.exists(ssh_key_path):
            try:
                os.remove(ssh_key_path)
                append_log(host, f"Deleted SSH key file: {ssh_key_path}")
                log.info(f"Deleted SSH key file: {ssh_key_path}")
            except OSError as e:
                log.error(f"Error deleting SSH key file {ssh_key_path}: {e}")
                append_log(host, f"Warning: Failed to delete SSH key file {ssh_key_path}: {e}")

        if host.provider == 'self' and ssh_key_path:
            pub_key_path = f"{ssh_key_path}.pub"
            if os.path.exists(pub_key_path):
                try:
                    public_key = Path(pub_key_path).read_text().strip()
                except OSError as e:
                    public_key = None
                    log.error(f"Error reading SSH public key file {pub_key_path}: {e}")
                    append_log(host, f"Warning: Failed to read SSH public key file {pub_key_path}: {e}")

                if public_key:
                    try:
                        removed = remove_authorized_key(public_key)
                        if removed:
                            append_log(host, "Removed self-host public key from authorized_keys")
                        else:
                            log.warning(
                                "Self-host public key was not present in authorized_keys for host %s",
                                host.id,
                            )
                            append_log(host, "Warning: Self-host public key was not present in authorized_keys")
                    except Exception as e:
                        log.error(f"Error removing self-host authorized key: {e}")
                        append_log(host, f"Warning: Failed to remove self-host authorized key: {e}")

                try:
                    os.remove(pub_key_path)
                    append_log(host, f"Deleted SSH public key file: {pub_key_path}")
                except OSError as e:
                    log.error(f"Error deleting SSH public key file {pub_key_path}: {e}")
                    append_log(host, f"Warning: Failed to delete SSH public key file {pub_key_path}: {e}")

        # 2. Delete Ansible inventory file
        inventory_path = os.path.abspath(f"ansible/inventory/{inventory_filename_for_host(host)}")
        if os.path.exists(inventory_path):
            try:
                os.remove(inventory_path)
                append_log(host, f"Deleted Ansible inventory file: {inventory_path}")
                log.info(f"Deleted Ansible inventory file: {inventory_path}")
            except OSError as e:
                log.error(f"Error deleting inventory file {inventory_path}: {e}")
                append_log(host, f"Warning: Failed to delete inventory file {inventory_path}: {e}")

        # 3. Delete local config directory
        config_dir_path = Path(f"configs/{host_name}")
        cleanup_log_msg = ""
        try:
            if config_dir_path.exists() and config_dir_path.is_dir():
                shutil.rmtree(config_dir_path)
                cleanup_log_msg = f"Successfully removed local host config directory: {config_dir_path}"
                log.info(cleanup_log_msg)
            else:
                cleanup_log_msg = f"Local config directory not found, skipping: {config_dir_path}"
                log.info(cleanup_log_msg)
        except OSError as e:
            cleanup_log_msg = f"Error removing local config directory {config_dir_path}: {e}"
            log.error(cleanup_log_msg)

        append_log(host, cleanup_log_msg)
        append_log(host, "Standalone host removal complete. Deleting database record...")
        db.session.commit()

        # 4. Delete the host record from the database
        log.info(f"Deleting host record {host_id} ({host_name}) from database.")
        db.session.delete(host)
        db.session.commit()
        log.info(f"Finished task remove_standalone_host for host_id: {host_id}. Record deleted.")

        return f"Standalone host {host_id} ({host_name}) removed from inventory."

    except Exception as e:
        log.exception(f"Unhandled exception in remove_standalone_host_logic for host_id {host_id}: {e}")
        if host and host.status != HostStatus.ERROR:
            try:
                host.status = HostStatus.ERROR
                append_log(host, f"Task failed with unhandled exception: {e}")
                db.session.commit()
            except Exception as commit_err:
                log.error(f"Failed to update host status/log on unhandled exception: {commit_err}")
        return f"Error during standalone host {host_id} removal: {e}"
