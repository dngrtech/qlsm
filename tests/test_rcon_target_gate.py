import threading
import time


def test_target_operation_serializes_same_target_in_fifo_order():
    from ui.rcon_target_gate import operation, operation_bookkeeping

    first_entered = threading.Event()
    release_first = threading.Event()
    order = []

    def operate(name):
        with operation(7, 8):
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
    _wait_for_tickets(operation_bookkeeping, (7, 8), 2)
    threads[2].start()
    _wait_for_tickets(operation_bookkeeping, (7, 8), 3)
    release_first.set()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert order == ["first", "second", "third"]
    assert operation_bookkeeping() == {}


def test_many_unique_target_operations_leave_bounded_stripes_and_no_tickets():
    from ui import rcon_target_gate

    stripe_count = rcon_target_gate.stripe_count()
    for number in range(stripe_count * 20):
        with rcon_target_gate.operation(number, number + 1):
            assert rcon_target_gate.operation_bookkeeping()[
                (number, number + 1)
            ] == 1

    assert rcon_target_gate.stripe_count() == stripe_count
    assert rcon_target_gate.operation_bookkeeping() == {}


def test_rcon_production_modules_stay_below_300_code_lines():
    from pathlib import Path

    root = Path(__file__).parents[1] / "ui"
    modules = [
        root / "rcon_ownership.py",
        root / "rcon_target_gate.py",
        root / "rcon_sid_lifecycle.py",
        root / "rcon_transport.py",
        root / "socketio_events.py",
    ]
    counts = {
        path.name: sum(
            bool(line.strip()) and not line.lstrip().startswith("#")
            for line in path.read_text().splitlines()
        )
        for path in modules
    }

    assert counts == {name: count for name, count in counts.items() if count <= 300}
    assert all(len(path.read_text().splitlines()) < 500 for path in modules)


def _wait_for_tickets(bookkeeping, key, count):
    deadline = time.monotonic() + 2
    while bookkeeping().get(key, 0) < count:
        assert time.monotonic() < deadline
