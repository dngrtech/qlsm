"""Durable, fenced Custom release changes. Only a systemd unit changes per instance."""
import json

from ui import db
from ui.custom_runtime import pinned_release, release_for_host
from ui.custom_runtime_update import capture_inputs, fingerprint, ssh_endpoint
from ui.models import HostStatus, InstanceStatus
from ui.task_logic.common import append_log
from .host_runtime_upgrade import is_job_timeout
from .host_runtime_upgrade_state import StaleExecution


class ReleaseStepFailed(Exception):
    """Public error: carries only a step and an optional numeric instance ID."""


def _step(ex, action, instance=None, **kwargs):
    ex.fence()
    inputs = ex.inputs()
    endpoint = {key: inputs[key] for key in ('address', 'ssh_port', 'ssh_user', 'ssh_key_path')}
    result = ex.deps.custom_step(ex.host, action, operation_id=ex.operation_id, fencing_token=ex.token,
                                 endpoint=endpoint, instance=instance, **kwargs)
    if not result:
        suffix = f' for instance {instance.id}' if instance else ''
        raise ReleaseStepFailed(f'Custom release step {action} failed{suffix}.')
    return result


def _require_state(ex, inst, expected):
    if ex.deps.service_state(inst) != expected:
        raise ReleaseStepFailed(f'Could not verify instance {inst.id} is {expected}.')


def _ready(ex, inst):
    ok, _ = ex.deps.wait_ready(inst, ex.deps.ready_timeout)
    if not ok:
        raise ReleaseStepFailed(f'Instance {inst.id} did not report fresh status.')


def _validate(ex):
    host, inputs = ex.host, ex.inputs()
    if (host.status != HostStatus.CONFIGURING or host.provider != 'standalone' or host.runtime != 'custom'
            or fingerprint(inputs) != ex.op.fingerprint):
        raise ReleaseStepFailed('The confirmed host or capture changed.')
    current = release_for_host(host)
    selected = json.loads(ex.op.answers_json)
    choices = {action: (pinned_release(current.provider_id, summary['sha256']) if summary else None)
               for action, summary in inputs['choices'].items()}
    target = choices[selected['action']]
    if (target is None or target.sha256 != selected['target_sha256']
            or target.metadata['plugin_api'] != current.metadata['plugin_api']
            or target.metadata['platform'] != current.metadata['platform']
            or capture_inputs(host, current, choices) != inputs):
        raise ReleaseStepFailed('The release or instance settings changed since confirmation.')
    for iid, state in ex.originals().items():
        if state == 'stopped':
            observed = ex.deps.service_state(ex.instance(iid))
            if observed == 'unknown':
                ex.record_host(unobserved_instance=iid)
            if observed != 'inactive':
                raise ReleaseStepFailed(f'Could not verify stopped instance {iid} is inactive.')
    return inputs, current, target


def _prepare(ex):
    inputs, current, target = _validate(ex)
    ex.record_host(stage_requested=True, commit=False)
    ex.set_state('preparing', phase='staging')
    _step(ex, 'stage', release=target, original=current)
    for row in inputs['instances']:
        inst = ex.instance(row['instance_id'])
        ex.record(inst.id, inventory='requested')
        _step(ex, 'inventory', inst, unit=row['units'][target.sha256])
        ex.record(inst.id, inventory='verified')
    ex.record_host(staged=True)
    # Stage may spend minutes installing dependencies. Recheck the current
    # pin, retained bytes, render inputs and stopped services before downtime.
    _validate(ex)
    return inputs, target


