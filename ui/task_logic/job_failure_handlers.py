"""
RQ Job Failure Handlers

This module provides failure callback functions for RQ jobs.
When a job fails (including timeouts), these handlers update
database status to ERROR to prevent instances from being stuck
in transitional states.
"""
import logging
from rq.exceptions import AbandonedJobError
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
    from ui.task_logic.common import append_log, commit_with_retry
    
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

            lock_token = job.meta.get('lock_token') if job.meta else None

            # The worker died mid-job: the service may be fine, so report what
            # is actually running instead of blindly setting ERROR.
            if issubclass(type, AbandonedJobError):
                from ui.task_logic.interrupted_job_recovery import recover_interrupted_instance
                recover_interrupted_instance(
                    instance_id, job.id, lock_token, f"{type.__name__}: {value}"
                )
                return

            from ui.task_lock import lock_superseded, release_lock
            if lock_superseded('instance', instance_id, lock_token):
                log.info(f"Instance {instance_id} lock held by a newer operation, skipping failure handling for job {job.id}")
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
            error_message = f"Job {job.id} failed: {type.__name__}: {value}"
            skip_reason = {}

            def _mark_failed():
                # Re-checked on every attempt: during a retry backoff a newer
                # operation can take the lock and save its own status, which
                # this stale callback must not overwrite with ERROR.
                if lock_superseded('instance', instance_id, lock_token):
                    skip_reason['why'] = 'superseded'
                    return False
                current = db.session.get(QLInstance, instance_id)
                if current is None:
                    skip_reason['why'] = 'gone'
                    return False
                if current.status not in transitional_states:
                    skip_reason['why'] = current.status.value
                    return False
                append_log(current, f"Task failed (timeout or crash): {error_message}")
                current.status = InstanceStatus.ERROR

            try:
                if commit_with_retry(_mark_failed):
                    log.info(f"Instance {instance_id} status updated to ERROR by failure handler")
                elif skip_reason.get('why') == 'superseded':
                    log.info(f"Instance {instance_id} lock held by a newer operation, skipping failure handling for job {job.id}")
                    return
                else:
                    log.info(f"Instance {instance_id} not in a transitional state ({skip_reason.get('why')}), skipping update")
            finally:
                # Release entity lock if token is available (safety net). It
                # runs even when the status could not be saved; a newer owner's
                # lock is left alone.
                if lock_token and skip_reason.get('why') != 'superseded':
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
    from ui.task_logic.common import append_log, commit_with_retry
    
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
            error_message = f"Job {job.id} failed: {type.__name__}: {value}"
            lock_token = job.meta.get('lock_token') if job.meta else None
            locked_instance_ids = (
                job.meta.get('locked_instance_ids', []) if job.meta else []
            )
            skip_reason = {}
            from ui.task_lock import lock_superseded

            def _mark_failed():
                # Re-checked on every attempt, like the instance handler: a
                # newer operation (a deletion saving DELETING) can take the
                # host lock during a retry backoff.
                if lock_superseded('host', host_id, lock_token):
                    skip_reason['why'] = 'superseded'
                    return False
                current = db.session.get(Host, host_id)
                if current is None:
                    skip_reason['why'] = 'gone'
                    return False
                if current.status not in transitional_states:
                    skip_reason['why'] = current.status.value
                    return False
                append_log(current, f"Task failed (timeout or crash): {error_message}")
                current.status = HostStatus.ERROR

            try:
                if commit_with_retry(_mark_failed):
                    log.info(f"Host {host_id} status updated to ERROR by failure handler")
                else:
                    log.info(f"Host {host_id} not updated by failure handler ({skip_reason.get('why')})")
            finally:
                # Release rerun instance locks before the host lock so a crashed
                # worker does not leave the next setup attempt blocked until TTL.
                # Token-checked releases, run even when the status save failed.
                if lock_token:
                    from ui.task_lock import release_lock, release_locks
                    release_locks(
                        'instance',
                        locked_instance_ids,
                        lock_token,
                    )
                    release_lock('host', host_id, lock_token)

    except Exception as e:
        log.exception(f"Error in job failure handler for host {host_id}: {e}")


def runtime_upgrade_job_failure_handler(job: Job, connection, type, value, traceback):
    """Called by RQ when a host runtime upgrade (or its recovery) job fails,
    times out or is abandoned by a dead worker. Durably requests recovery and
    enqueues recover_host_runtime; if that enqueue fails, the periodic
    reconciler finds the operation and retries. Never raises."""
    from ui import create_app
    from ui.task_logic.host_runtime_upgrade_recovery import handle_upgrade_job_failure

    log.warning(f"Runtime upgrade job {job.id} failed: {getattr(type, '__name__', type)}: {value}")
    try:
        app = create_app()
        with app.app_context():
            handle_upgrade_job_failure(job, type, value)
    except Exception as e:
        log.error(f"Runtime upgrade failure handler error for job {job.id}: {e}", exc_info=True)
