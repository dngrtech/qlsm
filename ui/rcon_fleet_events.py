"""Authenticated fleet RCON Socket.IO lifecycle and command fan-out.

Desired-set acknowledgements contain one ordered result per normalized submitted
entry followed by sorted removals. Accepted selections report ``connecting``
(the request was accepted, not proof that the game transport is ready), rejected
entries carry a credential-free reason, and removals report ``removed``.
"""

from flask import current_app, request
from flask_socketio import join_room, leave_room, rooms

from ui.rcon_fleet_gate import operation as fleet_operation
from ui.rcon_ownership import (
    ConnectCompletionStatus,
    acquire_owner,
    begin_connect,
    complete_connect,
    owns,
    release_owner,
    rollback_acquire,
    snapshot_owned,
)
from ui.rcon_target_gate import operation as target_operation
from ui.rcon_transport import (
    MAX_RUN_ID_CHARS,
    RconPayloadError,
    RconTargetError,
    command_channel,
    command_payload,
    connect_payload,
    disconnect_payload,
    publish_json,
    resolve_fleet_target,
    room_name,
    validate_command_payload,
    validate_join_payload,
)
from ui.socketio_events import (
    _participant_count,
    authenticated_only,
    sid_operation_only,
    socketio,
)

_OWNER = "fleet"
_REJECTED = "rejected"


def _result(host_id=None, instance_id=None, state=_REJECTED, reason=None):
    item = {}
    if host_id is not None:
        item["host_id"] = host_id
    if instance_id is not None:
        item["instance_id"] = instance_id
    item["state"] = state
    if reason is not None:
        item["reason"] = reason
    return item


def _room_membership(
    sid: str, host_id: int, instance_id: int, room: str,
) -> set[str]:
    try:
        return set(rooms(sid=sid, namespace="/"))
    except Exception:
        current_app.logger.warning(
            "Unable to inspect RCON room membership for "
            "host_id=%s instance_id=%s room=%s",
            host_id, instance_id, room,
        )
        return set()


def _add_target(sid, target):
    host_id, instance_id = target.host_id, target.instance_id
    with target_operation(host_id, instance_id):
        acquisition = acquire_owner(sid, host_id, instance_id, _OWNER)
        if acquisition.first_owner:
            try:
                join_room(target.room)
            except Exception:
                rollback_acquire(acquisition)
                current_app.logger.warning(
                    "Unable to join RCON room for host_id=%s instance_id=%s room=%s",
                    host_id, instance_id, target.room,
                )
                return _result(
                    host_id, instance_id, reason="Unable to join RCON room",
                )

        attempt = begin_connect(acquisition)
        if attempt.should_publish:
            publication = publish_json(target.channel, connect_payload(target))
            completion = complete_connect(attempt, succeeded=publication.ok)
            if completion.status is ConnectCompletionStatus.STALE:
                if publication.ok and _participant_count(
                    target.room, excluding_sid=sid,
                ) == 0:
                    publish_json(target.channel, disconnect_payload())
                return _result(
                    host_id, instance_id, reason="Connection request superseded",
                )
            if not publication.ok:
                rollback = completion.rollback
                if rollback is not None and not rollback.owners:
                    try:
                        leave_room(target.room)
                    except Exception:
                        acquire_owner(sid, host_id, instance_id, _OWNER)
                        current_app.logger.warning(
                            "Unable to leave RCON room after failed connect for "
                            "host_id=%s instance_id=%s room=%s; fleet ownership restored",
                            host_id, instance_id, target.room,
                        )
                        return _result(
                            host_id,
                            instance_id,
                            reason=(
                                f"{publication.reason}; RCON room cleanup pending"
                            ),
                        )
                return _result(host_id, instance_id, reason=publication.reason)
            if not completion.claimant_active:
                return _result(
                    host_id, instance_id, reason="Connection request superseded",
                )
        elif not attempt.established:
            return _result(
                host_id, instance_id, reason="RCON connection was not established",
            )
        return _result(host_id, instance_id, state="connecting")


