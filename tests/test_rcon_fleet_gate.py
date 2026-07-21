import threading
import time

import pytest


def test_fleet_operation_serializes_same_sid_in_fifo_order():
    from ui.rcon_fleet_gate import operation, operation_bookkeeping

    first_entered = threading.Event()
    release_first = threading.Event()
    order = []

    def operate(name):
        with operation("sid-one"):
            order.append(name)
            if name == "first":
                first_entered.set()
                assert release_first.wait(timeout=2)

    threads = [
        threading.Thread(target=operate, args=(name,))
        for name in ("first", "second", "third")
    ]
    threads[0].start()
    assert first_entered.wait(timeout=2)
    threads[1].start()
    _wait_for_tickets(operation_bookkeeping, "sid-one", 2)
    threads[2].start()
    _wait_for_tickets(operation_bookkeeping, "sid-one", 3)
    release_first.set()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert order == ["first", "second", "third"]
    assert operation_bookkeeping() == {}


def test_different_sid_operations_progress_independently():
    from ui import rcon_fleet_gate

    first_sid = "sid-a"
    second_sid = next(
        f"sid-{number}" for number in range(1000)
        if rcon_fleet_gate._stripe(f"sid-{number}") != rcon_fleet_gate._stripe(first_sid)
    )
    first_entered = threading.Event()
    second_entered = threading.Event()
    release = threading.Event()

    def operate(sid, entered):
        with rcon_fleet_gate.operation(sid):
            entered.set()
            assert release.wait(timeout=2)

    first = threading.Thread(target=operate, args=(first_sid, first_entered))
    second = threading.Thread(target=operate, args=(second_sid, second_entered))
    first.start()
    assert first_entered.wait(timeout=2)
    second.start()
    assert second_entered.wait(timeout=2)
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert not first.is_alive() and not second.is_alive()
    assert rcon_fleet_gate.operation_bookkeeping() == {}


def test_waiter_cancellation_and_body_failure_clean_up_tickets(monkeypatch):
    from ui import rcon_fleet_gate

    entered = threading.Event()
    release = threading.Event()
    cancelled = []
    original_wait = threading.Condition.wait

    def cancellable_wait(condition, timeout=None):
        if threading.current_thread().name == "cancelled-waiter":
            raise RuntimeError("cancelled")
        return original_wait(condition, timeout)

    monkeypatch.setattr(threading.Condition, "wait", cancellable_wait)

    def holder():
        with pytest.raises(ValueError):
            with rcon_fleet_gate.operation("sid-cleanup"):
                entered.set()
                assert release.wait(timeout=2)
                raise ValueError("body failed")

    def waiter():
        with pytest.raises(RuntimeError, match="cancelled"):
            with rcon_fleet_gate.operation("sid-cleanup"):
                pass
        cancelled.append(True)

    first = threading.Thread(target=holder)
    first.start()
    assert entered.wait(timeout=2)
    second = threading.Thread(target=waiter, name="cancelled-waiter")
    second.start()
    second.join(timeout=2)
    assert not second.is_alive()
    assert cancelled == [True]
    assert rcon_fleet_gate.operation_bookkeeping() == {"sid-cleanup": 1}
    release.set()
    first.join(timeout=2)
    assert not first.is_alive()
    assert rcon_fleet_gate.operation_bookkeeping() == {}


def test_many_unique_sid_operations_leave_bounded_stripes_and_no_tickets():
    from ui import rcon_fleet_gate

    stripe_count = rcon_fleet_gate.stripe_count()
    for number in range(stripe_count * 20):
        sid = f"unique-sid-{number}"
        with rcon_fleet_gate.operation(sid):
            assert rcon_fleet_gate.operation_bookkeeping()[sid] == 1

    assert rcon_fleet_gate.stripe_count() == stripe_count
    assert rcon_fleet_gate.operation_bookkeeping() == {}


def _wait_for_tickets(bookkeeping, sid, count):
    deadline = time.monotonic() + 2
    while bookkeeping().get(sid, 0) < count:
        assert time.monotonic() < deadline
