"""Whole-host rollback of a runtime upgrade to minqlx. Idempotent: the
orchestrator runs it after a failed step, recovery runs it (again) after a
worker died, and every replay re-verifies the actual state.

Order: persist `rolling_back`; stop and verify every instance the upgrade
touched; put the host back on minqlx (independently of any per-instance
error); then, per instance, restore the snapshot (local tree + DB fields),
restore the remote managed-file inventory with the original unit, and bring
it back to its original RUNNING/STOPPED state. Failures are isolated per
instance and phase. An instance that cannot be quiesced keeps its running
files. A remote "not now" (lock still held by another play, host unreachable)
keeps the operation pending for a retry rather than failing it.
An instance whose rollback already completed in an earlier pass is never
stopped, restored or restarted again by a retry: its state is only re-read
and any drift is recorded for the operator.
"""
import logging

from ui import db
from ui.models import HostStatus, InstanceStatus
from ui.runtime import MINQLX
from ui.runtime_upgrade_conversion import discard_conversion_leftovers
from ui.runtime_upgrade_snapshot import restore_instance
from ui.task_logic.common import append_log

from .host_runtime_upgrade import conversion_tag, finalize_remote, is_job_timeout, live_config_dir
from .host_runtime_upgrade_deps import is_remote_pending
from .host_runtime_upgrade_state import StaleExecution, safe_error

log = logging.getLogger(__name__)

DEFAULT_REASON = 'the upgrade worker was interrupted'


def _touched(outcome):
    """Did the upgrade change this instance's files or service definition?
    Conversion is the first change; it only ever follows a verified stop."""
    return any(key in outcome for key in ('convert', 'configure', 'start'))


def _rolled_back(outcome):
    """Did an earlier pass already restore this instance and verify its state?"""
    return bool(outcome.get('rollback', {}).get('ok'))


def _files_changed(outcome):
    """Restore files only for an instance the forward run quiesced and converted.
    One whose forward stop failed was never converted and keeps its running files."""
    return 'convert' in outcome and outcome.get('stop') != 'failed'


class _InstanceFailure(Exception):
    def __init__(self, phase, error, pending=False):
        super().__init__(error)
        self.phase = phase
        self.error = safe_error(error)
        self.pending = pending


def _quiesce(execution, iid):
    """Stop a touched instance and prove it is inactive before its files change."""
    deps = execution.deps
    instance = execution.instance(iid)
    state = deps.service_state(instance)
    if state == 'active':
        # Fenced commit right before the (token-less) stop playbook.
        execution.record(iid, rollback={'phase': 'stop', 'ok': False, 'error': None, 'pending': False})
        ok, error = deps.stop(instance)
        state = deps.service_state(instance)
        if not ok and state != 'inactive':
            raise _InstanceFailure('stop', error or f'service is {state}', pending=state == 'unknown')
    if state != 'inactive':
        raise _InstanceFailure('stop', f'service is {state}', pending=state == 'unknown')


