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
SQLITE_BUSY_TIMEOUT_SECONDS = 30
# Worst case of one commit_with_retry() with the defaults: every attempt waits
# the full busy_timeout, plus the backoff sleeps between attempts (1s + 2s).
DB_LOCKED_RETRY_BUDGET_SECONDS = (
    DB_LOCKED_RETRY_ATTEMPTS * SQLITE_BUSY_TIMEOUT_SECONDS
    + DB_LOCKED_RETRY_BACKOFF_SECONDS
    * (DB_LOCKED_RETRY_ATTEMPTS * (DB_LOCKED_RETRY_ATTEMPTS - 1) // 2)
)


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
    changes, so they are passed in as `apply_changes` and re-applied in every
    attempt. `apply_changes()` runs inside the attempt: after a rollback it
    reads expired attributes, which can autoflush and hit the lock too.

    `apply_changes()` may return False to skip the write (e.g. the record is
    no longer eligible on a re-check); the session is rolled back and this
    returns False. Otherwise it returns True once committed. Any other error,
    or a lock that outlasts the last attempt, is raised after the rollback,
    leaving the session usable.
    """
    from ui import db

    for attempt in range(1, attempts + 1):
        try:
            if apply_changes() is False:
                db.session.rollback()
                return False
            db.session.commit()
            return True
        except Exception as exc:
            db.session.rollback()
            if not is_db_locked_error(exc) or attempt >= attempts:
                raise
            log.warning(
                "Commit hit a locked database (attempt %s/%s), retrying",
                attempt, attempts,
            )
            time.sleep(backoff * attempt)
    return False


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


# Matches the instance restart endpoint (instance_routes.restart_instance_api).
RESTART_LOCK_TTL_SECONDS = 180


def queue_instance_restart(instance, queued_log, fallback_status, context, previous_logs=None):
    """Queue a restart of `instance` the way the restart endpoint does: take
    the instance lock, save RESTARTING, enqueue with the lock token and
    instance_job_failure_handler, and release the lock if the enqueue fails.

    Bulk updates (plugins, Workshop) call this for many instances on many
    hosts at once, so a crashed or timed-out restart job must still land in
    the failure handler instead of leaving the instance in RESTARTING.

    If the instance is busy (another operation holds its lock) or the enqueue
    fails, the instance gets `fallback_status` and a log line saying the
    restart was not queued. Log lines are prepended to `previous_logs`
    (default: the instance's current logs). Returns True when the restart was
    queued.
    """
    import uuid

    from ui.database import update_instance
    from ui.models import InstanceStatus
    from ui.task_lock import acquire_lock, release_lock
    from ui.tasks import enqueue_task, restart_instance
    from ui.task_logic.job_failure_handlers import instance_job_failure_handler

    if previous_logs is None:
        previous_logs = instance.logs or ''
    lock_token = str(uuid.uuid4())
    try:
        locked = acquire_lock('instance', instance.id, lock_token, ttl=RESTART_LOCK_TTL_SECONDS)
    except Exception:
        log.warning("%s: could not lock instance %s for a restart", context, instance.id, exc_info=True)
        locked = False
    if not locked:
        update_instance(
            instance.id,
            status=fallback_status,
            logs=f"{context}: another operation holds this instance, restart not queued. "
                 f"Restart it when that operation finishes.\n{previous_logs}",
        )
        return False

    try:
        update_instance(instance.id, status=InstanceStatus.RESTARTING, logs=f"{queued_log}\n{previous_logs}")
        enqueue_task(
            restart_instance,
            instance.id,
            lock_token=lock_token,
            on_failure=instance_job_failure_handler,
        )
        return True
    except Exception as exc:
        release_lock('instance', instance.id, lock_token)
        log.warning("%s: could not queue a restart for instance %s", context, instance.id, exc_info=True)
        update_instance(
            instance.id,
            status=fallback_status,
            logs=f"{context}: could not queue a restart ({exc}). Restart it manually.\n{previous_logs}",
        )
        return False
