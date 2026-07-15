import datetime
import logging
from sqlalchemy.orm.attributes import flag_modified

log = logging.getLogger(__name__)


def append_log(model_instance, message):
    """Appends a timestamped log message to the instance's log field."""
    if not model_instance:
        return # Should not happen if called correctly

    # Use local time and include timezone name (e.g., PDT)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')
    log_entry = f"[{timestamp}] {message}\n"

    # Append log entry, handling None case
    if model_instance.logs is None:
        model_instance.logs = log_entry
    else:
        model_instance.logs += log_entry

    # Explicitly mark the 'logs' field as modified for SQLAlchemy
    flag_modified(model_instance, "logs")

    # Note: Committing should happen in the main task function after calling this.


def _migrate_host_instances_to_hook(host):
    """Flip Host.lan_rate_uses_hook and reconcile per-instance hook state.

    Captures instance IDs BEFORE the loop because apply_instance_hooks_logic
    commits internally and would expire host.instances mid-loop.
    Returns (migrated_ok, migrated_failed) counts.
    """
    # Lazy imports to avoid circular imports at module load time.
    from ui.task_logic.ansible_instance_hooks import apply_instance_hooks_logic
    from ui.models import db, InstanceStatus

    host.lan_rate_uses_hook = True
    # Commit BEFORE the loop so inner commits see the updated flag.
    db.session.commit()

    # Capture IDs and running state before the loop — inner commits may expire
    # host.instances. Only restart instances that were already running; leave
    # intentionally-stopped instances in the stopped state.
    instances_to_migrate = [
        (i.id, i.status == InstanceStatus.RUNNING)
        for i in host.instances if i.lan_rate_enabled
    ]

    ok = 0
    failed = 0
    for instance_id, was_running in instances_to_migrate:
        result = apply_instance_hooks_logic(instance_id, restart_service=was_running)
        if result is True:
            ok += 1
        else:
            failed += 1
            append_log(host, f"instance id={instance_id} migration result: {result}")

    return ok, failed


def _restart_running_instances(host):
    """Restart all RUNNING instances on a host.

    Used after a minqlx rebuild so instances load the new build. The restart
    runs sync_instance_configs_and_restart.yml, which mirrors the whole of
    minqlx-shared/ into the instance first — both the binary and the minqlx/
    Python package. Both halves must land together: a patched binary against a
    stale Python package leaves patched event dispatchers unregistered.
    Stopped instances are left untouched.
    Returns (restarted_ok, restarted_failed) counts.
    """
    from ui.task_logic.ansible_instance_mgmt import restart_instance_logic
    from ui.models import db, InstanceStatus

    running_ids = [
        i.id for i in host.instances if i.status == InstanceStatus.RUNNING
    ]

    ok = 0
    failed = 0
    for instance_id in running_ids:
        result = restart_instance_logic(instance_id)
        if result is True:
            ok += 1
        else:
            failed += 1
            append_log(host, f"instance id={instance_id} restart result: {result}")
        db.session.commit()

    return ok, failed
