import threading

import pytest


@pytest.fixture(autouse=True)
def clear_registry():
    from ui.rcon_ownership import cleanup_sid

    for sid in ("sid-a", "sid-b", "race"):
        cleanup_sid(sid)
    yield
    for sid in ("sid-a", "sid-b", "race"):
        cleanup_sid(sid)


def test_first_acquisition_and_idempotent_reacquire():
    from ui.rcon_ownership import acquire_owner, snapshot_owned

    first = acquire_owner("sid-a", 1, 2, "individual")
    again = acquire_owner("sid-a", 1, 2, "individual")

    assert first.changed is True
    assert first.first_owner is True
    assert first.final_owner is False
    assert first.owners == frozenset({"individual"})
    assert again.changed is False
    assert again.first_owner is False
    assert again.owners == frozenset({"individual"})
    assert snapshot_owned("sid-a") == {(1, 2): frozenset({"individual"})}


def test_individual_and_fleet_share_one_first_and_final_transition():
    from ui.rcon_ownership import acquire_owner, release_owner

    individual = acquire_owner("sid-a", 1, 2, "individual")
    fleet = acquire_owner("sid-a", 1, 2, "fleet")
    release_individual = release_owner("sid-a", 1, 2, "individual")
    release_fleet = release_owner("sid-a", 1, 2, "fleet")

    assert individual.first_owner is True
    assert fleet.first_owner is False
    assert fleet.owners == frozenset({"individual", "fleet"})
    assert release_individual.final_owner is False
    assert release_individual.owners == frozenset({"fleet"})
    assert release_fleet.final_owner is True
    assert release_fleet.owners == frozenset()


def test_either_leave_order_preserves_the_other_owner():
    from ui.rcon_ownership import acquire_owner, owns, release_owner

    for first, remaining in (("fleet", "individual"), ("individual", "fleet")):
        acquire_owner("sid-a", 1, 2, "individual")
        acquire_owner("sid-a", 1, 2, "fleet")
        transition = release_owner("sid-a", 1, 2, first)
        assert transition.final_owner is False
        assert owns("sid-a", 1, 2, remaining)
        assert release_owner("sid-a", 1, 2, remaining).final_owner is True


