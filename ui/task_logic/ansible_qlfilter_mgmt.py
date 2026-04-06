from flask import current_app

from ui.models import Host, HostStatus, QLFilterStatus
from ui.database import get_host, update_host
from .ansible_runner import _run_host_ansible_playbook # Changed to new helper


# Define QLFilter specific statuses if they were added to HostStatus enum
# For now, using existing statuses or will add them later.
# Example: QLFILTER_INSTALLING, QLFILTER_UNINSTALLING, QLFILTER_ACTIVE, QLFILTER_INACTIVE

def install_qlfilter_logic(host_id):
    """
    Logic to install QLFilter on a given host.
    Executes the 'setup_qlfilter.yml' playbook.
    """
    host = get_host(host_id)
    if not host:
        current_app.logger.error(f"install_qlfilter_logic: Host with ID {host_id} not found.")
        return False

    # update_host(host.id, status=HostStatus.PROVISIONING) # Example placeholder status
    update_host(host.id, qlfilter_status=QLFilterStatus.INSTALLING)

    playbook_path = "ansible/playbooks/setup_qlfilter.yml"
    extra_vars = {"target_host": host.name} # Or host.ip_address if inventory uses IPs

    current_app.logger.info(f"Executing QLFilter install playbook for host: {host.name} (ID: {host.id})")
    
    success, stdout, stderr = _run_host_ansible_playbook(
        host=host,
        playbook_name=playbook_path.split('/')[-1], # Pass only playbook name
        extravars=extra_vars
    )

    if success:
        current_app.logger.info(f"QLFilter installed successfully on host: {host.name}")
        update_host(host.id, qlfilter_status=QLFilterStatus.ACTIVE, status=HostStatus.ACTIVE, logs=f"QLFilter installed successfully.\n{host.logs or ''}")
        return True
    else:
        current_app.logger.error(f"Failed to install QLFilter on host: {host.name}. Error: {stderr}")
        update_host(host.id, qlfilter_status=QLFilterStatus.ERROR, status=HostStatus.ACTIVE, logs=f"QLFilter installation failed. Error: {stderr}\n{host.logs or ''}")
        # If QLFilter install fails, host is still ACTIVE, but qlfilter_status is ERROR
        return False

def uninstall_qlfilter_logic(host_id):
    """
    Logic to uninstall QLFilter from a given host.
    Executes the 'remove_qlfilter.yml' playbook.
    """
    host = get_host(host_id)
    if not host:
        current_app.logger.error(f"uninstall_qlfilter_logic: Host with ID {host_id} not found.")
        return False

    update_host(host.id, qlfilter_status=QLFilterStatus.UNINSTALLING)

    playbook_path = "ansible/playbooks/remove_qlfilter.yml"
    extra_vars = {"target_host": host.name}

    current_app.logger.info(f"Executing QLFilter uninstall playbook for host: {host.name} (ID: {host.id})")
    
    success, stdout, stderr = _run_host_ansible_playbook(
        host=host,
        playbook_name=playbook_path.split('/')[-1], # Pass only playbook name
        extravars=extra_vars
    )

    if success:
        current_app.logger.info(f"QLFilter uninstalled successfully from host: {host.name}")
        update_host(host.id, qlfilter_status=QLFilterStatus.NOT_INSTALLED, status=HostStatus.ACTIVE, logs=f"QLFilter uninstalled successfully.\n{host.logs or ''}")
        return True
    else:
        current_app.logger.error(f"Failed to uninstall QLFilter from host: {host.name}. Error: {stderr}")
        update_host(host.id, qlfilter_status=QLFilterStatus.ERROR, status=HostStatus.ACTIVE, logs=f"QLFilter uninstallation failed. Error: {stderr}\n{host.logs or ''}")
        # If QLFilter uninstall fails, host is still ACTIVE, but qlfilter_status is ERROR
        return False

def check_qlfilter_status_logic(host_id):
    """
    Logic to check QLFilter status on a given host.
    Executes the 'check_qlfilter_status.yml' playbook and parses its output.
    Returns a dictionary with status flags (e.g., {'installed': True, 'active': True}).
    """
    host = get_host(host_id)
    if not host:
        current_app.logger.error(f"check_qlfilter_status_logic: Host with ID {host_id} not found.")
        return {"error": "Host not found", "installed": False, "active": False, "enabled": False, "exists": False}

    playbook_path = "ansible/playbooks/check_qlfilter_status.yml"
    extra_vars = {"target_host": host.name}

    current_app.logger.info(f"Executing QLFilter status check playbook for host: {host.name} (ID: {host.id})")
    
    success, stdout, stderr = _run_host_ansible_playbook(
        host=host,
        playbook_name=playbook_path.split('/')[-1], # Pass only playbook name
        extravars=extra_vars,
        capture_output=True # Ensure we get stdout for parsing
    )
    
    parsed_status = QLFilterStatus.UNKNOWN
    final_status_dict = {"installed": False, "active": False, "enabled": False, "exists": False}


    if success and stdout:
        try:
            # Simple string parsing for the debug message:
            if "QLFilter Installed: True" in stdout:
                final_status_dict["installed"] = True
            if "Active: True" in stdout:
                final_status_dict["active"] = True
            if "Enabled: True" in stdout:
                final_status_dict["enabled"] = True
            if "Exists: True" in stdout:
                final_status_dict["exists"] = True

            if final_status_dict["installed"] and final_status_dict["active"]:
                parsed_status = QLFilterStatus.ACTIVE
            elif final_status_dict["installed"]: # Installed but not active (or enabled status is more nuanced)
                parsed_status = QLFilterStatus.INACTIVE
            elif final_status_dict["exists"]: # Exists but not installed/active (e.g. service file present but not enabled/running)
                 parsed_status = QLFilterStatus.INACTIVE # Or a more specific state
            else: # Not installed, not active, not enabled, not exists
                parsed_status = QLFilterStatus.NOT_INSTALLED
            
            current_app.logger.info(f"Parsed QLFilter status for host {host.name}: {parsed_status.value}")
            update_host(host.id, qlfilter_status=parsed_status)
            return final_status_dict # Return the dict for direct API response if needed
        except Exception as e:
            current_app.logger.error(f"Failed to parse QLFilter status output for host {host.name}: {e}. Output: {stdout}")
            update_host(host.id, qlfilter_status=QLFilterStatus.ERROR)
            final_status_dict["error"] = "Failed to parse status output"
            return final_status_dict
    else:
        current_app.logger.error(f"Failed to check QLFilter status on host: {host.name}. Error: {stderr}")
        update_host(host.id, qlfilter_status=QLFilterStatus.ERROR)
        final_status_dict["error"] = f"Playbook execution failed: {stderr}"
        return final_status_dict
