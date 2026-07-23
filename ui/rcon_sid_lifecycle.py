"""Process-local, bounded lifecycle boundary for Socket.IO session IDs.

An operation registers before it can wait on a target gate. Disconnect marks the
SID closing and drains registered operations without holding this module's
condition during target, registry, Socket.IO, DB, or Redis work. Records are
removed after operations or close complete; fixed condition stripes are the only
persistent synchronization storage.

Removing the closing record relies on Socket.IO's contract that no new events
for a SID are dispatched after its disconnect handler completes. Deployments
that violate that contract need a distributed/session-generation authority.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import threading

_STRIPE_COUNT = 64
_CONDITIONS = tuple(
    threading.Condition(threading.RLock()) for _ in range(_STRIPE_COUNT)
)
_RECORDS: tuple[dict[str, "_SidState"], ...] = tuple(
    {} for _ in range(_STRIPE_COUNT)
)


@dataclass
class _SidState:
    active: int = 0
    closing: bool = False


def _stripe(sid: str) -> int:
    return hash(sid) % len(_CONDITIONS)


@contextmanager
def operation(sid: str):
    """Register a SID operation, yielding false when disconnect is closing it."""
    stripe = _stripe(sid)
    condition = _CONDITIONS[stripe]
    records = _RECORDS[stripe]
    state = None
    accepted = False
    with condition:
        current = records.get(sid)
        if current is None or not current.closing:
            state = current or _SidState()
            records[sid] = state
            state.active += 1
            accepted = True
    try:
        yield accepted
    finally:
        if accepted:
            assert state is not None
            with condition:
                state.active -= 1
                if state.active == 0 and not state.closing:
                    records.pop(sid, None)
                condition.notify_all()


@contextmanager
def closing(sid: str):
    """Mark ``sid`` closing, drain active operations, and yield cleanup authority.

    Exactly one concurrent closer receives true. Its cleanup body runs after the
    active count reaches zero and outside the SID condition. Other closers wait
    for that cleanup to finish and receive false.
    """
    stripe = _stripe(sid)
    condition = _CONDITIONS[stripe]
    records = _RECORDS[stripe]
    state = None
    should_cleanup = False
    with condition:
        state = records.setdefault(sid, _SidState())
        if state.closing:
            while records.get(sid) is state:
                condition.wait()
        else:
            state.closing = True
            while state.active:
                condition.wait()
            should_cleanup = True
    try:
        yield should_cleanup
    finally:
        if should_cleanup:
            with condition:
                if records.get(sid) is state:
                    records.pop(sid, None)
                condition.notify_all()


def is_closing(sid: str) -> bool:
    """Return whether disconnect has marked ``sid`` closing."""
    stripe = _stripe(sid)
    with _CONDITIONS[stripe]:
        state = _RECORDS[stripe].get(sid)
        return state is not None and state.closing


def bookkeeping() -> dict[str, dict[str, int | bool]]:
    """Snapshot active/closing ephemeral records for diagnostics and tests."""
    result = {}
    for condition, records in zip(_CONDITIONS, _RECORDS):
        with condition:
            result.update({
                sid: {"active": state.active, "closing": state.closing}
                for sid, state in records.items()
            })
    return result


def stripe_count() -> int:
    """Return the fixed synchronization stripe count."""
    return len(_CONDITIONS)
