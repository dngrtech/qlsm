# ui/task_logic/ansible_workshop_update.py

import logging
from rq import get_current_job
from flask import current_app

from ui import rq
from ui.models import HostStatus, InstanceStatus
from ui.database import get_host, update_host, get_instance, update_instance
from ui.pending_changes import SOURCE_WORKSHOP_UPDATE, record_pending_change
from . import service_runtime
from .ansible_runner import _run_host_ansible_playbook


log = logging.getLogger(__name__)


def _capture_pending_baselines(host, instances):
    try:
        baselines = service_runtime.probe_host_invocation_ids(host, instances)
    except Exception:
        current_app.logger.warning(
            "Workshop update succeeded, but runtime baseline capture failed for host %s",
            host.id,
            exc_info=True,
        )
        return {}
    if not isinstance(baselines, dict):
        current_app.logger.warning(
            "Workshop update succeeded without runtime baselines for host %s",
            host.id,
        )
        return {}
    return baselines


def force_update_workshop_logic(host_id, workshop_id, restart_instance_ids):
    host = get_host(host_id)
    if not host:
        current_app.logger.error(f"force_update_workshop_logic: Host {host_id} not found.")
        return False

    original_host_logs = host.logs or ""
    update_host(host.id, status=HostStatus.ACTIVE, logs=f"Initiating Workshop item {workshop_id} update...\n{original_host_logs}")

    # Set all instances on this host to CONFIGURING
    original_instance_states = {}
    for instance in host.instances:
        # Save previous state to revert on failure
        original_instance_states[instance.id] = {
            "status": instance.status,
            "logs": instance.logs or ""
        }
        update_instance(
            instance.id, 
            status=InstanceStatus.CONFIGURING, 
            logs=f"Updating Workshop item {workshop_id}...\n{instance.logs or ''}"
        )

    try:
        playbook_name = "force_update_workshop.yml"
        extra_vars = {
            "item_id": workshop_id
        }

        current_app.logger.info(f"Executing workshop update playbook for host: {host.name}")
        job = get_current_job()

        success, stdout, stderr = _run_host_ansible_playbook(
            host=host,
            playbook_name=playbook_name,
            extravars=extra_vars
        )

        if success:
            current_app.logger.info(f"Workshop item {workshop_id} updated on {host.name}.")
            update_host(host.id, status=HostStatus.ACTIVE, logs=f"Workshop item {workshop_id} updated.\n{original_host_logs}")

            pending_instances = [
                instance for instance in host.instances
                if (
                    original_instance_states[instance.id]["status"] != InstanceStatus.STOPPED
                    and instance.id not in restart_instance_ids
                )
            ]
            baselines = (
                _capture_pending_baselines(host, pending_instances)
                if pending_instances else {}
            )

            # Now handle instances
            from ui.tasks import restart_instance
            for instance in host.instances:
                orig_state = original_instance_states[instance.id]["status"]

                if orig_state == InstanceStatus.STOPPED:
                    update_instance(
                        instance.id,
                        status=InstanceStatus.STOPPED,
                        logs=f"Workshop {workshop_id} updated while stopped; service left stopped.\n{original_instance_states[instance.id]['logs']}"
                    )
                elif instance.id in restart_instance_ids:
                    update_instance(
                        instance.id,
                        status=InstanceStatus.RESTARTING,
                        logs=f"Workshop {workshop_id} updated. Queuing restart...\n{original_instance_states[instance.id]['logs']}"
                    )
                    restart_instance.queue(instance.id)
                else:
                    # update_instance below commits this record too.
                    record_pending_change(
                        instance.id,
                        SOURCE_WORKSHOP_UPDATE,
                        [],
                        [{'field': 'workshop_item', 'before': None, 'after': str(workshop_id)}],
                    )
                    update_instance(
                        instance.id,
                        status=InstanceStatus.UPDATED,
                        runtime_invocation_id=baselines.get(str(instance.port)),
                        logs=f"Workshop {workshop_id} updated.\n{original_instance_states[instance.id]['logs']}"
                    )
            return True
        else:
            current_app.logger.error(f"Failed to update workshop on {host.name}: {stderr}")
            update_host(host.id, status=HostStatus.ERROR, logs=f"Workshop update failed: {stderr}.\n{original_host_logs}")
            
            # Revert instances to previous states
            for instance in host.instances:
                update_instance(
                    instance.id,
                    status=original_instance_states[instance.id]["status"],
                    logs=f"Workshop update failed. Reverting state.\n{original_instance_states[instance.id]['logs']}"
                )
            return False

    except Exception as e:
        current_app.logger.exception(f"Unexpected error in force_update_workshop_logic: {e}")
        job = get_current_job()
        job_str = job.id if job else "unknown_job"
        update_host(host.id, status=HostStatus.ERROR, logs=f"Unexpected Python error during workshop update (Job ID: {job_str}): {str(e)}\n{original_host_logs}")
        
        # Revert instances
        for instance in host.instances:
            update_instance(
                instance.id,
                status=original_instance_states[instance.id]["status"],
                logs=f"Workshop update failed due to internal error.\n{original_instance_states[instance.id]['logs']}"
            )
        return False
