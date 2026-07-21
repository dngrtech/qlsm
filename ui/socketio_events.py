"""Flask-SocketIO handlers bridging RCON browser events to Redis."""

import logging
from functools import wraps

from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room, rooms

from ui.rcon_ownership import (
    ConnectCompletionStatus,
    acquire_owner,
    begin_connect,
    cleanup_sid_residual,
    cleanup_target,
    complete_connect,
    owns,
    release_owner,
    snapshot_owned,
)
from ui.rcon_sid_lifecycle import closing as closing_sid
from ui.rcon_sid_lifecycle import is_closing as sid_is_closing
from ui.rcon_sid_lifecycle import operation as sid_operation
from ui.rcon_target_gate import operation as target_operation
from ui.rcon_transport import (
    RconTargetError,
    command_channel,
    command_payload,
    connect_payload,
    disconnect_payload,
    publish_json,
    rcon_target_for_host,
    resolve_fleet_target,
)
from ui.task_logic.self_host_network import resolve_self_host_management_target

log = logging.getLogger(__name__)
socketio = SocketIO()


def _stats_stream_enabled() -> bool:
    """Allow live stats stream only when running at DEBUG log level."""
    return logging.getLogger().isEnabledFor(logging.DEBUG)


def _rcon_target_for_host(host) -> str | None:
    """Compatibility wrapper for the extracted shared target resolver."""
    return rcon_target_for_host(host, resolve_self_host_management_target)


def _emit_rcon_error(error: str | None, host_id, instance_id) -> None:
    emit("rcon:error", {
        "error": error,
        "host_id": host_id,
        "instance_id": instance_id,
    })


def _publish_or_error(
    channel: str, payload: dict, host_id, instance_id,
) -> bool:
    result = publish_json(channel, payload)
    if not result.ok:
        _emit_rcon_error(result.reason, host_id, instance_id)
    return result.ok


def authenticated_only(f):
    """Signal JWT rejection so the outer SID wrapper can disconnect safely."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        auth = request.cookies.get("access_token_cookie")
        if not auth:
            log.warning("SocketIO connection rejected: No auth cookie")
            raise _AuthenticationRejected
        try:
            decode_token(auth)
        except Exception as exc:
            log.warning("SocketIO connection rejected: Invalid token - %s", exc)
            raise _AuthenticationRejected from None
        if sid_is_closing(request.sid):
            return None
        return f(*args, **kwargs)
    return wrapped


class _AuthenticationRejected(Exception):
    """Private control flow consumed by ``sid_operation_only``."""


def sid_operation_only(f):
    """Register before authentication and defer auth disconnect until release."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        rejected = False
        with sid_operation(request.sid) as accepted:
            if not accepted:
                return None
            try:
                return f(*args, **kwargs)
            except _AuthenticationRejected:
                rejected = True
        if rejected:
            disconnect()
        return None
    return wrapped


@socketio.on("connect")
def handle_connect():
    emit("connected", {"status": "ok", "sid": request.sid})


@socketio.on("disconnect")
def handle_disconnect():
    """Drain SID operations, then clean ownership through target gates."""
    sid = request.sid
    with closing_sid(sid) as should_cleanup:
        if not should_cleanup:
            return
        for host_id, instance_id in snapshot_owned(sid):
            with target_operation(host_id, instance_id):
                transition = cleanup_target(sid, host_id, instance_id)
                if not transition.changed:
                    continue
                room = f"rcon:{host_id}:{instance_id}"
                leave_room(room)
                if _participant_count(room, excluding_sid=sid) == 0:
                    publish_json(
                        command_channel(host_id, instance_id),
                        disconnect_payload(),
                    )
        cleanup_sid_residual(sid)


@socketio.on("rcon:join")
@sid_operation_only
@authenticated_only
def handle_rcon_join(data):
    host_id = data.get("host_id")
    instance_id = data.get("instance_id")
    if not all([host_id, instance_id]):
        _emit_rcon_error(
            "Missing required fields (host_id, instance_id)", host_id, instance_id,
        )
        return

    try:
        target = resolve_fleet_target(host_id, instance_id)
    except RconTargetError as exc:
        _emit_rcon_error(str(exc), host_id, instance_id)
        return

    with target_operation(host_id, instance_id):
        acquisition = acquire_owner(
            request.sid, host_id, instance_id, "individual",
        )
        if acquisition.first_owner:
            join_room(target.room)

        attempt = begin_connect(acquisition)
        if attempt.should_publish:
            result = publish_json(target.channel, connect_payload(target))
            completion = complete_connect(attempt, succeeded=result.ok)
            if completion.status is ConnectCompletionStatus.STALE:
                if result.ok and _participant_count(
                    target.room, excluding_sid=request.sid,
                ) == 0:
                    publish_json(target.channel, disconnect_payload())
                return
            if not result.ok:
                rollback = completion.rollback
                if rollback is not None and not rollback.owners:
                    leave_room(target.room)
                _emit_rcon_error(result.reason, host_id, instance_id)
                return
            if not completion.claimant_active:
                return
        elif not attempt.established:
            _emit_rcon_error(
                "RCON connection was not established", host_id, instance_id,
            )
            return

        emit("rcon:joined", {
            "room": target.room,
            "host_id": host_id,
            "instance_id": instance_id,
        })


