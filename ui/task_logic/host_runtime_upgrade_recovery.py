"""Durable recovery of interrupted host runtime upgrades.

    start_upgrade_job(operation_id)        pre-assign the job id in the row, then
                                           enqueue upgrade_host_runtime (Task 6)
    request_recovery(operation_id, ...)    CAS a new job id into the row, then
                                           enqueue recover_host_runtime
    recover_host_runtime_logic(op_id)      take over once the old job is dead and
                                           finish: preparation-only -> failed_preparation,
                                           anything later -> idempotent rollback
    handle_upgrade_job_failure(job, ...)   the RQ failure callback body
    reconcile_runtime_upgrades()           startup sweep + every 60 s from the
                                           status poller: find nonterminal
                                           operations whose job is dead

Recovery never races a live worker: it takes over only when the recorded RQ
job is gone, terminal or heartbeat-stale, and every execution bumps the
fencing token, which the remote playbooks check before each write phase. A
remote play still holding the host's runtime lock, or an unreachable host,
keeps the operation pending (host ERROR, reservation kept) for a later retry.
"""
import datetime
import logging
import uuid

from sqlalchemy import update

from ui import db
from ui.models import Host
from ui.models_runtime_upgrade import NONTERMINAL_STATES, HostRuntimeUpgradeOperation
from ui.task_logic.common import append_log

from .host_runtime_upgrade import fail_preparation, is_job_timeout, mark_recovery_required, take_ownership
from .host_runtime_upgrade_deps import UpgradeDeps
from .host_runtime_upgrade_state import StaleExecution, safe_error

log = logging.getLogger(__name__)

RECONCILE_INTERVAL_SECONDS = 60
# A row whose job id is not recorded yet may still be being enqueued.
UNASSIGNED_JOB_GRACE_SECONDS = 120
# How often an incomplete rollback (recovery_required) is retried.
RETRY_INTERVAL_SECONDS = 300


def _new_job_id():
    return uuid.uuid4().hex


def _swap_job_id(operation_id, expected, new_job_id, recovery):
    """CAS the row's rq_job_id from `expected` to `new_job_id`."""
    condition = (HostRuntimeUpgradeOperation.rq_job_id.is_(None) if expected is None
                 else HostRuntimeUpgradeOperation.rq_job_id == expected)
    values = {'rq_job_id': new_job_id, 'updated_at': datetime.datetime.utcnow()}
    if recovery:
        values['recovery_required'] = True
    result = db.session.execute(
        update(HostRuntimeUpgradeOperation)
        .where(HostRuntimeUpgradeOperation.id == operation_id,
               HostRuntimeUpgradeOperation.state.in_(NONTERMINAL_STATES), condition)
        .values(**values))
    db.session.commit()
    return result.rowcount == 1


def start_upgrade_job(operation_id, *, enqueue=None):
    """Record a job id for a freshly created operation, then enqueue the
    upgrade with the operation-specific failure callback. If the enqueue
    fails, the reconciler finds the missing job and recovers the operation.
    Returns the job id."""
    job_id = _new_job_id()
    op = db.session.get(HostRuntimeUpgradeOperation, operation_id)
    if op is None or not _swap_job_id(operation_id, op.rq_job_id, job_id, recovery=False):
        raise RuntimeError(f'Runtime upgrade {operation_id} cannot be started')
    if enqueue is None:
        from ui.task_logic.job_failure_handlers import runtime_upgrade_job_failure_handler
        from ui.tasks import enqueue_task, upgrade_host_runtime

        def enqueue(op_id, job_id):
            return enqueue_task(upgrade_host_runtime, op_id, job_id=job_id,
                                on_failure=runtime_upgrade_job_failure_handler)
    enqueue(operation_id, job_id)
    return job_id


def request_recovery(operation_id, *, deps=None, expected_job_id=None, reason=None):
    """Hand the operation to a new recovery job. Returns the job id, or None
    when it is terminal or someone else already handed it over."""
    deps = deps or UpgradeDeps()
    op = db.session.get(HostRuntimeUpgradeOperation, operation_id)
    if op is None or op.is_terminal:
        return None
    expected = op.rq_job_id if expected_job_id is None else expected_job_id
    job_id = _new_job_id()
    if not _swap_job_id(operation_id, expected, job_id, recovery=True):
        return None
    if reason:
        host = db.session.get(Host, op.host_id)
        if host is not None:
            append_log(host, f'Runtime upgrade interrupted ({safe_error(reason)}); recovery scheduled.')
            db.session.commit()
    try:
        deps.enqueue_recovery(operation_id, job_id)
    except Exception:
        # The row now names a job that does not exist: the reconciler sees it
        # as dead and retries.
        log.exception('Upgrade %s: could not enqueue recovery job', operation_id)
    return job_id


