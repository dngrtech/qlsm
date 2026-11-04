"""Durable state and fenced ownership of one host runtime upgrade operation.

The HostRuntimeUpgradeOperation row is the source of truth. Every execution
(the first worker, or a recovery worker) takes ownership by compare-and-set
incrementing `fencing_token`. Every write it makes is committed through
Execution.commit(), which is conditional on that token only (a claim refuses
terminal operations, so finishing one always bumps the token first), and
every side effect is preceded by Execution.fence(), which also refuses a
terminal operation; a superseded execution gets StaleExecution and stops.
Intent is committed before each side effect and the outcome after it is
verified.

instance_outcomes_json layout:

    {"host": {"original_runtime_deps_isolated": false, "rollback_reason": "..."},
     "instances": {"<id>": {"original_status": "running",
                            "original_python_deps_path": null,
                            "stop": "requested|ok|failed|verified_inactive", "convert": "swapping|swapped",
                            "configure": "requested|ok|failed", "start": "requested|ok|failed",
                            "rollback": {"phase": "...", "ok": bool, "error": "...", "pending": bool},
                            "error": "..."}}}
"""
import datetime
import json
import logging

from sqlalchemy import update

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

    def commit(self):
        """Commit pending changes only if this execution still owns the operation.

        The check is a conditional UPDATE on (id, fencing_token) inside the same
        transaction as the changes. Its rowcount decides: 0 means a takeover
        committed first, so everything pending is rolled back and
        StaleExecution raised. Once this transaction has written, SQLite holds
        the write lock, so a takeover cannot commit between the check and this
        commit. The token alone is enough: claim_operation refuses terminal
        operations, so another executor can only finish the operation after
        bumping the token. Every operation-row, host and instance write the
        executor makes goes through here.
        """
        table = HostRuntimeUpgradeOperation.__table__
        result = db.session.connection().execute(
            update(table)
            .where(table.c.id == self.operation_id, table.c.fencing_token == self.token)
            .values(updated_at=_now()))
        if result.rowcount != 1:
            db.session.rollback()
            raise StaleExecution(f'operation {self.operation_id} token {self.token} superseded')
        db.session.commit()

    def fence(self):
        """Commit (fenced) and re-check ownership before a side effect; renew locks."""
        self.commit()
        if self.op.is_terminal:
            raise StaleExecution(f'operation {self.operation_id} is already {self.op.state}')
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
            self.commit()

    def record_host(self, commit=True, **fields):
        data = self.outcomes()
        data['host'].update(fields)
        self._write_outcomes(data)
        if commit:
            self.commit()

    def set_state(self, state, phase=None, commit=True, **fields):
        op = self.op
        op.state = state
        op.phase = phase if phase is not None else state
        for key, value in fields.items():
            setattr(op, key, value)
        if commit:
            self.commit()
