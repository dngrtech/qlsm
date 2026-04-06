from flask import current_app
from ui import db
from ui.models import Host, HostStatus
from rq import get_current_job
from ui.task_logic.ansible_runner import _run_host_ansible_playbook


def configure_host_auto_restart_logic(host_id, schedule_cron):
    """
    Configures the auto-restart schedule on the host via Ansible.
    
    Args:
        host_id (int): The ID of the host.
        schedule_cron (str): The cron expression (e.g., '0 4 * * *'). If None or empty, the cron job is removed.
    """
    host = db.session.get(Host, host_id)
    if not host:
        current_app.logger.error(f"Host {host_id} not found for auto-restart configuration.")
        return False

    job = get_current_job()

    current_app.logger.info(f"Starting auto-restart configuration for host: {host.name} (Schedule: {schedule_cron or 'None'})")

    extra_vars = {}
    if schedule_cron:
        extra_vars = {
            'on_calendar': schedule_cron
        }

    # Use the existing function for host playbooks
    success, stdout_str, stderr_str = _run_host_ansible_playbook(
        host=host,
        playbook_name='configure_auto_restart.yml',
        extravars=extra_vars
    )
    
    if success:
        current_app.logger.info(f"Successfully configured auto-restart for host {host.name}.")
        host.auto_restart_schedule = schedule_cron
        host.status = HostStatus.ACTIVE
        host.logs = f"Auto-restart configured successfully.\n{host.logs or ''}"
    else:
        current_app.logger.error(f"Failed to configure auto-restart for host {host.name}.")
        host.status = HostStatus.ERROR
        host.logs = f"Auto-restart configuration failed.\n{host.logs or ''}"

    db.session.commit()
    return success
