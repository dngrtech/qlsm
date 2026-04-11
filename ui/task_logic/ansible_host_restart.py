# ui/task_logic/ansible_host_restart.py

import logging
import os
import random
import shutil
import time
import subprocess
from pathlib import Path
from rq import get_current_job
from flask import current_app

# Import database and models - requires app context
from ui import db
from ui.models import Host, HostStatus # Need Host and HostStatus
from .common import append_log # Import append_log from common module
from ui.database import get_host, update_host # Import get_host and update_host from ui.database
from .ansible_runner import _run_host_ansible_playbook, SimpleAnsibleResult # Import the runner helper and result class

from ui import rq  # or however you get your RQ queue

log = logging.getLogger(__name__)

def restart_host_ansible_logic(host_id):
    host = get_host(host_id)
    if not host:
        current_app.logger.error(f"restart_host_ansible_logic: Host with ID {host_id} not found.")
        return False

    original_logs = host.logs or "" # Store original logs
    update_host(host.id, status=HostStatus.REBOOTING, logs=f"Initiating host restart...\n{original_logs}")

    try:
        playbook_name = "restart_host.yml" # Just the playbook name
        # extravars are typically for things specific to the playbook run, 
        # host.name is used by _run_host_ansible_playbook for -l limit
        # If restart_host.yml needs target_host explicitly, it can be added.
        # For now, assuming -l host.name is sufficient.
        extra_vars = {}
        if host.provider == 'self':
            extra_vars['critical_services'] = ['ssh']
        # If your playbook /ansible/playbooks/restart_host.yml uses a variable like `target_host_name`
        # then you would define it here:
        # extra_vars = {"target_host_name": host.name} 

        current_app.logger.info(f"Executing restart playbook for host: {host.name} (ID: {host.id})")

        job = get_current_job()

        # Corrected function call: Use _run_host_ansible_playbook
        # It returns: success_bool, stdout_content, stderr_content
        success, stdout, stderr = _run_host_ansible_playbook(
            host=host, # First argument is the host object
            playbook_name=playbook_name, 
            extravars=extra_vars
        )

        if success:
            current_app.logger.info(f"Host {host.name} restarted successfully.")
            # Assuming restart puts it back to ACTIVE. If it needs checks, that's more complex.
            # For now, let's optimistically set it to ACTIVE.
            # The frontend polling should eventually reflect the true state if it takes time.
            update_host(host.id, status=HostStatus.ACTIVE, logs=f"Host restarted successfully via Ansible.\n{original_logs}")
            return True
        else:
            current_app.logger.error(f"Failed to restart host {host.name}. Error: {stderr}")
            update_host(host.id, status=HostStatus.ERROR, logs=f"Host restart via Ansible failed. Error: {stderr}\n{original_logs}")
            return False
            
    except Exception as e:
        current_app.logger.exception(f"Unexpected error in restart_host_ansible_logic for host {host_id} after setting to REBOOTING: {e}")
        job = get_current_job() # Try to get job ID again for logging
        job_id_str = job.id if job else "unknown_job"
        error_message = f"Unexpected Python error during host restart task (Job ID: {job_id_str}): {str(e)}"
        update_host(host.id, status=HostStatus.ERROR, logs=f"{error_message}\n{original_logs}")
        return False
