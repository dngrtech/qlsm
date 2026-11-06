"""Background upgrade of one host from minqlx to minqlxtended.

upgrade_host_runtime_logic(operation_id) runs the operation Task 6 created
(state `preparing`, host CONFIGURING, inputs/fingerprint/answers persisted):

  1. take fenced ownership and execution locks; re-validate eligibility as if
     ACTIVE, recapture the inputs and compare the fingerprint, validate the
     answers. A stale approval ends `failed_preparation`, host ACTIVE, no downtime.
  2. publish the complete snapshot + fallback presets (Task 3); recheck the
     live inputs right before mutation. Failures here are preparation-only.
  3. `quiescing`: stop originally RUNNING instances, verify every instance is
     inactive. 4. `installing`: Task 4 installer. 5. `converting`: converted
     trees from immutable inputs, swapped into configs/ with journaled intent.
  6. commit the target runtime (`configuring`), configure every instance
     without starting it, then start only originally RUNNING instances and
     verify readiness within 60 s; originally STOPPED ones must stay inactive.
  7. success: host ACTIVE, operation `succeeded`, remote record finalized.

Any failure after mutation began runs the idempotent whole-host rollback in
host_runtime_upgrade_rollback. Worker death is recovered by
host_runtime_upgrade_recovery. Never logs or returns the captured inputs
(they hold ZMQ passwords).
"""
import json
import logging
import os

from ui import db
from ui.models import HostStatus, InstanceStatus
from ui.runtime_upgrade import (
    UPGRADE_TARGET_RUNTIME,
    UpgradeInputsChanged,
    capture_upgrade_inputs,
    classification_fingerprint,
    upgrade_eligibility,
)
from ui.runtime_upgrade_conversion import (
    build_converted_tree,
    build_target_system_hooks,
    discard_conversion_leftovers,
    excluded_hooks,
    install_converted_tree,
    parse_answers,
)
from ui.runtime_upgrade_snapshot import (
    STAGING_SUFFIX,
    _cleanup_preparation,
    prepare_upgrade_snapshot,
    snapshot_dir,
)
from ui.task_logic.common import append_log
from ui.task_logic.instance_runtime_update import dependency_path, install_inputs_from_materialized

from .host_runtime_upgrade_deps import UpgradeDeps
from .host_runtime_upgrade_state import Execution, StaleExecution, claim_operation, safe_error

log = logging.getLogger(__name__)


class PreparationFailed(Exception):
    """Nothing live has changed; the operation ends failed_preparation."""


# --- shared helpers (also used by rollback/recovery) -----------------------------------

def live_config_dir(host_name, instance_id):
    from ui import runtime_upgrade

    return runtime_upgrade._instance_config_dir(host_name, instance_id)


def conversion_tag(operation_id, instance_id):
    return f'{int(instance_id)}-{operation_id}'


def inputs_dir(op):
    return os.path.join(op.snapshot_path, 'inputs')


def take_ownership(operation_id, job_id, deps):
    """Claim the operation (None if another execution won) and try to take its
    execution locks; check `execution.locked` before any side effect."""
    token = claim_operation(operation_id, job_id)
    if token is None:
        return None
    execution = Execution(operation_id, token, job_id, deps)
    if not execution.acquire_locks():
        log.warning('Upgrade %s: host/instance execution locks are held elsewhere', operation_id)
    return execution


def finalize_remote(execution):
    """Best effort, after the terminal state is committed: a failure leaves a
    record the next operation may take over (it is listed as terminal)."""
    op = execution.op
    try:
        result = execution.deps.finalize(op.host_id, operation_id=op.id, fencing_token=execution.token)
        if not result.get('ok'):
            log.warning('Upgrade %s: finalize on host failed: %s', op.id, result.get('error'))
    except Exception:
        log.exception('Upgrade %s: finalize on host raised', op.id)


def fail_preparation(execution, reason, *, cleanup_snapshot):
    """End a preparation-only operation: nothing was stopped or changed."""
    op = execution.op
    host = execution.host
    if cleanup_snapshot:
        published = snapshot_dir(op.host_id, op.id)
        _cleanup_preparation(op.id, published + STAGING_SUFFIX, published)
    execution.set_state('failed_preparation', phase='failed_preparation', commit=False,
                        last_error=safe_error(reason), recovery_required=False,
                        snapshot_complete=False if cleanup_snapshot else op.snapshot_complete)
    if host is not None:
        if host.status == HostStatus.CONFIGURING:
            host.status = HostStatus.ACTIVE
        append_log(host, f'Upgrade to minqlxtended cancelled before any change: {safe_error(reason)}')
    execution.commit()
    return False


