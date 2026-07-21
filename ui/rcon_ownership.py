"""Process-local RCON room ownership and connection coordination.

The packaged deployment uses one Gunicorn worker with threads. This registry is
not suitable for non-sticky Socket.IO routing across multiple worker processes.
Registry mutations hold only short striped locks; callers perform DB, Socket.IO,
and Redis work outside those locks.
"""

from dataclasses import dataclass
from enum import Enum
import threading

from ui.rcon_target_gate import operation

Owner = str
TargetKey = tuple[int, int]
_VALID_OWNERS = frozenset({"individual", "fleet"})
_STRIPE_COUNT = 64


@dataclass(frozen=True)
class OwnershipTransition:
    sid: str
    host_id: int
    instance_id: int
    owner: Owner | None
    changed: bool
    first_owner: bool
    final_owner: bool
    owners: frozenset[Owner]


@dataclass(frozen=True)
class ConnectAttempt:
    """Result of waiting for or claiming target connection establishment."""

    acquisition: OwnershipTransition
    should_publish: bool
    established: bool
    _token: object | None = None


class ConnectCompletionStatus(Enum):
    """Explicit outcome of completing a claimed publication attempt."""

    ESTABLISHED = "established"
    FAILED = "failed"
    STALE = "stale"


@dataclass(frozen=True)
class ConnectCompletion:
    status: ConnectCompletionStatus
    rollback: OwnershipTransition | None = None
    claimant_active: bool = False


@dataclass
class _ConnectionState:
    status: str
    token: object | None = None


_registry: dict[str, dict[TargetKey, set[Owner]]] = {}
_connection_states: dict[str, dict[TargetKey, _ConnectionState]] = {}
_SID_CONDITIONS = tuple(
    threading.Condition(threading.RLock()) for _ in range(_STRIPE_COUNT)
)



def _sid_condition(sid: str) -> threading.Condition:
    return _SID_CONDITIONS[hash(sid) % len(_SID_CONDITIONS)]


def _check_owner(owner: Owner) -> None:
    if owner not in _VALID_OWNERS:
        raise ValueError("Unknown RCON owner")


def acquire_owner(
    sid: str, host_id: int, instance_id: int, owner: Owner,
) -> OwnershipTransition:
    _check_owner(owner)
    with _sid_condition(sid):
        targets = _registry.setdefault(sid, {})
        owners = targets.setdefault((host_id, instance_id), set())
        was_empty = not owners
        changed = owner not in owners
        owners.add(owner)
        return _transition(
            sid, host_id, instance_id, owner, changed,
            first_owner=changed and was_empty, final_owner=False, owners=owners,
        )


def release_owner(
    sid: str, host_id: int, instance_id: int, owner: Owner,
) -> OwnershipTransition:
    _check_owner(owner)
    condition = _sid_condition(sid)
    with condition:
        transition = _release_owner_locked(sid, host_id, instance_id, owner)
        if transition.final_owner:
            _drop_connection_state_locked(sid, (host_id, instance_id))
        if transition.changed:
            condition.notify_all()
        return transition


def rollback_acquire(acquisition: OwnershipTransition) -> OwnershipTransition:
    """Undo only a changed acquisition, preserving all other owners."""
    if not acquisition.changed:
        return OwnershipTransition(
            acquisition.sid, acquisition.host_id, acquisition.instance_id,
            acquisition.owner, False, False, False, acquisition.owners,
        )
    if acquisition.owner is None:
        raise ValueError("Acquisition has no owner")
    return release_owner(
        acquisition.sid, acquisition.host_id, acquisition.instance_id,
        acquisition.owner,
    )


def begin_connect(acquisition: OwnershipTransition) -> ConnectAttempt:
    """Wait for an active attempt, or claim the next publication attempt.

    Only one owner per SID/target receives ``should_publish=True``. Waiting
    owners observe success, or claim a retry after failure. The caller must
    pair a claimed attempt with :func:`complete_connect` after publishing.
    """
    if acquisition.owner is None:
        raise ValueError("Acquisition has no owner")
    sid = acquisition.sid
    key = (acquisition.host_id, acquisition.instance_id)
    condition = _sid_condition(sid)
    with condition:
        while True:
            owners = _registry.get(sid, {}).get(key, set())
            if acquisition.owner not in owners:
                return ConnectAttempt(acquisition, False, False)
            states = _connection_states.setdefault(sid, {})
            state = states.get(key)
            if state is None or state.status == "failed":
                token = object()
                states[key] = _ConnectionState("pending", token)
                return ConnectAttempt(acquisition, True, False, token)
            if state.status == "established":
                return ConnectAttempt(acquisition, False, True)
            condition.wait()


