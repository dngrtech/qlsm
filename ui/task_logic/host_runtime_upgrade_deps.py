"""Everything the host runtime upgrade does outside the database and the
local filesystem, behind one object so tests can fault-inject each call.

UpgradeDeps' defaults talk to the real world: the existing stop/start
playbooks, the SSH runtime probe (systemd state + serverchecker status as the
RCON readiness signal), the Task 4 install/configure/finalize entry points,
Redis execution locks, RQ job state and enqueueing. Return conventions:

    stop(instance) / start(instance)    -> (ok, error)
    service_state(instance)             -> 'active' | 'inactive' | 'unknown'
    wait_ready(instance, timeout)       -> (ok, error)
    install / configure / finalize      -> Task 4 result dicts {'ok', 'error', 'details'}
    job_alive(job_id)                   -> bool (unknown counts as alive)
    enqueue_recovery(operation_id, job_id)
    checkpoint(name)                    -> no-op; tests raise here to simulate worker death
"""
import logging
import os
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

READY_TIMEOUT_SECONDS = 60
READY_POLL_SECONDS = 3
# Longer than the 3600 s job timeout: the database reservation, not this
# TTL, is what keeps other operations out; the lock only serializes workers.
EXECUTION_LOCK_TTL = 4200

# Remote/control-plane conditions that mean "not now", not "failed": the
# host's runtime-operation lock is still held by another play (Task 4's
# qlsm_runtime_op.py), or the host cannot be reached.
_PENDING_MARKERS = (
    'another runtime operation play is still running',
    'UNREACHABLE',
    'unreachable',
    'Connection timed out',
    'Connection refused',
    'No route to host',
)


def is_remote_pending(error):
    """True when an error means the host or its lock is not available yet."""
    return bool(error) and any(marker in error for marker in _PENDING_MARKERS)


def execution_lock_token(operation_id, fencing_token):
    return f'rtu:{operation_id}:{int(fencing_token)}'


class RedisExecutionLocks:
    """Host + instance task locks held by one fenced execution.

    Uses the same keys as every other host/instance task (ui.task_lock), so
    ordinary operations are serialized with the upgrade worker. A newer
    execution of the same operation replaces locks left by an older token of
    that operation (the takeover has already been proven safe by then).
    """

    def _keys(self, host_id, instance_ids):
        return [('host', host_id)] + [('instance', iid) for iid in sorted(set(instance_ids))]

    def acquire(self, operation_id, token, host_id, instance_ids):
        from ui.task_lock import _get_redis, acquire_lock, force_release_lock, release_lock

        redis_client = _get_redis()
        prefix = f'rtu:{operation_id}:'
        taken = []
        for kind, entity_id in self._keys(host_id, instance_ids):
            owner = redis_client.get(f'task_lock:{kind}:{entity_id}')
            if isinstance(owner, bytes):
                owner = owner.decode()
            if owner and owner.startswith(prefix) and owner != token:
                force_release_lock(kind, entity_id)
            if owner != token and not acquire_lock(kind, entity_id, token, EXECUTION_LOCK_TTL):
                for done_kind, done_id in taken:
                    release_lock(done_kind, done_id, token)
                return False
            taken.append((kind, entity_id))
        return True

    def renew(self, operation_id, token, host_id, instance_ids):
        from ui.task_lock import _get_redis, acquire_lock

        redis_client = _get_redis()
        ok = True
        for kind, entity_id in self._keys(host_id, instance_ids):
            key = f'task_lock:{kind}:{entity_id}'
            owner = redis_client.get(key)
            if isinstance(owner, bytes):
                owner = owner.decode()
            if owner == token:
                redis_client.expire(key, EXECUTION_LOCK_TTL)
            elif owner is None:
                ok = acquire_lock(kind, entity_id, token, EXECUTION_LOCK_TTL) and ok
            else:
                ok = False
        return ok

    def release(self, operation_id, token, host_id, instance_ids):
        from ui.task_lock import release_lock

        for kind, entity_id in self._keys(host_id, instance_ids):
            try:
                release_lock(kind, entity_id, token)
            except Exception:
                log.exception('Could not release %s %s lock of upgrade %s', kind, entity_id, operation_id)