def _restore(execution, iid, original, snapshot_root):
    deps = execution.deps
    op = execution.op
    outcome = execution.instance_outcome(iid)

    if _files_changed(outcome):
        execution.fence()
        result = restore_instance(execution.instance(iid), snapshot_root)
        # phase 'cleanup': the restore took effect, only removing its backup failed.
        if not result['ok'] and result['phase'] != 'cleanup':
            raise _InstanceFailure(f'restore:{result["phase"]}', result['error'] or 'restore failed')
        execution.deps.checkpoint(f'rollback_restored:{iid}')
    elif outcome.get('stop') == 'failed':
        # Not quiesced by the forward run: its files were never touched and
        # are not overwritten now. Only its service state is verified below.
        execution.record(iid, forward_stop_failed=outcome.get('error') or 'stop failed')

    if 'configure' in outcome:
        execution.fence()
        remote = deps.configure(iid, MINQLX, None, None, operation_id=op.id,
                                fencing_token=execution.token, restore_from_operation=op.id)
        if not remote.get('ok'):
            raise _InstanceFailure('configure', remote.get('error') or 'remote restore failed',
                                   pending=is_remote_pending(remote.get('error')))
        instance = execution.instance(iid)
        original_deps = outcome.get('original_python_deps_path')
        if instance.python_deps_path != original_deps:
            instance.python_deps_path = original_deps
            execution.commit()

    if not _touched(outcome):
        stop = outcome.get('stop')
        if stop in (None, 'failed', 'verified_inactive'):
            # Never attempted, known not to have succeeded, or originally STOPPED
            # and never touched: leave it as found.
            return _leave_untouched(execution, iid, original, outcome)
        if stop == 'requested':
            # The stop was sent but its outcome was never recorded (crash or
            # exception mid-stop): the actual state decides.
            state = deps.service_state(execution.instance(iid))
            if state == 'unknown':
                raise _InstanceFailure('verify', 'service state cannot be observed', pending=True)
            if state in ('active', 'stray_process'):
                # Still running (the stop never took effect), or a server
                # survived it: do not start anything over it.
                return _leave_untouched(execution, iid, original, outcome)
            # inactive with no process: it was stopped by us -> restart below.

    instance = execution.instance(iid)
    state = deps.service_state(instance)
    if original == InstanceStatus.RUNNING.value:
        if state != 'active':
            execution.fence()  # the start playbook carries no token: re-check first
            ok, error = deps.start(instance)
            if not ok:
                raise _InstanceFailure('start', error or 'start failed', pending=is_remote_pending(error))
        ok, error = deps.wait_ready(instance, deps.ready_timeout)
        if not ok:
            raise _InstanceFailure('verify', error or 'not ready', pending=is_remote_pending(error))
        instance = execution.instance(iid)
        instance.status = InstanceStatus.RUNNING
    else:
        if state != 'inactive':
            raise _InstanceFailure('verify', f'STOPPED instance service is {state}', pending=state == 'unknown')
        instance.status = InstanceStatus.STOPPED
    # Fenced commit: a superseded execution cannot write this status/journal.
    execution.record(iid, rollback={'phase': 'complete', 'ok': True, 'error': None, 'pending': False})


_DESCRIBE = {'active': 'running', 'inactive': 'stopped', 'stray_process': 'stopped in systemd but a '
             'server process is still running', 'unknown': 'not observable'}


def _leave_untouched(execution, iid, original, outcome):
    """An instance the upgrade never stopped (or whose stop never succeeded)
    and never converted or configured: its files and remote state are what
    they were, and whatever its service is doing now is not our doing. It
    counts as restored and never pins the reservation; it is not started (a
    failed stop may have left a server holding the port). Anything unexpected
    is recorded and logged for the operator."""
    instance = execution.instance(iid)
    state = execution.deps.service_state(instance)
    expected = 'active' if original == InstanceStatus.RUNNING.value else 'inactive'
    note = None
    if state != expected:
        stop = outcome.get('stop')
        why = ({'failed': 'its stop failed', 'requested': 'its stop did not take effect'}
               .get(stop, 'it was never stopped')) \
            if original == InstanceStatus.RUNNING.value else 'it was never started by the upgrade'
        note = (f'left as found ({why}, files unchanged): it is {_DESCRIBE.get(state, state)}, '
                f'expected {original.upper()}')
        append_log(execution.host, f'Rollback: instance {instance.name} {note}.')
    execution.record(iid, rollback={'phase': 'complete', 'ok': True, 'error': None, 'pending': False,
                                    'untouched': True, 'note': note})


def _reverify(execution, iid, original, outcome):
    """A retry of an instance an earlier pass already restored: read its state
    only. Drift is recorded and logged (once per distinct note), never acted on:
    the instance is not stopped, reconfigured or restarted again."""
    instance = execution.instance(iid)
    state = execution.deps.service_state(instance)
    expected = 'active' if original == InstanceStatus.RUNNING.value else 'inactive'
    if state == expected:
        return
    previous = outcome['rollback']
    note = (f'restored earlier, but it is now {_DESCRIBE.get(state, state)}, expected '
            f'{original.upper()}; left as found')
    if note != previous.get('note'):
        append_log(execution.host, f'Rollback: instance {instance.name} {note}.')
        execution.record(iid, rollback={**previous, 'note': note})


