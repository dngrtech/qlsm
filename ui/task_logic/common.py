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


def _reconcile_host_instances_after_setup(host):
    """Reconcile every host instance once from a pre-commit status snapshot."""
    from ui.models import db, InstanceStatus
    from ui.task_logic.instance_reconciliation import (
        reconcile_instance_after_host_setup,
    )

    instance_snapshots = [
        (instance.id, instance.status)
        for instance in host.instances
    ]

    host.lan_rate_uses_hook = True
    db.session.commit()

    ok = 0
    failed = 0
    for instance_id, original_status in instance_snapshots:
        restart_service = original_status is not InstanceStatus.STOPPED
        target_status = (
            InstanceStatus.RUNNING
            if restart_service
            else InstanceStatus.STOPPED
        )
        result = reconcile_instance_after_host_setup(
            instance_id,
            restart_service=restart_service,
            target_status=target_status,
        )
        if result is True:
            ok += 1
        else:
            failed += 1
            append_log(host, f"instance id={instance_id} reconciliation failed")

    return ok, failed
