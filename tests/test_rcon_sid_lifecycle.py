import threading
import time


def test_operation_started_before_close_drains_before_close_body():
    from ui.rcon_sid_lifecycle import closing, operation

    operation_entered = threading.Event()
    release_operation = threading.Event()
    close_body_entered = threading.Event()

    def run_operation():
        with operation("sid-a") as accepted:
            assert accepted
            operation_entered.set()
            assert release_operation.wait(timeout=2)

    def run_close():
        with closing("sid-a") as should_cleanup:
            assert should_cleanup
            close_body_entered.set()

    active = threading.Thread(target=run_operation)
    closer = threading.Thread(target=run_close)
    active.start()
    assert operation_entered.wait(timeout=2)
    closer.start()
    _wait_until_closing("sid-a")
    assert not close_body_entered.is_set()
    release_operation.set()
    active.join(timeout=2)
    closer.join(timeout=2)

    assert not active.is_alive() and not closer.is_alive()
    assert close_body_entered.is_set()


def test_operation_attempted_after_close_begins_is_rejected():
    from ui.rcon_sid_lifecycle import closing, operation

    close_body_entered = threading.Event()
    release_close = threading.Event()

    def run_close():
        with closing("sid-a") as should_cleanup:
            assert should_cleanup
            close_body_entered.set()
            assert release_close.wait(timeout=2)

    closer = threading.Thread(target=run_close)
    closer.start()
    assert close_body_entered.wait(timeout=2)
    with operation("sid-a") as accepted:
        assert accepted is False
    release_close.set()
    closer.join(timeout=2)
    assert not closer.is_alive()


def test_many_completed_sid_lifecycles_leave_bounded_stripes_and_no_records():
    from ui import rcon_sid_lifecycle

    stripe_count = rcon_sid_lifecycle.stripe_count()
    for number in range(stripe_count * 20):
        sid = f"sid-{number}"
        with rcon_sid_lifecycle.operation(sid) as accepted:
            assert accepted
        with rcon_sid_lifecycle.closing(sid) as should_cleanup:
            assert should_cleanup

    assert rcon_sid_lifecycle.stripe_count() == stripe_count
    assert rcon_sid_lifecycle.bookkeeping() == {}


def _wait_until_closing(sid):
    from ui.rcon_sid_lifecycle import bookkeeping

    deadline = time.monotonic() + 2
    while not bookkeeping().get(sid, {}).get("closing"):
        assert time.monotonic() < deadline