# --- forward -------------------------------------------------------------------------

def _validate(execution):
    """Step 1: everything the operator confirmed is still true. Returns the inputs."""
    op = execution.op
    host = execution.host
    if host is None:
        raise PreparationFailed(f'Host {op.host_id} no longer exists')
    inputs = execution.inputs()
    if not op.fingerprint or classification_fingerprint(inputs) != op.fingerprint:
        raise PreparationFailed('The stored upgrade inputs do not match their confirmation fingerprint')
    eligibility = upgrade_eligibility(host, assume_status=HostStatus.ACTIVE)
    if not eligibility['enabled']:
        raise PreparationFailed(eligibility['reason'] or 'Host is no longer eligible for the upgrade')
    # The capture covers every instance of the host (ids, configs, scripts,
    # selections, hooks, renderer fields) and the target inputs, so an equal
    # fingerprint also proves the instance set is the confirmed one.
    if classification_fingerprint(capture_upgrade_inputs(host)) != op.fingerprint:
        raise PreparationFailed('The host changed after the upgrade was confirmed; review it again')
    try:
        parse_answers(inputs, op.answers_json)
    except UpgradeInputsChanged as exc:
        raise PreparationFailed(str(exc)) from exc

    captured = {int(item['instance_id']): item for item in inputs.get('instances') or []}
    op.original_runtime = host.runtime
    op.original_instance_states_json = json.dumps(
        {str(iid): item['original_status'] for iid, item in sorted(captured.items())})
    outcomes = execution.outcomes()
    outcomes['host']['original_runtime_deps_isolated'] = bool(host.runtime_deps_isolated)
    for iid in captured:
        instance = execution.instance(iid)
        outcomes['instances'].setdefault(str(iid), {}).update(
            original_status=captured[iid]['original_status'],
            original_python_deps_path=instance.python_deps_path)
    execution._write_outcomes(outcomes)
    execution.commit()
    return inputs


_STATE_TEXT = {'active': 'its service is running', 'unknown': 'its state cannot be observed',
               'stray_process': 'its service is stopped but a server process is still running'}


def _preflight_stopped(execution):
    """Every originally STOPPED instance must already be quiesced (systemd
    inactive and no server process), checked before anything is stopped:
    otherwise the upgrade is cancelled with no change at all."""
    for iid, original in sorted(execution.originals().items()):
        if original != InstanceStatus.STOPPED.value:
            continue
        instance = execution.instance(iid)
        state = execution.deps.service_state(instance)
        if state != 'inactive':
            raise PreparationFailed(
                f'instance {instance.name} is STOPPED but {_STATE_TEXT.get(state, f"its service is {state}")}; '
                'stop it fully and try again')


def _prepare(execution, inputs):
    """Step 2: STOPPED preflight, complete published snapshot, then the last
    pre-mutation check."""
    op = execution.op
    host = execution.host
    _preflight_stopped(execution)
    try:
        prepare_upgrade_snapshot(host, op.id, inputs)
    except Exception as exc:
        raise PreparationFailed(f'Could not snapshot the instances: {safe_error(exc)}') from exc
    execution.deps.checkpoint('snapshot_published')
    execution.fence()
    if classification_fingerprint(capture_upgrade_inputs(host)) != op.fingerprint:
        raise PreparationFailed('The host changed while it was being snapshotted; review it again')


class StepFailed(Exception):
    """A forward step failed after mutation began: roll back with this reason."""


def _quiesce(execution):
    execution.fence()
    execution.set_state('quiescing')
    deps = execution.deps
    for iid, original in sorted(execution.originals().items()):
        instance = execution.instance(iid)
        if original == InstanceStatus.RUNNING.value:
            execution.fence()
            execution.record(iid, stop='requested')
            ok, error = deps.stop(instance)
            state = deps.service_state(instance)
            if not ok or state != 'inactive':
                detail = error or f'service is {state}'
                execution.record(iid, stop='failed', error=safe_error(detail))
                raise StepFailed(f'could not stop instance {instance.name}: {safe_error(detail)}')
            instance.status = InstanceStatus.STOPPED
            execution.record(iid, stop='ok')
        else:
            state = deps.service_state(instance)
            if state != 'inactive':
                execution.record(iid, stop='failed', error=f'service is {state}')
                raise StepFailed(f'instance {instance.name} was STOPPED but its service is {state}')
            # Not stopped by us: 'ok' is reserved for instances the upgrade stopped.
            execution.record(iid, stop='verified_inactive')