def _remove_target(sid: str, host_id: int, instance_id: int):
    with target_operation(host_id, instance_id):
        transition = release_owner(sid, host_id, instance_id, _OWNER)
        if not transition.changed:
            return None
        room = room_name(host_id, instance_id)
        if transition.final_owner:
            try:
                leave_room(room)
            except Exception:
                acquire_owner(sid, host_id, instance_id, _OWNER)
                current_app.logger.warning(
                    "Unable to leave RCON room for host_id=%s instance_id=%s room=%s; "
                    "fleet ownership restored",
                    host_id, instance_id, room,
                )
                return _result(
                    host_id, instance_id, reason="Unable to leave RCON room",
                )
            if _participant_count(room) == 0:
                publish_json(
                    command_channel(host_id, instance_id),
                    disconnect_payload(),
                )
        return _result(host_id, instance_id, state="removed")


def _reconcile(data):
    sid = request.sid
    with fleet_operation(sid):
        return _reconcile_serial(data, sid)


def _reconcile_serial(data, sid):
    try:
        entries = validate_join_payload(data)
    except RconPayloadError as exc:
        return {"targets": [_result(reason=exc.safe_reason)]}

    current = set(snapshot_owned(sid, _OWNER))
    accepted = set()
    results = []
    for entry in entries:
        if entry.key is None:
            results.append(_result(reason=entry.reason))
            continue
        host_id, instance_id = entry.key
        try:
            target = resolve_fleet_target(host_id, instance_id)
        except RconTargetError as exc:
            results.append(_result(host_id, instance_id, reason=str(exc)))
            continue
        accepted.add(entry.key)
        results.append(_add_target(sid, target))

    for host_id, instance_id in sorted(current - accepted):
        removal = _remove_target(sid, host_id, instance_id)
        if removal is not None:
            results.append(removal)
    return {"targets": results}


@socketio.on("rcon:fleet_join")
@sid_operation_only
@authenticated_only
def handle_fleet_join(data):
    """Treat the submitted targets as this SID's complete fleet selection."""
    return _reconcile(data)


@socketio.on("rcon:fleet_targets")
@sid_operation_only
@authenticated_only
def handle_fleet_targets(data):
    """Reconcile an updated complete fleet selection for this SID."""
    return _reconcile(data)


@socketio.on("rcon:fleet_command")
@sid_operation_only
@authenticated_only
def handle_fleet_command(data):
    """Publish one command per still-authorized and currently eligible target."""
    try:
        run_id, cmd, entries = validate_command_payload(data)
    except RconPayloadError as exc:
        run_id = data.get("run_id") if isinstance(data, dict) else None
        if (
            not isinstance(run_id, str) or not run_id.strip()
            or len(run_id) > MAX_RUN_ID_CHARS
        ):
            run_id = None
        return {"run_id": run_id, "targets": [_result(reason=exc.safe_reason)]}

    sid = request.sid
    results = []
    for entry in entries:
        if entry.key is None:
            results.append(_result(reason=entry.reason))
            continue
        host_id, instance_id = entry.key
        with target_operation(host_id, instance_id):
            room = room_name(host_id, instance_id)
            if (
                not owns(sid, host_id, instance_id, _OWNER)
                or room not in _room_membership(sid, host_id, instance_id, room)
            ):
                results.append(_result(
                    host_id, instance_id, reason="Fleet target is not joined",
                ))
                continue
            try:
                target = resolve_fleet_target(host_id, instance_id)
            except RconTargetError as exc:
                results.append(_result(host_id, instance_id, reason=str(exc)))
                continue
            publication = publish_json(target.channel, command_payload(cmd))
            if publication.ok:
                results.append(_result(host_id, instance_id, state="queued"))
            else:
                results.append(_result(
                    host_id, instance_id, reason=publication.reason,
                ))
    return {"run_id": run_id, "targets": results}


@socketio.on("rcon:fleet_leave")
@sid_operation_only
@authenticated_only
def handle_fleet_leave(_data=None):
    """Release every fleet owner for this SID without disturbing other owners."""
    sid = request.sid
    with fleet_operation(sid):
        left = 0
        failures = []
        for host_id, instance_id in sorted(snapshot_owned(sid, _OWNER)):
            removal = _remove_target(sid, host_id, instance_id)
            if removal is None:
                continue
            if removal["state"] == "removed":
                left += 1
            else:
                failures.append(removal)
        if failures:
            return {"left": left, "targets": failures}
        return {"left": left}
