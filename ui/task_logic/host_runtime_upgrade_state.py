"""Durable state and fenced ownership of one host runtime upgrade operation.

The HostRuntimeUpgradeOperation row is the source of truth. Every execution
(the first worker, or a recovery worker) takes ownership by compare-and-set
incrementing `fencing_token`; before each side effect it re-reads the token
and stops (StaleExecution) if a newer execution has taken over or the
operation went terminal. Intent is committed before each side effect and the
outcome after it is verified.

instance_outcomes_json layout:

    {"host": {"original_runtime_deps_isolated": false, "rollback_reason": "..."},
     "instances": {"<id>": {"original_status": "running",
                            "original_python_deps_path": null,
                            "stop": "requested|ok|failed", "convert": "swapping|swapped",
                            "configure": "requested|ok|failed", "start": "requested|ok|failed",
                            "rollback": {"phase": "...", "ok": bool, "error": "...", "pending": bool},
                            "error": "..."}}}
"""
import datetime
import json
import logging

from sqlalchemy import select, update

from ui import db
from ui.models import Host, QLInstance
from ui.models_runtime_upgrade import TERMINAL_STATES, HostRuntimeUpgradeOperation
from ui.runtime_upgrade_snapshot import _safe_error

from .host_runtime_upgrade_deps import execution_lock_token

log = logging.getLogger(__name__)

MAX_ERROR_CHARS = 600


class StaleExecution(Exception):
    """A newer execution owns the operation (or it is terminal): stop now."""


def safe_error(exc_or_text):
    text = exc_or_text if isinstance(exc_or_text, str) else _safe_error(exc_or_text)
    text = ' '.join((text or 'unknown error').split())
    return text if len(text) <= MAX_ERROR_CHARS else text[:MAX_ERROR_CHARS - 3] + '...'


def _now():
    return datetime.datetime.utcnow()


def claim_operation(operation_id, job_id):
    """Take ownership: CAS fencing_token -> token+1 and record `job_id`.

    Returns the new token, or None when another execution won the race or the
    operation is missing/terminal.
    """
    op = db.session.get(HostRuntimeUpgradeOperation, operation_id)
    if op is None or op.is_terminal:
        return None
    old = op.fencing_token or 0
    result = db.session.execute(
        update(HostRuntimeUpgradeOperation)
        .where(HostRuntimeUpgradeOperation.id == operation_id,
               HostRuntimeUpgradeOperation.fencing_token == old)
        .values(fencing_token=old + 1, rq_job_id=job_id, updated_at=_now()))
    db.session.commit()
    if result.rowcount != 1:
        return None
    db.session.expire(op)
    return old + 1


class Execution:
    """One fenced execution of an operation."""

    def __init__(self, operation_id, token, job_id, deps):
        self.operation_id = operation_id
        self.token = token
        self.job_id = job_id
        self.deps = deps
        self.lock_token = execution_lock_token(operation_id, token)
        self.locked = False

    # --- rows ------------------------------------------------------------------------
    @property
    def op(self):
        return db.session.get(HostRuntimeUpgradeOperation, self.operation_id)

    @property
    def host(self):
        return db.session.get(Host, self.op.host_id)

    def instance(self, instance_id):
        return db.session.get(QLInstance, int(instance_id))

    def fence(self):
        """Raise StaleExecution unless this execution still owns a live operation."""
        db.session.flush()
        row = db.session.execute(
            select(HostRuntimeUpgradeOperation.fencing_token, HostRuntimeUpgradeOperation.state)
            .where(HostRuntimeUpgradeOperation.id == self.operation_id)).one_or_none()
        if row is None or row[0] != self.token:
            raise StaleExecution(f'operation {self.operation_id} token {self.token} superseded')
        if row[1] in TERMINAL_STATES:
            raise StaleExecution(f'operation {self.operation_id} is already {row[1]}')
        if self.locked:
            try:
                self.deps.locks.renew(self.operation_id, self.lock_token, self.op.host_id,
                                      self.instance_ids())
            except Exception:
                log.exception('Could not renew execution locks of upgrade %s', self.operation_id)

    # --- locks -----------------------------------------------------------------------
    def instance_ids(self):
        return sorted(int(key) for key in (self.outcomes().get('instances') or {})) or \
            sorted(int(item['instance_id']) for item in self.inputs().get('instances') or [])

    def acquire_locks(self):
        self.locked = bool(self.deps.locks.acquire(
            self.operation_id, self.lock_token, self.op.host_id, self.instance_ids()))
        return self.locked

    def release_locks(self):
        """Release only the execution locks this token owns; never the reservation."""
        if not self.locked:
            return
        try:
            self.deps.locks.release(self.operation_id, self.lock_token, self.op.host_id,
                                    self.instance_ids())
        except Exception:
            log.exception('Could not release execution locks of upgrade %s', self.operation_id)
        self.locked = False

    # --- JSON columns ------------------------------------------------------------------
    def inputs(self):
        return json.loads(self.op.inputs_json or '{}')

    def outcomes(self):
        data = json.loads(self.op.instance_outcomes_json or '{}')
        data.setdefault('host', {})
        data.setdefault('instances', {})
        return data

    def originals(self):
        """{instance_id: 'running' | 'stopped'} from the immutable capture."""
        return {int(key): value for key, value in json.loads(self.op.original_instance_states_json or '{}').items()}

    def instance_outcome(self, instance_id):
        return self.outcomes()['instances'].get(str(int(instance_id)), {})

    def _write_outcomes(self, data):
        self.op.instance_outcomes_json = json.dumps(data, sort_keys=True)

    def record(self, instance_id, commit=True, **fields):
        """Merge fields into one instance's outcome (committed unless told otherwise)."""
        data = self.outcomes()
        entry = data['instances'].setdefault(str(int(instance_id)), {})
        entry.update(fields)
        self._write_outcomes(data)
        if commit:
            db.session.commit()

    def record_host(self, commit=True, **fields):
        data = self.outcomes()
        data['host'].update(fields)
        self._write_outcomes(data)
        if commit:
            db.session.commit()

    def set_state(self, state, phase=None, commit=True, **fields):
        op = self.op
        op.state = state
        op.phase = phase if phase is not None else state
        for key, value in fields.items():
            setattr(op, key, value)
        if commit:
            db.session.commit()
