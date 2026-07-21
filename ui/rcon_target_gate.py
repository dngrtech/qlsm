"""Bounded FIFO serialization for RCON target lifecycle side effects."""

from collections import deque
from contextlib import contextmanager
import threading

TargetKey = tuple[int, int]
_STRIPE_COUNT = 64
_CONDITIONS = tuple(
    threading.Condition(threading.RLock()) for _ in range(_STRIPE_COUNT)
)
_TICKETS: tuple[dict[TargetKey, deque[object]], ...] = tuple(
    {} for _ in range(_STRIPE_COUNT)
)


def _stripe(key: TargetKey) -> int:
    return hash(key) % len(_CONDITIONS)


@contextmanager
def operation(host_id: int, instance_id: int):
    """Serialize one target's lifecycle side effects in FIFO arrival order.

    Conditions are fixed-size stripes. Per-target ticket queues are ephemeral,
    and the caller never holds a stripe while running DB, Socket.IO, or Redis
    work.
    """
    key = (host_id, instance_id)
    stripe = _stripe(key)
    condition = _CONDITIONS[stripe]
    tickets = _TICKETS[stripe]
    ticket = object()
    with condition:
        queue = tickets.setdefault(key, deque())
        queue.append(ticket)
        try:
            while queue[0] is not ticket:
                condition.wait()
        except BaseException:
            queue.remove(ticket)
            if not queue:
                tickets.pop(key, None)
            condition.notify_all()
            raise
    try:
        yield
    finally:
        with condition:
            queue = tickets[key]
            queue.remove(ticket)
            if not queue:
                tickets.pop(key, None)
            condition.notify_all()


def operation_bookkeeping() -> dict[TargetKey, int]:
    """Return outstanding target ticket counts for diagnostics and tests."""
    result = {}
    for condition, tickets in zip(_CONDITIONS, _TICKETS):
        with condition:
            result.update({key: len(queue) for key, queue in tickets.items()})
    return result


def stripe_count() -> int:
    """Return the fixed synchronization stripe count."""
    return len(_CONDITIONS)