def _install(execution, ids):
    execution.fence()
    execution.set_state('installing')
    op = execution.op
    result = execution.deps.install(
        op.host_id, operation_id=op.id, fencing_token=execution.token,
        immutable_inputs=install_inputs_from_materialized(inputs_dir(op), ids))
    if not result.get('ok'):
        raise StepFailed(f'minqlxtended install failed: {safe_error(result.get("error"))}')
    execution.deps.checkpoint('installed')


def _converted_dir(op, instance_id):
    return os.path.join(op.snapshot_path, 'converted', str(int(instance_id)))


def _system_hooks_dir(op):
    return os.path.join(op.snapshot_path, 'converted', '_system_hooks')


def _convert(execution, inputs):
    execution.fence()
    execution.set_state('converting')
    op = execution.op
    host = execution.host
    answers = parse_answers(inputs, op.answers_json)
    excluded = excluded_hooks(inputs)
    build_target_system_hooks(inputs_dir(op), excluded, _system_hooks_dir(op))
    for captured in sorted(inputs.get('instances') or [], key=lambda item: item['instance_id']):
        iid = int(captured['instance_id'])
        dest = _converted_dir(op, iid)
        fields = build_converted_tree(inputs_dir(op), captured, answers[iid], excluded, dest)
        execution.fence()
        execution.record(iid, convert='swapping')
        install_converted_tree(live_config_dir(host.name, iid), dest, conversion_tag(op.id, iid))
        instance = execution.instance(iid)
        instance.qlx_plugins = fields['qlx_plugins']
        instance.ld_preload_hooks = fields['ld_preload_hooks']
        execution.record(iid, convert='swapped')
        execution.deps.checkpoint(f'converted:{iid}')


def _commit_runtime(execution):
    execution.fence()
    host = execution.host
    host.runtime = UPGRADE_TARGET_RUNTIME
    host.runtime_deps_isolated = True
    execution.set_state('configuring', phase='runtime_committed')
    execution.deps.checkpoint('runtime_committed')


def _configure(execution, ids):
    op = execution.op
    for iid in ids:
        execution.fence()
        instance = execution.instance(iid)
        instance.status = InstanceStatus.CONFIGURING
        execution.record(iid, configure='requested')
        result = execution.deps.configure(
            iid, UPGRADE_TARGET_RUNTIME,
            {'config_dir': _converted_dir(op, iid), 'system_hooks_dir': _system_hooks_dir(op)},
            dependency_path(op.id, iid), operation_id=op.id, fencing_token=execution.token,
            commit=execution.commit)
        if not result.get('ok'):
            execution.record(iid, configure='failed', error=safe_error(result.get('error')))
            raise StepFailed(f'configuring instance {instance.name} failed: {safe_error(result.get("error"))}')
        execution.record(iid, configure='ok')
        execution.deps.checkpoint(f'configured:{iid}')


def _start_and_verify(execution):
    execution.fence()
    execution.set_state('configuring', phase='starting')
    deps = execution.deps
    for iid, original in sorted(execution.originals().items()):
        instance = execution.instance(iid)
        execution.fence()
        if original == InstanceStatus.RUNNING.value:
            execution.record(iid, start='requested')
            ok, error = deps.start(instance)
            if ok:
                ok, error = deps.wait_ready(instance, deps.ready_timeout)
            if not ok:
                execution.record(iid, start='failed', error=safe_error(error))
                raise StepFailed(f'instance {instance.name} did not come up on minqlxtended: {safe_error(error)}')
            instance.status = InstanceStatus.RUNNING
            execution.record(iid, start='ok')
        else:
            state = deps.service_state(instance)
            if state != 'inactive':
                execution.record(iid, start='failed', error=f'service is {state}')
                raise StepFailed(f'STOPPED instance {instance.name} is {state} after configuration')
            instance.status = InstanceStatus.STOPPED
            execution.record(iid, start='not_started')