def _fail_instance(execution, iid, failure):
    db.session.rollback()
    instance = execution.instance(iid)
    if instance is not None and not failure.pending:
        instance.status = InstanceStatus.ERROR
    execution.record(iid, rollback={'phase': failure.phase, 'ok': False,
                                    'error': failure.error, 'pending': failure.pending})


def rollback(execution, reason=None):
    """Roll the whole host back to minqlx. Returns False (the upgrade failed)."""
    execution.fence()
    op = execution.op
    host = execution.host
    stored = execution.outcomes()['host'].get('rollback_reason')
    reason = stored or safe_error(reason or DEFAULT_REASON)
    if not stored:
        execution.record_host(commit=False, rollback_reason=reason)
        append_log(host, f'Upgrade to minqlxtended failed: {reason}. Rolling back to minqlx.')
    execution.set_state('rolling_back', commit=False, recovery_required=True)
    execution.commit()
    if not op.snapshot_complete or not op.snapshot_path:
        # Mutation never starts before publication; refuse to restore anything else.
        execution.set_state('recovery_required', phase='rolling_back: no published snapshot',
                            last_error='No complete snapshot to roll back from')
        return False

    originals = execution.originals()
    failures = {}
    restored = {iid for iid in originals if _rolled_back(execution.instance_outcome(iid))}
    for iid in sorted(originals):
        if iid not in restored and _touched(execution.instance_outcome(iid)):
            try:
                _quiesce(execution, iid)
            except StaleExecution:
                raise
            except _InstanceFailure as failure:
                failures[iid] = failure
                _fail_instance(execution, iid, failure)

    execution.fence()
    host = execution.host
    host.runtime = MINQLX
    host.runtime_deps_isolated = bool(execution.outcomes()['host'].get('original_runtime_deps_isolated', False))
    execution.set_state('rolling_back', phase='runtime_restored')
    execution.deps.checkpoint('rollback_runtime_restored')

    for iid, original in sorted(originals.items()):
        if iid in failures:
            continue  # never overwrite the files of an instance we could not stop
        try:
            if iid in restored:
                _reverify(execution, iid, original, execution.instance_outcome(iid))
                continue
            _restore(execution, iid, original, op.snapshot_path)
        except StaleExecution:
            raise
        except _InstanceFailure as failure:
            failures[iid] = failure
            _fail_instance(execution, iid, failure)
        except Exception as exc:
            if is_job_timeout(exc):
                raise  # not an instance failure: this job must stop; recovery resumes
            log.exception('Upgrade %s: rollback of instance %s failed', op.id, iid)
            failures[iid] = _InstanceFailure('unexpected', exc)
            _fail_instance(execution, iid, failures[iid])
    return _finish(execution, reason, failures)


def _finish(execution, reason, failures):
    execution.fence()
    op = execution.op
    host = execution.host
    host.status = HostStatus.ERROR
    if not failures:
        execution.set_state('rolled_back', commit=False, recovery_required=False, last_error=reason)
        append_log(host, f'Upgrade failed: {reason}. Rolled back to minqlx.')
        execution.commit()
        finalize_remote(execution)
        for iid in execution.originals():
            discard_conversion_leftovers(live_config_dir(host.name, iid), conversion_tag(op.id, iid))
        return False

    names = []
    for iid, failure in sorted(failures.items()):
        instance = execution.instance(iid)
        label = instance.name if instance is not None else str(iid)
        names.append(label)
        state = 'waiting to retry' if failure.pending else 'failed'
        append_log(host, f'Rollback of instance {label} {state} in {failure.phase}: {failure.error}')
    pending = all(failure.pending for failure in failures.values())
    summary = (f'Upgrade failed: {reason}. Rollback to minqlx incomplete for {", ".join(names)}; '
               + ('the host is unreachable or busy, recovery will retry.' if pending
                  else 'recovery will retry; snapshot and presets are kept.'))
    append_log(host, summary)
    execution.set_state('recovery_required', phase='rolling_back: ' + ', '.join(
        f'{iid}:{failure.phase}' for iid, failure in sorted(failures.items())),
        commit=False, recovery_required=True, last_error=safe_error(summary))
    execution.commit()
    return False