class UpgradeDeps:
    """Default (production) implementations. Subclass or replace attributes in tests."""

    ready_timeout = READY_TIMEOUT_SECONDS

    def __init__(self):
        self.locks = RedisExecutionLocks()

    # --- services ---------------------------------------------------------------
    def stop(self, instance):
        from ui.task_logic.ansible_instance_mgmt import STOP_SUCCESS_MARKER, stop_instance_logic

        result = stop_instance_logic(instance.id)
        ok = isinstance(result, str) and STOP_SUCCESS_MARKER in result
        return ok, None if ok else str(result)

    def start(self, instance):
        from ui.task_logic.ansible_instance_mgmt import start_instance_logic

        result = start_instance_logic(instance.id)
        ok = isinstance(result, str) and 'start successful' in result
        return ok, None if ok else str(result)

    def service_state(self, instance):
        from ui.task_logic.interrupted_job_recovery import probe_service_state

        return probe_service_state(instance)

    def wait_ready(self, instance, timeout=READY_TIMEOUT_SECONDS):
        """systemd active and a serverchecker status published after the
        service started (the existing readiness signal the status poller and
        interrupted-job recovery use), within `timeout` seconds."""
        from ui.task_logic.service_runtime import observation_has_fresh_status, probe_host_runtime

        host = instance.host
        password = os.environ.get('REDIS_PASSWORD') if getattr(host, 'provider', None) == 'self' else None
        deadline = time.monotonic() + timeout
        last = 'no observation'
        while True:
            observations = probe_host_runtime(host, [instance], redis_password=password)
            observation = (observations or {}).get(str(instance.port))
            if observation is not None and observation_has_fresh_status(observation):
                return True, None
            if observations is None:
                last = 'host unreachable'
            elif observation is None or not observation.active:
                last = 'service is not active'
            else:
                last = 'server has not reported status since it started'
            if time.monotonic() >= deadline:
                return False, f'not ready within {timeout}s: {last}'
            time.sleep(READY_POLL_SECONDS)

    # --- Task 4 remote entry points ---------------------------------------------
    def install(self, host_id, **kwargs):
        from ui.task_logic.instance_runtime_update import install_runtime_on_host

        return install_runtime_on_host(host_id, **kwargs)

    def configure(self, instance_id, runtime, immutable_inputs, dependency_path, **kwargs):
        from ui.task_logic.instance_runtime_update import configure_existing_instance

        return configure_existing_instance(instance_id, runtime, immutable_inputs, dependency_path, **kwargs)

    def finalize(self, host_id, **kwargs):
        from ui.task_logic.instance_runtime_update import finalize_runtime_operation

        return finalize_runtime_operation(host_id, **kwargs)

    # --- RQ ----------------------------------------------------------------------
    def job_alive(self, job_id, now=None):
        if not job_id:
            return False
        from rq.exceptions import NoSuchJobError
        from rq.job import Job, JobStatus

        from ui import rq
        from ui.task_logic.interrupted_job_recovery import STALE_HEARTBEAT_SECONDS

        try:
            job = Job.fetch(job_id, connection=rq.get_queue().connection)
            status = job.get_status(refresh=False)
        except NoSuchJobError:
            return False
        except Exception:
            log.exception('Could not read RQ job %s; treating it as alive', job_id)
            return True
        if status in (JobStatus.QUEUED, JobStatus.DEFERRED, JobStatus.SCHEDULED):
            return True
        if status != JobStatus.STARTED:
            return False
        last_seen = job.last_heartbeat or job.started_at
        if last_seen is None:
            return True
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        return (now - last_seen).total_seconds() <= STALE_HEARTBEAT_SECONDS

    def enqueue_recovery(self, operation_id, job_id):
        from ui.task_logic.job_failure_handlers import runtime_upgrade_job_failure_handler
        from ui.tasks import enqueue_task, recover_host_runtime

        return enqueue_task(recover_host_runtime, operation_id, job_id=job_id,
                            on_failure=runtime_upgrade_job_failure_handler)

    # --- test seam -----------------------------------------------------------------
    def checkpoint(self, name):
        """Called after each durable step; production does nothing."""
