import datetime
import logging
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.attributes import flag_modified

log = logging.getLogger(__name__)

# SQLite already waits busy_timeout (30s) inside each attempt; these retries
# only cover a writer that holds the lock longer than that.
DB_LOCKED_RETRY_ATTEMPTS = 3
DB_LOCKED_RETRY_BACKOFF_SECONDS = 1.0


def record_host_error(host_id, message, attempts=3):
    """Best effort: put the host in ERROR with a log line after a task died
    with an unhandled exception. Returns True when the write was committed.

    The task's shared session may be unusable here: a flush that failed (for
    example SQLite "database is locked" after busy_timeout) leaves it waiting
    for a rollback, and every later write then fails with PendingRollbackError,
    which is how a finished setup used to leave a host in CONFIGURING. So every
    attempt rolls back, reloads the host and writes again, a few seconds apart.
    """
    import time

    from ui import db
    from ui.models import Host, HostStatus

    for attempt in range(1, attempts + 1):
        try:
            db.session.rollback()
            host = db.session.get(Host, host_id)
            if host is None:
                return False
            host.status = HostStatus.ERROR
            append_log(host, message)
            db.session.commit()
            return True
        except Exception as err:
            log.error(f"Attempt {attempt}/{attempts} to record ERROR for host {host_id} failed: {err}")
            if attempt < attempts:
                time.sleep(2 * attempt)
    db.session.rollback()
    return False


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


def is_db_locked_error(exc):
    """True for SQLite's "database is locked" (another writer holds the lock)."""
    return isinstance(exc, OperationalError) and 'database is locked' in str(exc).lower()


def commit_with_retry(apply_changes, attempts=DB_LOCKED_RETRY_ATTEMPTS,
                      backoff=DB_LOCKED_RETRY_BACKOFF_SECONDS):
    """Apply changes and commit, retrying while SQLite reports a locked database.

    A failed commit needs a rollback, and the rollback drops the pending
    changes, so they are passed in as `apply_changes` and re-applied before
    every attempt. Any other error, or a lock that outlasts the last attempt,
    is raised after the rollback, leaving the session usable.
    """
    from ui import db

    for attempt in range(1, attempts + 1):
        apply_changes()
        try:
            db.session.commit()
            return
        except OperationalError as exc:
            db.session.rollback()
            if not is_db_locked_error(exc) or attempt >= attempts:
                raise
            log.warning(
                "Commit hit a locked database (attempt %s/%s), retrying",
                attempt, attempts,
            )
            time.sleep(backoff * attempt)


def record_task_failure(apply_changes):
    """Persist a task's failure state from its except path.

    The exception that got us here may have been the session itself (a
    failed flush or commit), so roll back first: otherwise the next commit
    fails with "transaction has been rolled back" and the status is lost.
    If the failure state still cannot be committed, this raises, so RQ marks
    the job failed and the job's on_failure handler gets its own chance to
    move the record out of its transitional status.
    """
    from ui import db

    db.session.rollback()
    commit_with_retry(apply_changes)