def complete_connect(
    attempt: ConnectAttempt, succeeded: bool,
) -> ConnectCompletion:
    """Complete a claim with an explicit established, failed, or stale result."""
    if not attempt.should_publish or attempt._token is None:
        raise ValueError("Connect attempt was not claimed for publication")
    acquisition = attempt.acquisition
    sid = acquisition.sid
    key = (acquisition.host_id, acquisition.instance_id)
    condition = _sid_condition(sid)
    with condition:
        states = _connection_states.get(sid, {})
        state = states.get(key)
        if state is None or state.token is not attempt._token:
            return ConnectCompletion(ConnectCompletionStatus.STALE)
        owners = _registry.get(sid, {}).get(key, set())
        if succeeded and owners:
            states[key] = _ConnectionState("established")
            completion = ConnectCompletion(
                ConnectCompletionStatus.ESTABLISHED,
                claimant_active=acquisition.owner in owners,
            )
        else:
            rollback = _rollback_acquire_locked(acquisition)
            owners = _registry.get(sid, {}).get(key, set())
            if owners:
                states[key] = _ConnectionState("failed")
            else:
                _drop_connection_state_locked(sid, key)
            completion = ConnectCompletion(
                ConnectCompletionStatus.FAILED, rollback,
            )
        condition.notify_all()
        return completion


def owns(
    sid: str, host_id: int, instance_id: int, owner: Owner | None = None,
) -> bool:
    if owner is not None:
        _check_owner(owner)
    with _sid_condition(sid):
        owners = _registry.get(sid, {}).get((host_id, instance_id), set())
        return bool(owners) if owner is None else owner in owners


def snapshot_owned(
    sid: str, owner: Owner | None = None,
) -> dict[TargetKey, frozenset[Owner]]:
    if owner is not None:
        _check_owner(owner)
    with _sid_condition(sid):
        targets = _registry.get(sid, {})
        return {
            key: frozenset(owners)
            for key, owners in targets.items()
            if owner is None or owner in owners
        }


def cleanup_target(
    sid: str, host_id: int, instance_id: int,
) -> OwnershipTransition:
    """Clear one SID's target ownership and pending state.

    Lifecycle callers must hold the target gate across this mutation,
    room participant checks, and any resulting disconnect publication.
    """
    key = (host_id, instance_id)
    condition = _sid_condition(sid)
    with condition:
        targets = _registry.get(sid, {})
        owners = targets.pop(key, set())
        changed = bool(owners)
        if not targets:
            _registry.pop(sid, None)
        _drop_connection_state_locked(sid, key)
        if changed:
            condition.notify_all()
        return OwnershipTransition(
            sid=sid,
            host_id=host_id,
            instance_id=instance_id,
            owner=None,
            changed=changed,
            first_owner=False,
            final_owner=changed,
            owners=frozenset(),
        )


def cleanup_sid(sid: str) -> list[OwnershipTransition]:
    """Clear a snapshot of SID targets through their lifecycle gates.

    This compatibility helper performs no external publication. Socket.IO
    disconnect cleanup uses ``snapshot_owned`` and ``cleanup_target`` directly
    so each target gate also covers room and Redis work.
    """
    transitions = []
    for host_id, instance_id in snapshot_owned(sid):
        with operation(host_id, instance_id):
            transition = cleanup_target(sid, host_id, instance_id)
            if transition.changed:
                transitions.append(transition)

    cleanup_sid_residual(sid)
    return transitions


def cleanup_sid_residual(sid: str) -> None:
    """Drop only ownerless connection state after snapshot-based cleanup."""
    condition = _sid_condition(sid)
    with condition:
        owned_keys = set(_registry.get(sid, {}))
        states = _connection_states.get(sid)
        if states is not None:
            for key in tuple(states):
                if key not in owned_keys:
                    states.pop(key, None)
            if not states:
                _connection_states.pop(sid, None)
        condition.notify_all()


def _rollback_acquire_locked(
    acquisition: OwnershipTransition,
) -> OwnershipTransition | None:
    if not acquisition.changed or acquisition.owner is None:
        return None
    return _release_owner_locked(
        acquisition.sid, acquisition.host_id, acquisition.instance_id,
        acquisition.owner,
    )


def _release_owner_locked(
    sid: str, host_id: int, instance_id: int, owner: Owner,
) -> OwnershipTransition:
    targets = _registry.get(sid, {})
    owners = targets.get((host_id, instance_id), set())
    changed = owner in owners
    if changed:
        owners.remove(owner)
    final_owner = changed and not owners
    if not owners:
        targets.pop((host_id, instance_id), None)
    if not targets:
        _registry.pop(sid, None)
    return _transition(
        sid, host_id, instance_id, owner, changed,
        first_owner=False, final_owner=final_owner, owners=owners,
    )


def _drop_connection_state_locked(sid: str, key: TargetKey) -> None:
    states = _connection_states.get(sid)
    if states is None:
        return
    states.pop(key, None)
    if not states:
        _connection_states.pop(sid, None)


def _transition(
    sid: str,
    host_id: int,
    instance_id: int,
    owner: Owner | None,
    changed: bool,
    first_owner: bool,
    final_owner: bool,
    owners: set[Owner],
) -> OwnershipTransition:
    return OwnershipTransition(
        sid=sid,
        host_id=host_id,
        instance_id=instance_id,
        owner=owner,
        changed=changed,
        first_owner=first_owner,
        final_owner=final_owner,
        owners=frozenset(owners),
    )