def _apply(ex, inputs, target):
    ex.record_host(quiesce_requested=True, commit=False)
    ex.set_state('quiescing')
    for row in inputs['instances']:
        iid = row['instance_id']
        inst = ex.instance(iid)
        if row['status'] == 'running':
            ex.record(iid, stop='requested')
            _step(ex, 'stop', inst)
        _require_state(ex, inst, 'inactive')
        inst.status = InstanceStatus.STOPPED
        ex.record(iid, stop='verified')

    # A service stopped early can reactivate while a later instance stops.
    for iid in ex.originals():
        _require_state(ex, ex.instance(iid), 'inactive')
    ex.host.runtime_release_sha256 = target.sha256
    ex.set_state('configuring', phase='runtime_committed')
    for row in inputs['instances']:
        iid = row['instance_id']
        ex.record(iid, configure='requested')
        _step(ex, 'apply', ex.instance(iid), unit=row['units'][target.sha256])
        ex.record(iid, configure='verified')

    ex.set_state('configuring', phase='starting')
    for iid, status in sorted(ex.originals().items()):
        inst = ex.instance(iid)
        if status == 'running':
            ex.record(iid, start='requested')
            _step(ex, 'start', inst)
            _ready(ex, inst)
        else:
            _require_state(ex, inst, 'inactive')
        inst.status = InstanceStatus(status)
        ex.record(iid, start='verified')


def _pending(ex, reason):
    db.session.rollback()
    ex.host.status = HostStatus.ERROR
    ex.set_state('recovery_required', recovery_required=True, last_error=reason)
    return f'pending: {reason}'


def _expected_pin(ex, decision):
    if decision == 'succeeded':
        return json.loads(ex.op.answers_json)['target_sha256']
    return ex.inputs()['current']['sha256']


def _verify_services(ex, decision):
    if decision == 'failed_preparation':
        iid = ex.outcomes()['host'].get('unobserved_instance')
        if iid:
            _require_state(ex, ex.instance(iid), 'inactive')
        return
    for iid, status in ex.originals().items():
        inst = ex.instance(iid)
        if status == 'running':
            _require_state(ex, inst, 'active')
            _ready(ex, inst)
        else:
            _require_state(ex, inst, 'inactive')


def _expected_target(ex, decision):
    return _same_target(ex) and ex.host.runtime_release_sha256 == _expected_pin(ex, decision)


def _finish(ex, decision, *, finalize=True):
    # Persist intent first. Only the remote response (or a later receipt
    # query) proves that the operation actually closed on the target.
    ex.record_host(decision=decision, finalize=finalize)
    if finalize and not ex.outcomes()['host'].get('remote_finalized'):
        if not _expected_target(ex, decision):
            return _pending(ex, 'The host or release pin differs from the expected final state.')
        try:
            # Confirm the entire set while a forward failure can still roll
            # back. Early starters may have died as later services came up.
            _verify_services(ex, decision)
        except ReleaseStepFailed as exc:
            if decision in ('succeeded', 'rolled_back'):
                ex.record_host(decision=None, failure=str(exc))
                if decision == 'succeeded':
                    return _rollback(ex)
                # Retry an incomplete rollback through the reconciler.
            return _pending(ex, str(exc))
        try:
            _step(ex, 'finalize', allow_unrecorded=decision == 'failed_preparation')
            ex.record_host(remote_finalized=True)
        except ReleaseStepFailed as exc:
            return _pending(ex, str(exc))
    host = ex.host
    if not _expected_target(ex, decision):
        return _pending(ex, 'The host or release pin differs from the expected final state.')
    try:
        _verify_services(ex, decision)
    except ReleaseStepFailed as exc:
        return _pending(ex, str(exc))
    host.status = HostStatus.ACTIVE
    reason = ex.outcomes()['host'].get('failure')
    ex.set_state(decision, phase='complete', recovery_required=False,
                 last_error=reason if decision != 'succeeded' else None, commit=False)
    messages = {'succeeded': f'Custom runtime now uses release {host.runtime_release_sha256[:12]}.',
                'rolled_back': f'Custom release change failed. Restored the original release and services. {reason}',
                'failed_preparation': f'Custom release change cancelled before downtime. {reason}'}
    append_log(host, messages[decision])
    ex.commit()
    return decision == 'succeeded'


def _restore_instance(ex, iid, original):
    inst = ex.instance(iid)
    journal = ex.instance_outcome(iid)
    state = ex.deps.service_state(inst)
    if state not in ('active', 'inactive'):
        raise ReleaseStepFailed(f'Could not verify service state for instance {iid}.')
    if journal.get('configure') and journal.get('restored_unit') != 'verified':
        if state == 'active':
            ex.record(iid, undo_start='requested')
            _step(ex, 'stop', inst)
        _require_state(ex, inst, 'inactive')
        ex.record(iid, restored_unit='requested')
        _step(ex, 'restore', inst)
        ex.record(iid, restored_unit='verified')
        state = 'inactive'
    if original == 'running':
        if state == 'inactive':
            ex.record(iid, restore_start='requested')
            _step(ex, 'start', inst)
        _ready(ex, inst)
    else:
        if state == 'active':
            ex.record(iid, restore_stop='requested')
            _step(ex, 'stop', inst)
        _require_state(ex, inst, 'inactive')
    inst.status = InstanceStatus(original)
    ex.record(iid, restored_status='verified')