def _succeed(execution, ids):
    execution.fence()
    op = execution.op
    host = execution.host
    presets = []
    try:
        with open(os.path.join(op.snapshot_path, 'manifest.json'), encoding='utf-8') as handle:
            presets = json.load(handle).get('presets') or []
    except (OSError, ValueError):
        pass
    execution.set_state('succeeded', phase='complete', commit=False,
                        recovery_required=False, last_error=None)
    host.status = HostStatus.ACTIVE
    append_log(host, 'Upgraded to minqlxtended; every instance is back in its original state.'
               + (f' Fallback presets: {", ".join(presets)}.' if presets else ''))
    execution.commit()
    finalize_remote(execution)
    for iid in ids:
        discard_conversion_leftovers(live_config_dir(host.name, iid), conversion_tag(op.id, iid))
    return True


def _run(execution):
    from .host_runtime_upgrade_rollback import rollback

    try:
        inputs = _validate(execution)
        _prepare(execution, inputs)
    except PreparationFailed as exc:
        published = execution.op.snapshot_complete
        return fail_preparation(execution, str(exc), cleanup_snapshot=published)
    except StaleExecution:
        raise
    except Exception as exc:
        if is_job_timeout(exc):
            raise
        log.exception('Upgrade %s failed during preparation', execution.operation_id)
        return fail_preparation(execution, f'unexpected error: {safe_error(exc)}',
                                cleanup_snapshot=execution.op.snapshot_complete)

    ids = sorted(execution.originals())
    try:
        _quiesce(execution)
        _install(execution, ids)
        _convert(execution, inputs)
        _commit_runtime(execution)
        _configure(execution, ids)
        _start_and_verify(execution)
    except StaleExecution:
        raise
    except StepFailed as exc:
        db.session.rollback()
        return rollback(execution, str(exc))
    except Exception as exc:
        if is_job_timeout(exc):
            raise
        log.exception('Upgrade %s failed unexpectedly', execution.operation_id)
        db.session.rollback()
        return rollback(execution, f'unexpected error: {safe_error(exc)}')
    return _succeed(execution, ids)


def is_job_timeout(exc):
    try:
        from rq.timeouts import JobTimeoutException
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, JobTimeoutException)


def mark_recovery_required(execution, reason, *, state=None):
    """Durably (and fenced) record that a rollback is owed and leave it to the
    reconciler/recovery job. Never raises."""
    try:
        db.session.rollback()
        op = execution.op
        if op is not None and not op.is_terminal:
            op.recovery_required = True
            op.last_error = safe_error(reason)
            if state:
                op.state = state
            execution.commit()
    except StaleExecution:
        log.warning('Upgrade %s: superseded while recording recovery_required', execution.operation_id)
    except Exception:
        log.exception('Upgrade %s: could not record recovery_required', execution.operation_id)
        db.session.rollback()


def upgrade_host_runtime_logic(operation_id, *, deps=None, job_id=None):
    """Entry point for the RQ task. Returns True on success, False on a
    cancelled/rolled-back upgrade, or an error string. Never raises: an RQ job
    timeout (or any other escape) records recovery_required and returns; the
    reconciler then sees the finished job and hands the operation to recovery."""
    from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation

    from .host_runtime_upgrade_recovery import recover_host_runtime_logic

    deps = deps or UpgradeDeps()
    op = db.session.get(HostRuntimeUpgradeOperation, operation_id)
    if op is None:
        return f'Error: runtime upgrade operation {operation_id} not found'
    if op.is_terminal:
        return op.state == 'succeeded'
    if op.state != 'preparing' or op.recovery_required:
        # Redelivered or late: anything past preparation belongs to recovery.
        return recover_host_runtime_logic(operation_id, deps=deps, job_id=job_id)

    execution = take_ownership(operation_id, job_id, deps)
    if execution is None:
        return f'Error: could not take ownership of runtime upgrade {operation_id}'
    try:
        if not execution.locked:
            return fail_preparation(execution, 'another operation is running on this host or one of '
                                    'its instances; try again when it finishes', cleanup_snapshot=False)
        return _run(execution)
    except StaleExecution as exc:
        log.warning('Upgrade %s: stopping, %s', operation_id, exc)
        db.session.rollback()
        return False
    except Exception as exc:
        if is_job_timeout(exc):
            # Stop all work in this job; recovery resumes the rollback.
            mark_recovery_required(execution, f'worker timed out: {exc}')
            return f'Error: runtime upgrade {operation_id} timed out; recovery pending'
        log.exception('Upgrade %s: unexpected error outside the step handlers', operation_id)
        mark_recovery_required(execution, f'unexpected error: {safe_error(exc)}')
        return f'Error: runtime upgrade {operation_id} needs recovery: {safe_error(exc)}'
    finally:
        execution.release_locks()
