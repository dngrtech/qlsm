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
    from ui.models import db

    host.lan_rate_uses_hook = True
    # Commit BEFORE the loop so inner commits see the updated flag.
    db.session.commit()

    # Capture IDs before the loop — inner commits may expire host.instances.
    instance_ids_to_migrate = [
        i.id for i in host.instances if i.lan_rate_enabled
    ]

    ok = 0
    failed = 0
    for instance_id in instance_ids_to_migrate:
        result = apply_instance_hooks_logic(instance_id, restart_service=True)
        if result is True:
            ok += 1
        else:
            failed += 1
            append_log(host, f"instance id={instance_id} migration result: {result}")

    return ok, failed