def recover_host_runtime_logic(operation_id, *, deps=None, job_id=None):
    """Finish an interrupted operation. Returns True when it is terminal and
    the host is in a defined state, False after a rollback/cancellation, or a
    `pending:` string when it must be retried later."""
    from .host_runtime_upgrade_rollback import rollback

    deps = deps or UpgradeDeps()
    op = db.session.get(HostRuntimeUpgradeOperation, operation_id)
    if op is None:
        return f'Error: runtime upgrade operation {operation_id} not found'
    if op.is_terminal:
        return True
    previous = op.rq_job_id
    if previous and previous != job_id and deps.job_alive(previous):
        return f'pending: job {previous} still owns runtime upgrade {operation_id}'

    execution = take_ownership(operation_id, job_id, deps)
    if execution is None:
        return f'pending: could not take ownership of runtime upgrade {operation_id}'
    if not execution.locked:
        return f'pending: execution locks of runtime upgrade {operation_id} are held elsewhere'
    try:
        if execution.op.state == 'preparing':
            # Quiescing intent is persisted before anything is stopped, so
            # nothing live changed: discard the preparation.
            return fail_preparation(execution, 'the upgrade worker was interrupted before any change',
                                    cleanup_snapshot=True)
        return rollback(execution)
    except StaleExecution as exc:
        log.warning('Recovery of upgrade %s stopped: %s', operation_id, exc)
        db.session.rollback()
        return f'pending: {exc}'
    except Exception as exc:
        if is_job_timeout(exc):
            # Stop work in this job; the reconciler hands it to a new one.
            mark_recovery_required(execution, f'recovery worker timed out: {exc}')
            return f'pending: recovery of runtime upgrade {operation_id} timed out'
        log.exception('Recovery of upgrade %s failed', operation_id)
        mark_recovery_required(execution, f'recovery failed: {safe_error(exc)}', state='recovery_required')
        return f'pending: recovery failed: {safe_error(exc)}'
    finally:
        execution.release_locks()


def handle_upgrade_job_failure(job, exc_type, value, *, deps=None):
    """RQ failure callback body (app context required): the worker died or
    timed out, so durably request recovery and enqueue it."""
    if not job.args:
        return None
    op = db.session.get(HostRuntimeUpgradeOperation, job.args[0])
    if op is None or op.is_terminal:
        return None
    if op.rq_job_id not in (None, job.id):
        return None  # a newer job already owns it
    reason = f'{getattr(exc_type, "__name__", exc_type)}: {value}'
    return request_recovery(op.id, deps=deps, expected_job_id=op.rq_job_id, reason=reason)


def reconcile_runtime_upgrades(*, deps=None, now=None):
    """Request recovery for every nonterminal operation whose job is dead.
    Returns the operation ids handed over."""
    deps = deps or UpgradeDeps()
    now = now or datetime.datetime.utcnow()
    handed = []
    rows = (HostRuntimeUpgradeOperation.query
            .filter(HostRuntimeUpgradeOperation.state.in_(NONTERMINAL_STATES))
            .order_by(HostRuntimeUpgradeOperation.created_at).all())
    for op in rows:
        try:
            age = (now - (op.updated_at or op.created_at)).total_seconds()
            if op.rq_job_id is None and age < UNASSIGNED_JOB_GRACE_SECONDS:
                continue
            if deps.job_alive(op.rq_job_id):
                continue
            if op.state == 'recovery_required' and age < RETRY_INTERVAL_SECONDS:
                continue
            if request_recovery(op.id, deps=deps, expected_job_id=op.rq_job_id,
                                reason='no live worker owns it'):
                handed.append(op.id)
        except Exception:
            log.exception('Reconcile of runtime upgrade %s failed', op.id)
            db.session.rollback()
    return handed
