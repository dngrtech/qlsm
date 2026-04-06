# This file defines the RQ tasks that are enqueued by the Flask application.
# It imports the actual task logic from the ui.task_logic package.

# Import the app context decorator
from ui.task_context import with_app_context

# Import Ansible task logic from new files
from ui.task_logic.ansible_instance_mgmt import (
    deploy_instance_logic,
    restart_instance_logic,
    stop_instance_logic,
    start_instance_logic,
    apply_instance_config_logic,
    delete_instance_logic,
    reconfigure_instance_lan_rate_logic
)
from ui.task_logic.ansible_host_setup import setup_host_ansible_logic
from ui.task_logic.ansible_host_restart import restart_host_ansible_logic
from ui.task_logic.ansible_host_rename import rename_host_logic
from ui.task_logic.ansible_host_auto_restart import configure_host_auto_restart_logic

# Import Terraform task logic from new files
from ui.task_logic.terraform_provision import provision_host_logic
from ui.task_logic.terraform_destroy import destroy_host_logic

# Import standalone host task logic
from ui.task_logic.standalone_host_setup import setup_standalone_host_logic
from ui.task_logic.standalone_host_remove import remove_standalone_host_logic

# Import QLFilter management task logic
from ui.task_logic.ansible_qlfilter_mgmt import (
    install_qlfilter_logic,
    uninstall_qlfilter_logic,
    check_qlfilter_status_logic
)
from ui.task_logic.ansible_workshop_update import force_update_workshop_logic

# Import RQ library
from ui import rq


def enqueue_task(task_func, *args, on_failure=None, **kwargs):
    """Enqueue a task, properly passing on_failure to RQ's enqueue_call.

    Flask-RQ2's .queue() doesn't recognize on_failure and forwards it as a
    task kwarg, causing a TypeError. This helper replicates .queue() logic
    while passing on_failure directly to RQ's enqueue_call().
    """
    helper = task_func.helper
    queue_name = kwargs.pop('queue', helper.queue_name)
    timeout = kwargs.pop('timeout', helper.timeout)
    result_ttl = kwargs.pop('result_ttl', helper.result_ttl)
    ttl = kwargs.pop('ttl', helper.ttl)
    depends_on = kwargs.pop('depends_on', helper._depends_on)
    job_id = kwargs.pop('job_id', None)
    at_front = kwargs.pop('at_front', helper._at_front)
    meta = dict(kwargs.pop('meta', helper._meta) or {})  # Defensive copy
    description = kwargs.pop('description', helper._description)

    # Store lock_token in job meta for failure handler access.
    # IMPORTANT: Do NOT pop lock_token — it must also pass through as a
    # task kwarg so the task's try/finally can release it.
    lock_token = kwargs.get('lock_token')
    if lock_token:
        meta['lock_token'] = lock_token

    return helper.rq.get_queue(queue_name).enqueue_call(
        helper.wrapped,
        args=args,
        kwargs=kwargs,
        timeout=timeout,
        result_ttl=result_ttl,
        ttl=ttl,
        depends_on=depends_on,
        job_id=job_id,
        at_front=at_front,
        meta=meta,
        description=description,
        on_failure=on_failure,
    )


# --- Task Definitions ---
# These functions are the entry points for RQ jobs.
# They simply call the corresponding logic functions from the task_logic package.
# Each task is decorated with with_app_context to ensure database access works.
# Timeouts are set on instance tasks - on_failure callbacks are passed at queue time.

@rq.job(timeout=1200)
@with_app_context
def provision_host(host_id, lock_token=None):
    """RQ task entry point for provisioning a host."""
    preserve_lock_for_setup = False
    try:
        # Pass lock_token only when present; provision_host_logic will forward it
        # to setup_host_ansible when enqueueing (handled in Task 6).
        if lock_token:
            result = provision_host_logic(host_id, lock_token=lock_token)
            from ui import db
            from ui.models import Host, HostStatus

            host = db.session.get(Host, host_id)
            preserve_lock_for_setup = (
                host is not None and host.status == HostStatus.PROVISIONED_PENDING_SETUP
            )
            return result
        return provision_host_logic(host_id)
    finally:
        if lock_token and not preserve_lock_for_setup:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=1200)
@with_app_context
def destroy_host(host_id, lock_token=None):
    """RQ task entry point for destroying a host."""
    try:
        return destroy_host_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=1200)