def _same_target(ex):
    inputs, host = ex.inputs(), ex.host
    if (not host or host.id != inputs['host_id'] or fingerprint(inputs) != ex.op.fingerprint
            or (host.created_at.isoformat() if host.created_at else None) != inputs['host_created_at']
            or host.provider != 'standalone' or host.runtime != 'custom'
            or host.runtime_provider_id != inputs['current']['provider_id']
            or host.runtime_plugin_api != inputs['current']['plugin_api']
            or host.name != inputs['host_name']
            or any(inputs.get(key) != value for key, value in ssh_endpoint(host).items())):
        return False
    captured = {(i['instance_id'], i['port'], i['created_at']) for i in inputs['instances']}
    return captured == {(i.id, i.port, i.created_at.isoformat() if i.created_at else None) for i in host.instances}


def _rollback(ex):
    inputs, host = ex.inputs(), ex.host
    host.runtime_release_sha256 = inputs['current']['sha256']
    ex.set_state('rolling_back', recovery_required=True)
    try:
        # Establish the new remote fence before trusting any probe. A delayed
        # lower-token play can no longer change a service observed by recovery.
        _step(ex, 'barrier')
        for iid, original in sorted(ex.originals().items()):
            _restore_instance(ex, iid, original)
    except ReleaseStepFailed as exc:
        return _pending(ex, str(exc))
    return _finish(ex, 'rolled_back')


def _resume_finish(ex, journal):
    decision, finalize = journal['decision'], journal['finalize']
    if ex.host.runtime_release_sha256 != _expected_pin(ex, decision):
        return _pending(ex, 'The host release pin differs from the expected final state.')
    if not finalize or journal.get('remote_finalized'):
        return _finish(ex, decision, finalize=finalize)
    try:
        receipt = _step(ex, 'receipt')
        if receipt == 'closed':
            ex.record_host(remote_finalized=True)
        elif receipt == 'open':
            # Fence any delayed finalize from the prior worker before the
            # pre-close check can choose rollback.
            _step(ex, 'barrier')
        elif receipt != 'unrecorded' or decision != 'failed_preparation':
            raise ReleaseStepFailed('Could not verify the remote finalization receipt.')
    except ReleaseStepFailed as exc:
        return _pending(ex, str(exc))
    return _finish(ex, decision, finalize=finalize)


def recover(ex):
    if not _same_target(ex):
        return _pending(ex, 'The host or its instances no longer match the confirmed operation.')
    journal = ex.outcomes()['host']
    if journal.get('decision'):
        return _resume_finish(ex, journal)
    if not ex.outcomes()['host'].get('failure'):
        ex.record_host(failure='The Custom release worker was interrupted.')
    if not ex.outcomes()['host'].get('quiesce_requested'):
        iid = ex.outcomes()['host'].get('unobserved_instance')
        if iid and ex.deps.service_state(ex.instance(iid)) != 'inactive':
            return _pending(ex, f'Could not observe stopped instance {iid}.')
        return _finish(ex, 'failed_preparation', finalize=bool(ex.outcomes()['host'].get('stage_requested')))
    return _rollback(ex)


def run(ex):
    try:
        if not ex.locked:
            raise ReleaseStepFailed('Another operation holds the host or instance locks.')
        inputs, target = _prepare(ex)
        _apply(ex, inputs, target)
    except StaleExecution:
        raise
    except Exception as exc:
        if is_job_timeout(exc):
            raise
        db.session.rollback()
        reason = str(exc) if isinstance(exc, ReleaseStepFailed) else 'Could not complete the Custom release step.'
        ex.record_host(failure=reason)
        return recover(ex)
    return _finish(ex, 'succeeded')
