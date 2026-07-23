"""Bounded FIFO serialization for per-SID fleet reconciliation."""

from collections import deque
from contextlib import contextmanager
import threading

_STRIPE_COUNT = 64
_CONDITIONS = tuple(
    threading.Condition(threading.RLock()) for _ in range(_STRIPE_COUNT)
)
_TICKETS: tuple[dict[str, deque[object]], ...] = tuple(
    {} for _ in range(_STRIPE_COUNT)
)


def _stripe(sid: str) -> int:
    return hash(sid) % len(_CONDITIONS)


@contextmanager
def operation(sid: str):
    """Serialize one SID's fleet transaction in FIFO arrival order.

    Conditions are fixed-size stripes. Per-SID ticket queues are ephemeral, and
    the caller never holds a stripe while running DB, Socket.IO, or Redis work.
    """
    stripe = _stripe(sid)
    condition = _CONDITIONS[stripe]
    tickets = _TICKETS[stripe]
    ticket = object()
    with condition:
        queue = tickets.setdefault(sid, deque())
        queue.append(ticket)
        try:
            while queue[0] is not ticket:
                condition.wait()
        except BaseException:
            queue.remove(ticket)
            if not queue:
                tickets.pop(sid, None)
            condition.notify_all()
            raise
    try:
        yield
    finally:
        with condition:
            queue = tickets[sid]
            queue.remove(ticket)
            if not queue:
                tickets.pop(sid, None)
            condition.notify_all()


def operation_bookkeeping() -> dict[str, int]:
    """Return outstanding SID ticket counts for diagnostics and tests."""
    result = {}
    for condition, tickets in zip(_CONDITIONS, _TICKETS):
        with condition:
            result.update({sid: len(queue) for sid, queue in tickets.items()})
    return result


def stripe_count() -> int:
    """Return the fixed synchronization stripe count."""
    return len(_CONDITIONS)
