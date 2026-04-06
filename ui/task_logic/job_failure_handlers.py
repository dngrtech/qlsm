"""
RQ Job Failure Handlers

This module provides failure callback functions for RQ jobs.
When a job fails (including timeouts), these handlers update
database status to ERROR to prevent instances from being stuck
in transitional states.
"""
import logging
from rq.job import Job

log = logging.getLogger(__name__)


def instance_job_failure_handler(job: Job, connection, type, value, traceback):
    """
    Called by RQ when an instance-related job fails or times out.
    Updates the instance status to ERROR.
    
    Args:
        job: The failed RQ job
        connection: Redis connection
        type: Exception type
        value: Exception value
        traceback: Exception traceback
    """
    # Import here to avoid circular imports
    from ui import create_app, db
    from ui.models import QLInstance, InstanceStatus
    from ui.task_logic.common import append_log
    
    # Extract instance_id from job args
    instance_id = None
    if job.args:
        instance_id = job.args[0]
    
    if instance_id is None:
        log.error(f"Job failure handler: Could not extract instance_id from job {job.id}")
        return
    
    log.warning(f"Job failure handler triggered for instance {instance_id}, job {job.id}: {type.__name__}: {value}")
    
    try:
        app = create_app()
        with app.app_context():
            instance = db.session.get(QLInstance, instance_id)
            if not instance:
                log.error(f"Job failure handler: Instance {instance_id} not found")
                return
            
            # Only update if still in a transitional state
            transitional_states = [
                InstanceStatus.DEPLOYING,
                InstanceStatus.CONFIGURING,
                InstanceStatus.RESTARTING,
                InstanceStatus.STARTING,
                InstanceStatus.STOPPING,
                InstanceStatus.DELETING,
            ]
            
            if instance.status in transitional_states:
                error_message = f"Job {job.id} failed: {type.__name__}: {value}"
                append_log(instance, f"Task failed (timeout or crash): {error_message}")
                instance.status = InstanceStatus.ERROR
                db.session.commit()
                log.info(f"Instance {instance_id} status updated to ERROR by failure handler")
            else:
                log.info(f"Instance {instance_id} already in terminal state {instance.status.value}, skipping update")

            # Release entity lock if token is available (safety net)
            lock_token = job.meta.get('lock_token') if job.meta else None
            if lock_token:
                from ui.task_lock import release_lock
                release_lock('instance', instance_id, lock_token)

    except Exception as e:
        log.exception(f"Error in job failure handler for instance {instance_id}: {e}")


def host_job_failure_handler(job: Job, connection, type, value, traceback):
    """
    Called by RQ when a host-related job fails or times out.
    Updates the host status to ERROR.
    
    Args:
        job: The failed RQ job
        connection: Redis connection
        type: Exception type
        value: Exception value
        traceback: Exception traceback
    """
    # Import here to avoid circular imports
    from ui import create_app, db
    from ui.models import Host, HostStatus
    from ui.task_logic.common import append_log
    
    # Extract host_id from job args
    host_id = None
    if job.args:
        host_id = job.args[0]
    
    if host_id is None:
        log.error(f"Job failure handler: Could not extract host_id from job {job.id}")
        return
    
    log.warning(f"Host job failure handler triggered for host {host_id}, job {job.id}: {type.__name__}: {value}")
    
    try:
        app = create_app()
        with app.app_context():
            host = db.session.get(Host, host_id)
            if not host:
                log.error(f"Job failure handler: Host {host_id} not found")
                return
            
            # Only update if still in a transitional state
            transitional_states = [
                HostStatus.PROVISIONING,
                HostStatus.PROVISIONED_PENDING_SETUP,
                HostStatus.REBOOTING,
                HostStatus.DELETING,
                HostStatus.CONFIGURING,
            ]
            
            if host.status in transitional_states:
                error_message = f"Job {job.id} failed: {type.__name__}: {value}"
                append_log(host, f"Task failed (timeout or crash): {error_message}")
                host.status = HostStatus.ERROR
                db.session.commit()
                log.info(f"Host {host_id} status updated to ERROR by failure handler")
            else:
                log.info(f"Host {host_id} already in terminal state {host.status.value}, skipping update")

            # Release entity lock if token is available (safety net)
            lock_token = job.meta.get('lock_token') if job.meta else None
            if lock_token:
                from ui.task_lock import release_lock
                release_lock('host', host_id, lock_token)

    except Exception as e:
        log.exception(f"Error in job failure handler for host {host_id}: {e}")