@socketio.on("rcon:leave")
@sid_operation_only
@authenticated_only
def handle_rcon_leave(data):
    host_id = data.get("host_id")
    instance_id = data.get("instance_id")
    if host_id is None or instance_id is None:
        return

    with target_operation(host_id, instance_id):
        room = f"rcon:{host_id}:{instance_id}"
        if room not in rooms(sid=request.sid, namespace="/"):
            return
        if not owns(request.sid, host_id, instance_id, "individual"):
            return

        transition = release_owner(
            request.sid, host_id, instance_id, "individual",
        )
        if transition.final_owner:
            leave_room(room)
            if _participant_count(room) == 0:
                _publish_or_error(
                    command_channel(host_id, instance_id), disconnect_payload(),
                    host_id, instance_id,
                )
        emit("rcon:left", {"room": room})


@socketio.on("rcon:command")
@sid_operation_only
@authenticated_only
def handle_rcon_command(data):
    host_id = data.get("host_id")
    instance_id = data.get("instance_id")
    cmd = data.get("cmd")
    if not all([host_id, instance_id, cmd]):
        _emit_rcon_error("Missing required fields", host_id, instance_id)
        return

    room = f"rcon:{host_id}:{instance_id}"
    with target_operation(host_id, instance_id):
        authorized = (
            owns(request.sid, host_id, instance_id, "individual")
            and room in rooms(sid=request.sid, namespace="/")
        )
        if not authorized:
            _emit_rcon_error(
                "Not authorized for this instance", host_id, instance_id,
            )
            return
        _publish_or_error(
            command_channel(host_id, instance_id), command_payload(cmd),
            host_id, instance_id,
        )


@socketio.on("rcon:subscribe_stats")
@sid_operation_only
@authenticated_only
def handle_subscribe_stats(data):
    from .models import QLInstance

    host_id = data.get("host_id")
    instance_id = data.get("instance_id")
    if not _stats_stream_enabled():
        return

    with target_operation(host_id, instance_id):
        instance = QLInstance.query.get(instance_id)
        if not instance or instance.host_id != host_id:
            _emit_rcon_error(
                f"Instance {instance_id} not found on host {host_id}",
                host_id,
                instance_id,
            )
            return

        stats_port = instance.zmq_stats_port
        if not stats_port:
            return
        join_room(f"rcon:stats:{host_id}:{instance_id}")
        _publish_or_error(command_channel(host_id, instance_id), {
            "action": "subscribe_stats",
            "ip": _rcon_target_for_host(instance.host),
            "stats_port": stats_port,
            "stats_password": instance.zmq_stats_password,
        }, host_id, instance_id)


@socketio.on("rcon:unsubscribe_stats")
@sid_operation_only
@authenticated_only
def handle_unsubscribe_stats(data):
    host_id = data.get("host_id")
    instance_id = data.get("instance_id")
    if host_id is None or instance_id is None:
        return

    room = f"rcon:stats:{host_id}:{instance_id}"
    with target_operation(host_id, instance_id):
        if room not in rooms(sid=request.sid, namespace="/"):
            return
        leave_room(room)
        _publish_or_error(command_channel(host_id, instance_id), {
            "action": "unsubscribe_stats",
        }, host_id, instance_id)


def _participant_count(room: str, excluding_sid: str | None = None) -> int:
    """Fail closed when room membership cannot be determined."""
    try:
        participants = list(socketio.server.manager.get_participants("/", room))
        if excluding_sid is not None:
            participants = [
                participant for participant in participants
                if _participant_sid(participant) != excluding_sid
            ]
        return len(participants)
    except Exception as exc:
        log.warning("Failed to check RCON room participants: %s", exc)
        return 1


def _participant_sid(participant) -> str:
    if isinstance(participant, (tuple, list)) and participant:
        return participant[0]
    return participant


# Register fleet handlers after the shared decorators and room helpers exist.
# The import intentionally lives here because both modules use the same SocketIO
# instance and default namespace.
from ui import rcon_fleet_events as _rcon_fleet_events  # noqa: E402,F401