def test_final_release_has_only_one_final_transition_under_threads():
    from ui.rcon_ownership import acquire_owner, release_owner

    acquire_owner("sid-a", 1, 2, "individual")
    acquire_owner("sid-a", 1, 2, "fleet")
    barrier = threading.Barrier(3)
    results = []

    def release(owner):
        barrier.wait()
        results.append(release_owner("sid-a", 1, 2, owner))

    threads = [
        threading.Thread(target=release, args=("individual",)),
        threading.Thread(target=release, args=("fleet",)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert sum(result.final_owner for result in results) == 1
    assert sum(result.changed for result in results) == 2


def test_disconnect_cleanup_is_idempotent_and_sid_scoped():
    from ui.rcon_ownership import acquire_owner, cleanup_sid, owns, snapshot_owned

    acquire_owner("sid-a", 1, 2, "individual")
    acquire_owner("sid-a", 3, 4, "fleet")
    acquire_owner("sid-b", 1, 2, "individual")

    transitions = cleanup_sid("sid-a")

    assert {(item.host_id, item.instance_id) for item in transitions} == {(1, 2), (3, 4)}
    assert all(item.final_owner and not item.owners for item in transitions)
    assert cleanup_sid("sid-a") == []
    assert snapshot_owned("sid-a") == {}
    assert owns("sid-b", 1, 2, "individual")


def test_target_cleanup_removes_only_one_sid_target_and_pending_attempt():
    from ui.rcon_ownership import (
        ConnectCompletionStatus,
        acquire_owner,
        begin_connect,
        cleanup_sid_residual,
        cleanup_target,
        complete_connect,
        owns,
        snapshot_owned,
    )
    from ui.rcon_target_gate import operation

    attempt = begin_connect(acquire_owner("sid-a", 1, 2, "individual"))
    acquire_owner("sid-a", 3, 4, "fleet")
    acquire_owner("sid-b", 1, 2, "individual")

    with operation(1, 2):
        transition = cleanup_target("sid-a", 1, 2)
    cleanup_sid_residual("sid-a")

    assert transition.final_owner and transition.owners == frozenset()
    assert complete_connect(attempt, succeeded=True).status is ConnectCompletionStatus.STALE
    assert snapshot_owned("sid-a") == {(3, 4): frozenset({"fleet"})}
    assert owns("sid-b", 1, 2, "individual")


def test_rollback_removes_only_changed_acquisition_and_preserves_other_owner():
    from ui.rcon_ownership import acquire_owner, owns, rollback_acquire

    individual = acquire_owner("sid-a", 1, 2, "individual")
    fleet = acquire_owner("sid-a", 1, 2, "fleet")
    rolled_back = rollback_acquire(fleet)

    assert rolled_back.changed is True
    assert rolled_back.final_owner is False
    assert owns("sid-a", 1, 2, "individual")
    assert not owns("sid-a", 1, 2, "fleet")
    assert rollback_acquire(individual).final_owner is True


def test_rollback_of_idempotent_reacquire_is_noop():
    from ui.rcon_ownership import acquire_owner, owns, rollback_acquire

    acquire_owner("sid-a", 1, 2, "individual")
    duplicate = acquire_owner("sid-a", 1, 2, "individual")

    result = rollback_acquire(duplicate)

    assert result.changed is False
    assert owns("sid-a", 1, 2, "individual")


def test_failed_connect_wakes_surviving_owner_to_retry_deterministically():
    from ui.rcon_ownership import (
        acquire_owner,
        begin_connect,
        complete_connect,
        owns,
    )

    first_publish_started = threading.Event()
    allow_first_failure = threading.Event()
    second_owner_acquired = threading.Event()
    publications = []
    outcomes = {}

    def join(owner):
        acquisition = acquire_owner("race", 7, 8, owner)
        if owner == "fleet":
            second_owner_acquired.set()
        attempt = begin_connect(acquisition)
        if not attempt.should_publish:
            outcomes[owner] = attempt.established
            return
        publications.append(owner)
        if owner == "individual":
            first_publish_started.set()
            assert allow_first_failure.wait(timeout=2)
            complete_connect(attempt, succeeded=False)
            outcomes[owner] = False
        else:
            complete_connect(attempt, succeeded=True)
            outcomes[owner] = True

    first = threading.Thread(target=join, args=("individual",))
    survivor = threading.Thread(target=join, args=("fleet",))
    first.start()
    assert first_publish_started.wait(timeout=2)
    survivor.start()
    assert second_owner_acquired.wait(timeout=2)
    allow_first_failure.set()
    first.join(timeout=2)
    survivor.join(timeout=2)

    assert not first.is_alive() and not survivor.is_alive()
    assert publications == ["individual", "fleet"]
    assert outcomes == {"individual": False, "fleet": True}
    assert not owns("race", 7, 8, "individual")
    assert owns("race", 7, 8, "fleet")
    assert begin_connect(acquire_owner("race", 7, 8, "fleet")).established


def test_successful_connect_has_one_publisher_for_concurrent_owners():
    from ui.rcon_ownership import acquire_owner, begin_connect, complete_connect

    publish_started = threading.Event()
    finish_publish = threading.Event()
    publications = []
    results = []

    def join(owner):
        attempt = begin_connect(acquire_owner("race", 7, 8, owner))
        if attempt.should_publish:
            publications.append(owner)
            publish_started.set()
            assert finish_publish.wait(timeout=2)
            complete_connect(attempt, succeeded=True)
        results.append(attempt.should_publish or attempt.established)

    first = threading.Thread(target=join, args=("individual",))
    second = threading.Thread(target=join, args=("fleet",))
    first.start()
    assert publish_started.wait(timeout=2)
    second.start()
    finish_publish.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert publications == ["individual"]
    assert results == [True, True]


def test_nonfinal_release_wakes_waiting_connect_owner(monkeypatch):
    from ui import rcon_ownership
    from ui.rcon_ownership import acquire_owner, begin_connect, release_owner

    publisher = begin_connect(acquire_owner("race", 7, 8, "individual"))
    assert publisher.should_publish
    waiter_acquired = threading.Event()
    waiter_blocked = threading.Event()
    waiter_returned = threading.Event()
    outcomes = []
    condition = rcon_ownership._sid_condition("race")
    original_wait = condition.wait

    def observed_wait(*args, **kwargs):
        waiter_blocked.set()
        return original_wait(*args, **kwargs)

    monkeypatch.setattr(condition, "wait", observed_wait)

    def wait_for_connect():
        acquisition = acquire_owner("race", 7, 8, "fleet")
        waiter_acquired.set()
        outcomes.append(begin_connect(acquisition))
        waiter_returned.set()

    waiter = threading.Thread(target=wait_for_connect)
    waiter.start()
    assert waiter_acquired.wait(timeout=2)
    assert waiter_blocked.wait(timeout=2)

    transition = release_owner("race", 7, 8, "fleet")

    assert transition.changed and not transition.final_owner
    assert waiter_returned.wait(timeout=2)
    waiter.join(timeout=2)
    assert not waiter.is_alive()
    assert len(outcomes) == 1
    assert not outcomes[0].should_publish
    assert not outcomes[0].established


def test_connect_completion_explicitly_reports_stale_success_after_cleanup():
    from ui.rcon_ownership import (
        ConnectCompletionStatus,
        acquire_owner,
        begin_connect,
        cleanup_sid,
        complete_connect,
    )

    attempt = begin_connect(acquire_owner("race", 7, 8, "individual"))
    cleanup_sid("race")

    completion = complete_connect(attempt, succeeded=True)

    assert completion.status is ConnectCompletionStatus.STALE
    assert completion.rollback is None


def test_connect_completion_explicitly_reports_current_success():
    from ui.rcon_ownership import (
        ConnectCompletionStatus,
        acquire_owner,
        begin_connect,
        complete_connect,
    )

    attempt = begin_connect(acquire_owner("race", 7, 8, "individual"))

    completion = complete_connect(attempt, succeeded=True)

    assert completion.status is ConnectCompletionStatus.ESTABLISHED
    assert completion.rollback is None
    assert completion.claimant_active is True


def test_successful_connect_reports_released_claimant_while_survivor_is_established():
    from ui.rcon_ownership import (
        ConnectCompletionStatus,
        acquire_owner,
        begin_connect,
        complete_connect,
        owns,
        release_owner,
    )

    individual = acquire_owner("race", 7, 8, "individual")
    attempt = begin_connect(individual)
    acquire_owner("race", 7, 8, "fleet")
    release_owner("race", 7, 8, "individual")

    completion = complete_connect(attempt, succeeded=True)

    assert completion.status is ConnectCompletionStatus.ESTABLISHED
    assert completion.claimant_active is False
    assert owns("race", 7, 8, "fleet")
    assert begin_connect(acquire_owner("race", 7, 8, "fleet")).established


def test_failed_connect_without_survivor_rolls_back_and_cleans_state():
    from ui import rcon_ownership

    acquisition = rcon_ownership.acquire_owner("race", 7, 8, "individual")
    attempt = rcon_ownership.begin_connect(acquisition)

    completion = rcon_ownership.complete_connect(attempt, succeeded=False)

    assert completion.status is rcon_ownership.ConnectCompletionStatus.FAILED
    assert completion.rollback is not None and completion.rollback.final_owner
    assert not rcon_ownership.owns("race", 7, 8)
    assert "race" not in rcon_ownership._connection_states


def test_many_cleaned_sids_do_not_accumulate_lock_or_connection_storage():
    from ui import rcon_ownership

    stripe_count = len(rcon_ownership._SID_CONDITIONS)
    for number in range(stripe_count * 20):
        sid = f"lifecycle-{number}"
        rcon_ownership.acquire_owner(sid, 1, 2, "individual")
        rcon_ownership.cleanup_sid(sid)

    assert len(rcon_ownership._SID_CONDITIONS) == stripe_count
    assert not hasattr(rcon_ownership, "_sid_locks")
    assert rcon_ownership._registry == {}
    assert rcon_ownership._connection_states == {}


def test_reconciliation_snapshot_requires_revalidation_before_command_publish():
    """A stale command snapshot cannot authorize after concurrent cleanup."""
    from ui.rcon_ownership import acquire_owner, cleanup_sid, owns, snapshot_owned

    acquire_owner("race", 7, 8, "fleet")
    snapshot_taken = threading.Barrier(2)
    cleanup_done = threading.Barrier(2)
    published = []

    def command_path():
        snapshot = snapshot_owned("race", owner="fleet")
        assert (7, 8) in snapshot
        snapshot_taken.wait()
        cleanup_done.wait()
        if owns("race", 7, 8, "fleet"):
            published.append((7, 8))

    def cleanup_path():
        snapshot_taken.wait()
        cleanup_sid("race")
        cleanup_done.wait()

    command = threading.Thread(target=command_path)
    cleanup = threading.Thread(target=cleanup_path)
    command.start()
    cleanup.start()
    command.join()
    cleanup.join()

    assert published == []
    assert snapshot_owned("race") == {}


@pytest.mark.parametrize("owner", ["bad", "", None, 1])
def test_only_declared_owner_names_are_accepted(owner):
    from ui.rcon_ownership import acquire_owner

    with pytest.raises(ValueError, match="Unknown RCON owner"):
        acquire_owner("sid-a", 1, 2, owner)