@with_app_context
def deploy_instance(instance_id, lock_token=None):
    """RQ task entry point for deploying a QL instance."""
    try:
        return deploy_instance_logic(instance_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('instance', instance_id, lock_token)

@rq.job(timeout=120)
@with_app_context
def restart_instance(instance_id, lock_token=None):
    """RQ task entry point for restarting a QL instance."""
    try:
        return restart_instance_logic(instance_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('instance', instance_id, lock_token)

@rq.job(timeout=120)
@with_app_context
def stop_instance(instance_id, lock_token=None):
    """RQ task entry point for stopping a QL instance."""
    try:
        return stop_instance_logic(instance_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('instance', instance_id, lock_token)

@rq.job(timeout=120)
@with_app_context
def start_instance(instance_id, lock_token=None):
    """RQ task entry point for starting a QL instance."""
    try:
        return start_instance_logic(instance_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('instance', instance_id, lock_token)

@rq.job(timeout=300)
@with_app_context
def apply_instance_config(instance_id, restart=True, lock_token=None):
    """RQ task entry point for applying configuration to a QL instance."""
    try:
        return apply_instance_config_logic(instance_id, restart=restart)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('instance', instance_id, lock_token)

@rq.job(timeout=300)
@with_app_context
def delete_instance(instance_id, lock_token=None):
    """RQ task entry point for deleting a QL instance."""
    try:
        return delete_instance_logic(instance_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('instance', instance_id, lock_token)

@rq.job(timeout=300)
@with_app_context
def reconfigure_instance_lan_rate(instance_id, lock_token=None):
    """RQ task entry point for reconfiguring LAN rate settings for a QL instance."""
    try:
        return reconfigure_instance_lan_rate_logic(instance_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('instance', instance_id, lock_token)

@rq.job(timeout=1200)
@with_app_context
def setup_host_ansible(host_id, lock_token=None):
    """RQ task entry point for setting up a host via Ansible after provisioning."""
    try:
        return setup_host_ansible_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=120)
@with_app_context
def restart_host_task(host_id, lock_token=None):
    """RQ task entry point for restarting a host using Ansible."""
    try:
        return restart_host_ansible_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=120)
@with_app_context
def configure_host_auto_restart_task(host_id, schedule_cron, lock_token=None):
    """RQ task entry point for configuring host auto-restart."""
    try:
        return configure_host_auto_restart_logic(host_id, schedule_cron)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=300)
@with_app_context
def rename_host_task(host_id, old_name, new_name, lock_token=None):
    """RQ task entry point for renaming a host (inventory + Ansible)."""
    try:
        return rename_host_logic(host_id, old_name, new_name)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

# --- QLFilter Management Tasks ---

@rq.job(timeout=300)
@with_app_context
def install_qlfilter_task(host_id, lock_token=None):
    """RQ task entry point for installing QLFilter on a host."""
    try:
        return install_qlfilter_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=300)
@with_app_context
def uninstall_qlfilter_task(host_id, lock_token=None):
    """RQ task entry point for uninstalling QLFilter from a host."""
    try:
        return uninstall_qlfilter_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=120)
@with_app_context
def check_qlfilter_status_task(host_id, lock_token=None):
    """RQ task entry point for checking QLFilter status on a host."""
    try:
        return check_qlfilter_status_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)


# --- Workshop Management Tasks ---

@rq.job(timeout=300)
@with_app_context
def force_update_workshop_task(host_id, workshop_id, restart_instance_ids, lock_token=None):
    """RQ task entry point for force updating a workshop item on a host."""
    try:
        return force_update_workshop_logic(host_id, workshop_id, restart_instance_ids)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

# --- Standalone Host Tasks ---

@rq.job(timeout=1200)
@with_app_context
def setup_standalone_host_ansible(host_id, lock_token=None):
    """RQ task entry point for setting up a standalone host via Ansible."""
    try:
        return setup_standalone_host_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)

@rq.job(timeout=300)
@with_app_context
def remove_standalone_host(host_id, lock_token=None):
    """RQ task entry point for removing a standalone host from inventory."""
    try:
        return remove_standalone_host_logic(host_id)
    finally:
        if lock_token:
            from ui.task_lock import release_lock
            release_lock('host', host_id, lock_token)


# Note: The app context for database access is now provided by the with_app_context
# decorator, which creates a Flask application context for each task execution.
