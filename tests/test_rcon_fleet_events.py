import json
import threading
import time

import pytest
from flask_jwt_extended import create_access_token
import redis as redis_lib

from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance


class RecordingRedis:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.publications = []

    def publish(self, channel, serialized_json):
        self.publications.append((channel, serialized_json))
        return self.results.pop(0) if self.results else 1

    def clear(self):
        self.publications.clear()


class SelectiveRedis(RecordingRedis):
    def __init__(self, fail_instance=None, raise_instance=None):
        super().__init__()
        self.fail_instance = fail_instance
        self.raise_instance = raise_instance

    def publish(self, channel, serialized_json):
        self.publications.append((channel, serialized_json))
        instance_id = int(channel.rsplit(":", 1)[1])
        if instance_id == self.raise_instance:
            raise redis_lib.RedisError("redis://user:password@secret.invalid")
        return 0 if instance_id == self.fail_instance else 1


class BlockingRedis(RecordingRedis):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.started = threading.Event()
        self.release = threading.Event()

    def publish(self, channel, serialized_json):
        payload = json.loads(serialized_json)
        if payload["action"] == self.action:
            self.started.set()
            assert self.release.wait(timeout=2)
        return super().publish(channel, serialized_json)


@pytest.fixture
def fleet_targets(app):
    with app.app_context():
        host = Host(
            name="Fleet host", provider="vultr", ip_address="203.0.113.40",
            status=HostStatus.ACTIVE,
        )
        db.session.add(host)
        db.session.flush()
        instances = []
        for index, status in enumerate((
            InstanceStatus.RUNNING, InstanceStatus.UPDATED, InstanceStatus.STOPPED,
        ), start=1):
            instance = QLInstance(
                name=f"Fleet instance {index}", hostname=f"fleet-{index}.test",
                port=27959 + index, host_id=host.id, status=status,
                zmq_rcon_port=28887 + index,
                zmq_rcon_password=f"fleet-secret-{index}",
            )
            db.session.add(instance)
            instances.append(instance)
        db.session.commit()
        return host.id, tuple(instance.id for instance in instances)


@pytest.fixture
def fleet_socket(app):
    from ui import rcon_transport
    from ui.rcon_ownership import cleanup_sid
    from ui.socketio_events import socketio

    redis = RecordingRedis()
    rcon_transport._client = redis
    with app.app_context():
        token = create_access_token(identity="fleet-user")
    http = app.test_client()
    http.set_cookie("access_token_cookie", token, domain="test.server")
    client = socketio.test_client(app, flask_test_client=http)
    sid = next(
        event["args"][0]["sid"] for event in client.get_received()
        if event["name"] == "connected"
    )
    yield client, sid, redis
    cleanup_sid(sid)
    if client.is_connected():
        client.disconnect()
    rcon_transport._client = None


def _target(host_id, instance_id):
    return {"host_id": host_id, "instance_id": instance_id}


def _decoded(redis):
    return [(channel, json.loads(payload)) for channel, payload in redis.publications]


def _rooms(sid):
    from ui.socketio_events import socketio
    return set(socketio.server.manager.get_rooms(sid, "/"))


def test_join_room_failure_rolls_back_target_and_continues_then_retry_succeeds(
    fleet_targets, fleet_socket, monkeypatch, caplog,
):
    from ui import rcon_fleet_events
    from ui.rcon_ownership import owns

    host_id, (first, second, _) = fleet_targets
    client, sid, redis = fleet_socket
    original_join_room = rcon_fleet_events.join_room
    failed_room = f"rcon:{host_id}:{first}"
    attempts = []

    def selective_join(room):
        attempts.append(room)
        if room == failed_room and attempts.count(room) == 1:
            raise RuntimeError("redis://user:fleet-secret-1@manager.invalid")
        return original_join_room(room)

    monkeypatch.setattr(rcon_fleet_events, "join_room", selective_join)
    targets = [_target(host_id, first), _target(host_id, second)]

    ack = client.emit("rcon:fleet_join", {"targets": targets}, callback=True)

    assert ack == {"targets": [
        {**targets[0], "state": "rejected", "reason": "Unable to join RCON room"},
        {**targets[1], "state": "connecting"},
    ]}
    assert not owns(sid, host_id, first, "fleet")
    assert failed_room not in _rooms(sid)
    assert owns(sid, host_id, second, "fleet")
    assert [payload["action"] for _, payload in _decoded(redis)] == ["connect"]

    retry = client.emit(
        "rcon:fleet_targets", {"targets": [targets[0], targets[1]]}, callback=True,
    )

    assert retry == {"targets": [
        {**targets[0], "state": "connecting"},
        {**targets[1], "state": "connecting"},
    ]}
    assert attempts.count(failed_room) == 2
    assert owns(sid, host_id, first, "fleet")
    assert failed_room in _rooms(sid)
    assert [payload["action"] for _, payload in _decoded(redis)] == [
        "connect", "connect",
    ]
    assert "fleet-secret" not in repr(ack)
    assert "fleet-secret" not in caplog.text


def test_authenticated_fleet_join_reconciles_running_targets_and_rejects_stopped(
    fleet_targets, fleet_socket,
):
    from ui.rcon_ownership import owns

    host_id, (first, second, stopped) = fleet_targets
    client, sid, redis = fleet_socket
    targets = [_target(host_id, item) for item in (first, second, stopped)]

    ack = client.emit("rcon:fleet_join", {"targets": targets}, callback=True)

    assert ack == {"targets": [
        {**targets[0], "state": "connecting"},
        {**targets[1], "state": "connecting"},
        {**targets[2], "state": "rejected", "reason": "Instance is not running"},
    ]}
    assert _rooms(sid) >= {
        f"rcon:{host_id}:{first}", f"rcon:{host_id}:{second}",
    }
    assert owns(sid, host_id, first, "fleet")
    assert owns(sid, host_id, second, "fleet")
    assert not owns(sid, host_id, stopped, "fleet")
    assert _decoded(redis) == [
        (f"rcon:cmd:{host_id}:{first}", {
            "action": "connect", "ip": "203.0.113.40", "rcon_port": 28888,
            "rcon_password": "fleet-secret-1", "self_host": False,
        }),
        (f"rcon:cmd:{host_id}:{second}", {
            "action": "connect", "ip": "203.0.113.40", "rcon_port": 28889,
            "rcon_password": "fleet-secret-2", "self_host": False,
        }),
    ]
    assert "fleet-secret" not in repr(ack)


def _new_socket(app, identity="another-fleet-user"):
    from ui.socketio_events import socketio

    with app.app_context():
        token = create_access_token(identity=identity)
    http = app.test_client()
    http.set_cookie("access_token_cookie", token, domain="test.server")
    client = socketio.test_client(app, flask_test_client=http)
    sid = next(
        event["args"][0]["sid"] for event in client.get_received()
        if event["name"] == "connected"
    )
    return client, sid


def test_desired_set_add_remove_is_idempotent_and_preserves_individual_owner(
    fleet_targets, fleet_socket,
):
    from ui.rcon_ownership import owns

    host_id, (first, second, _) = fleet_targets
    client, sid, redis = fleet_socket
    first_target = _target(host_id, first)
    second_target = _target(host_id, second)
    client.emit("rcon:join", first_target)
    client.get_received()
    redis.clear()

    initial = client.emit(
        "rcon:fleet_join", {"targets": [first_target, first_target]}, callback=True,
    )
    repeated = client.emit(
        "rcon:fleet_targets", {"targets": [first_target]}, callback=True,
    )
    changed = client.emit(
        "rcon:fleet_targets", {"targets": [second_target]}, callback=True,
    )

    assert initial == {"targets": [{**first_target, "state": "connecting"}]}
    assert repeated == initial
    assert changed == {"targets": [
        {**second_target, "state": "connecting"},
        {**first_target, "state": "removed"},
    ]}
    assert [payload["action"] for _, payload in _decoded(redis)] == ["connect"]
    assert owns(sid, host_id, first, "individual")
    assert not owns(sid, host_id, first, "fleet")
    assert owns(sid, host_id, second, "fleet")
    assert f"rcon:{host_id}:{first}" in _rooms(sid)


def test_leave_room_failure_restores_owner_continues_removals_and_retry_repairs(
    fleet_targets, fleet_socket, monkeypatch, caplog,
):
    from ui import rcon_fleet_events
    from ui.rcon_ownership import owns

    host_id, (first, second, _) = fleet_targets
    client, sid, redis = fleet_socket
    targets = [_target(host_id, first), _target(host_id, second)]
    client.emit("rcon:fleet_join", {"targets": targets}, callback=True)
    redis.clear()
    original_leave_room = rcon_fleet_events.leave_room
    failed_room = f"rcon:{host_id}:{first}"
    attempts = []

    def selective_leave(room):
        attempts.append(room)
        if room == failed_room and attempts.count(room) == 1:
            raise RuntimeError("redis://user:fleet-secret-1@manager.invalid")
        return original_leave_room(room)

    monkeypatch.setattr(rcon_fleet_events, "leave_room", selective_leave)

    ack = client.emit("rcon:fleet_targets", {"targets": []}, callback=True)

    assert ack == {"targets": [
        {**targets[0], "state": "rejected", "reason": "Unable to leave RCON room"},
        {**targets[1], "state": "removed"},
    ]}
    assert owns(sid, host_id, first, "fleet")
    assert failed_room in _rooms(sid)
    assert not owns(sid, host_id, second, "fleet")
    assert f"rcon:{host_id}:{second}" not in _rooms(sid)
    assert [channel for channel, _ in _decoded(redis)] == [
        f"rcon:cmd:{host_id}:{second}",
    ]

    retry = client.emit("rcon:fleet_targets", {"targets": []}, callback=True)

    assert retry == {"targets": [{**targets[0], "state": "removed"}]}
    assert not owns(sid, host_id, first, "fleet")
    assert failed_room not in _rooms(sid)
    assert [payload["action"] for _, payload in _decoded(redis)] == [
        "disconnect", "disconnect",
    ]
    assert "fleet-secret" not in repr(ack)
    assert "fleet-secret" not in caplog.text


def test_fleet_leave_counts_only_successful_removals_and_continues(
    fleet_targets, fleet_socket, monkeypatch,
):
    from ui import rcon_fleet_events
    from ui.rcon_ownership import owns

    host_id, (first, second, _) = fleet_targets
    targets = [_target(host_id, first), _target(host_id, second)]
    client, sid, redis = fleet_socket
    client.emit("rcon:fleet_join", {"targets": targets}, callback=True)
    redis.clear()
    original_leave_room = rcon_fleet_events.leave_room
    failed_room = f"rcon:{host_id}:{first}"
    failed_once = False

    def selective_leave(room):
        nonlocal failed_once
        if room == failed_room and not failed_once:
            failed_once = True
            raise RuntimeError("room manager unavailable")
        return original_leave_room(room)

    monkeypatch.setattr(rcon_fleet_events, "leave_room", selective_leave)

    ack = client.emit("rcon:fleet_leave", {}, callback=True)

    assert ack == {
        "left": 1,
        "targets": [{
            **targets[0], "state": "rejected", "reason": "Unable to leave RCON room",
        }],
    }
    assert owns(sid, host_id, first, "fleet")
    assert not owns(sid, host_id, second, "fleet")
    assert [channel for channel, _ in _decoded(redis)] == [
        f"rcon:cmd:{host_id}:{second}",
    ]
    assert client.emit("rcon:fleet_leave", {}, callback=True) == {"left": 1}
    assert not owns(sid, host_id, first, "fleet")


def test_other_sid_survives_leave_and_final_participant_disconnects_once(
    app, fleet_targets, fleet_socket,
):
    from ui.rcon_ownership import cleanup_sid, owns

    host_id, (first, _, _) = fleet_targets
    target = _target(host_id, first)
    client, sid, redis = fleet_socket
    other, other_sid = _new_socket(app)
    try:
        client.emit("rcon:fleet_join", {"targets": [target]}, callback=True)
        other.emit("rcon:fleet_join", {"targets": [target]}, callback=True)
        redis.clear()

        assert client.emit("rcon:fleet_leave", {}, callback=True) == {"left": 1}
        assert owns(other_sid, host_id, first, "fleet")
        assert _decoded(redis) == []
        assert other.emit("rcon:fleet_leave", None, callback=True) == {"left": 1}

        assert [payload for _, payload in _decoded(redis)] == [
            {"action": "disconnect"},
        ]
        assert not owns(sid, host_id, first, "fleet")
        assert not owns(other_sid, host_id, first, "fleet")
    finally:
        cleanup_sid(other_sid)
        if other.is_connected():
            other.disconnect()


@pytest.mark.parametrize("subscribers", [0, "exception"])
def test_failed_connect_rolls_back_and_explicit_recheck_succeeds(
    fleet_targets, fleet_socket, subscribers,
):
    from ui import rcon_transport
    from ui.rcon_ownership import owns

    host_id, (first, _, _) = fleet_targets
    client, sid, _ = fleet_socket
    failed = SelectiveRedis(
        fail_instance=first if subscribers == 0 else None,
        raise_instance=first if subscribers == "exception" else None,
    )
    rcon_transport._client = failed
    ack = client.emit(
        "rcon:fleet_join", {"targets": [_target(host_id, first)]}, callback=True,
    )

    assert ack["targets"][0]["state"] == "rejected"
    assert "password@" not in repr(ack).lower()
    assert not owns(sid, host_id, first, "fleet")
    assert f"rcon:{host_id}:{first}" not in _rooms(sid)

    recovered = RecordingRedis()
    rcon_transport._client = recovered
    retry = client.emit(
        "rcon:fleet_targets", {"targets": [_target(host_id, first)]}, callback=True,
    )
    assert retry == {"targets": [
        {**_target(host_id, first), "state": "connecting"},
    ]}
    assert [payload["action"] for _, payload in _decoded(recovered)] == ["connect"]


def test_failed_connect_and_failed_compensating_leave_retains_recoverable_owner(
    fleet_targets, fleet_socket, monkeypatch, caplog,
):
    from ui import rcon_fleet_events, rcon_transport
    from ui.rcon_ownership import owns

    host_id, (first, _, _) = fleet_targets
    target = _target(host_id, first)
    room = f"rcon:{host_id}:{first}"
    client, sid, _ = fleet_socket
    original_leave_room = rcon_fleet_events.leave_room
    leave_attempts = []

    def fail_first_leave(requested_room):
        leave_attempts.append(requested_room)
        if len(leave_attempts) == 1:
            raise RuntimeError("redis://user:fleet-secret-1@manager.invalid")
        return original_leave_room(requested_room)

    monkeypatch.setattr(rcon_fleet_events, "leave_room", fail_first_leave)
    rcon_transport._client = SelectiveRedis(fail_instance=first)

    failed = client.emit(
        "rcon:fleet_join", {"targets": [target]}, callback=True,
    )

    assert failed == {"targets": [{
        **target, "state": "rejected",
        "reason": "RCON service unavailable; RCON room cleanup pending",
    }]}
    assert owns(sid, host_id, first, "fleet")
    assert room in _rooms(sid)

    recovered = RecordingRedis()
    rcon_transport._client = recovered
    retry = client.emit(
        "rcon:fleet_targets", {"targets": [target]}, callback=True,
    )
    removed = client.emit(
        "rcon:fleet_targets", {"targets": []}, callback=True,
    )

    assert retry == {"targets": [{**target, "state": "connecting"}]}
    assert removed == {"targets": [{**target, "state": "removed"}]}
    assert not owns(sid, host_id, first, "fleet")
    assert room not in _rooms(sid)
    assert [payload["action"] for _, payload in _decoded(recovered)] == [
        "connect", "disconnect",
    ]
    assert "fleet-secret" not in repr(failed)
    assert "fleet-secret" not in caplog.text


def test_room_membership_manager_failure_warns_and_rejects_without_publication(
    fleet_targets, fleet_socket, monkeypatch, caplog,
):
    from ui import rcon_fleet_events

    host_id, (first, _, _) = fleet_targets
    target = _target(host_id, first)
    client, _, redis = fleet_socket
    client.emit("rcon:fleet_join", {"targets": [target]}, callback=True)
    redis.clear()

    def fail_membership(**_kwargs):
        raise RuntimeError("redis://user:fleet-secret-1@manager.invalid")

    monkeypatch.setattr(rcon_fleet_events, "rooms", fail_membership)

    ack = client.emit("rcon:fleet_command", {
        "run_id": "manager-failure", "cmd": "status", "targets": [target],
    }, callback=True)

    assert ack == {"run_id": "manager-failure", "targets": [{
        **target, "state": "rejected", "reason": "Fleet target is not joined",
    }]}
    assert redis.publications == []
    assert "Unable to inspect RCON room membership" in caplog.text
    assert f"host_id={host_id}" in caplog.text
    assert f"instance_id={first}" in caplog.text
    assert f"room=rcon:{host_id}:{first}" in caplog.text
    assert "fleet-secret" not in caplog.text
    assert "fleet-secret" not in repr(ack)


def test_fleet_command_fans_out_and_isolates_rejections_and_redis_failure(
    fleet_targets, fleet_socket,
):
    from ui import rcon_transport

    host_id, (first, second, stopped) = fleet_targets
    client, _, _ = fleet_socket
    joined = [_target(host_id, first), _target(host_id, second)]
    client.emit("rcon:fleet_join", {"targets": joined}, callback=True)
    redis = SelectiveRedis(fail_instance=second)
    rcon_transport._client = redis
    missing = _target(host_id, 99999)
    mismatched = _target(host_id + 1, first)

    ack = client.emit("rcon:fleet_command", {
        "run_id": "run-42", "cmd": " status ",
        "targets": [joined[0], joined[1], _target(host_id, stopped), missing,
                    mismatched, joined[0], "bad"],
    }, callback=True)

    assert ack == {"run_id": "run-42", "targets": [
        {**joined[0], "state": "queued"},
        {**joined[1], "state": "rejected", "reason": "RCON service unavailable"},
        {**_target(host_id, stopped), "state": "rejected",
         "reason": "Fleet target is not joined"},
        {**missing, "state": "rejected", "reason": "Fleet target is not joined"},
        {**mismatched, "state": "rejected", "reason": "Fleet target is not joined"},
        {"state": "rejected", "reason": "Target must be an object"},
    ]}
    assert _decoded(redis) == [
        (f"rcon:cmd:{host_id}:{first}", {"action": "command", "cmd": "status"}),
        (f"rcon:cmd:{host_id}:{second}", {"action": "command", "cmd": "status"}),
    ]


@pytest.mark.parametrize("payload,reason", [
    (None, "Payload must be an object"),
    (7, "Payload must be an object"),
    ({"targets": None}, "Targets must be a list"),
    ({"targets": [{}] * 101}, "Too many targets"),
])
def test_fleet_join_rejects_invalid_top_level_payloads(fleet_socket, payload, reason):
    client, _, redis = fleet_socket
    assert client.emit("rcon:fleet_join", payload, callback=True) == {
        "targets": [{"state": "rejected", "reason": reason}],
    }
    assert redis.publications == []


@pytest.mark.parametrize("payload,reason", [
    (None, "Payload must be an object"),
    ({"run_id": "", "cmd": "status", "targets": []}, "Invalid run_id"),
    ({"run_id": "x" * 129, "cmd": "status", "targets": []}, "Invalid run_id"),
    ({"run_id": "r", "cmd": "", "targets": []}, "Invalid command"),
    ({"run_id": "r", "cmd": "x" * 4097, "targets": []}, "Invalid command"),
    ({"run_id": "r", "cmd": "\ud800", "targets": []}, "Invalid command"),
    ({"run_id": "r", "cmd": "status", "targets": [{}] * 101}, "Too many targets"),
])
def test_fleet_command_rejects_invalid_boundaries(fleet_socket, payload, reason):
    client, _, redis = fleet_socket
    ack = client.emit("rcon:fleet_command", payload, callback=True)
    assert ack["targets"] == [{"state": "rejected", "reason": reason}]
    assert redis.publications == []


@pytest.mark.parametrize("bad_id", [None, True, False, 0, -1, "1"])
def test_malformed_ids_are_safe_per_entry_rejections(fleet_socket, bad_id):
    client, _, redis = fleet_socket
    ack = client.emit("rcon:fleet_join", {"targets": [
        {"host_id": bad_id, "instance_id": 1},
    ]}, callback=True)
    assert ack == {"targets": [{
        "state": "rejected", "reason": "Target IDs must be positive integers",
    }]}
    assert redis.publications == []


def test_command_rechecks_current_status_and_desired_set_removes_ineligible_owner(
    app, fleet_targets, fleet_socket,
):
    from ui.models import QLInstance
    from ui.rcon_ownership import owns

    host_id, (first, _, _) = fleet_targets
    target = _target(host_id, first)
    client, sid, redis = fleet_socket
    client.emit("rcon:fleet_join", {"targets": [target]}, callback=True)
    redis.clear()
    with app.app_context():
        instance = db.session.get(QLInstance, first)
        instance.status = InstanceStatus.STOPPED
        db.session.commit()

    command_ack = client.emit("rcon:fleet_command", {
        "run_id": "recheck", "cmd": "status", "targets": [target],
    }, callback=True)
    desired_ack = client.emit(
        "rcon:fleet_targets", {"targets": [target]}, callback=True,
    )

    assert command_ack == {"run_id": "recheck", "targets": [{
        **target, "state": "rejected", "reason": "Instance is not running",
    }]}
    assert desired_ack == {"targets": [
        {**target, "state": "rejected", "reason": "Instance is not running"},
        {**target, "state": "removed"},
    ]}
    assert not owns(sid, host_id, first, "fleet")
    assert [payload["action"] for _, payload in _decoded(redis)] == ["disconnect"]


def test_command_and_concurrent_leave_are_serialized_without_command_after_disconnect(
    fleet_targets, fleet_socket,
):
    from ui import rcon_transport

    host_id, (first, _, _) = fleet_targets
    target = _target(host_id, first)
    client, _, _ = fleet_socket
    client.emit("rcon:fleet_join", {"targets": [target]}, callback=True)
    client.get_received()
    redis = BlockingRedis("command")
    rcon_transport._client = redis
    command_ack = []
    leave_ack = []
    command = threading.Thread(target=lambda: command_ack.append(client.emit(
        "rcon:fleet_command", {
            "run_id": "ordered", "cmd": "status", "targets": [target],
        }, callback=True,
    )))
    leave = threading.Thread(target=lambda: leave_ack.append(client.emit(
        "rcon:fleet_leave", {}, callback=True,
    )))
    command.start()
    assert redis.started.wait(timeout=2)
    leave.start()
    redis.release.set()
    command.join(timeout=2)
    leave.join(timeout=2)

    assert not command.is_alive() and not leave.is_alive()
    assert command_ack[0]["targets"][0]["state"] == "queued"
    assert leave_ack == [{"left": 1}]
    assert [payload["action"] for _, payload in _decoded(redis)] == [
        "command", "disconnect",
    ]


def test_leave_before_concurrent_command_rejects_without_post_disconnect_publish(
    fleet_targets, fleet_socket,
):
    from ui import rcon_transport

    host_id, (first, _, _) = fleet_targets
    target = _target(host_id, first)
    client, _, _ = fleet_socket
    client.emit("rcon:fleet_join", {"targets": [target]}, callback=True)
    redis = BlockingRedis("disconnect")
    rcon_transport._client = redis
    leave_ack = []
    command_ack = []
    leave = threading.Thread(target=lambda: leave_ack.append(client.emit(
        "rcon:fleet_leave", {}, callback=True,
    )))
    command = threading.Thread(target=lambda: command_ack.append(client.emit(
        "rcon:fleet_command", {
            "run_id": "after-leave", "cmd": "status", "targets": [target],
        }, callback=True,
    )))
    leave.start()
    assert redis.started.wait(timeout=2)
    command.start()
    redis.release.set()
    leave.join(timeout=2)
    command.join(timeout=2)

    assert not leave.is_alive() and not command.is_alive()
    assert leave_ack == [{"left": 1}]
    assert command_ack == [{"run_id": "after-leave", "targets": [{
        **target, "state": "rejected", "reason": "Fleet target is not joined",
    }]}]
    assert [payload["action"] for _, payload in _decoded(redis)] == ["disconnect"]


def test_concurrent_desired_sets_finish_as_complete_fifo_transactions(
    fleet_targets, fleet_socket,
):
    from ui import rcon_fleet_gate, rcon_transport
    from ui.rcon_ownership import snapshot_owned

    host_id, (initial, first, _) = fleet_targets
    client, sid, _ = fleet_socket
    initial_target = _target(host_id, initial)
    first_target = _target(host_id, first)
    second_target = initial_target
    client.emit("rcon:fleet_join", {"targets": [initial_target]}, callback=True)
    redis = BlockingRedis("connect")
    rcon_transport._client = redis
    first_ack = []
    second_ack = []
    first_request = threading.Thread(target=lambda: first_ack.append(client.emit(
        "rcon:fleet_targets", {"targets": [first_target]}, callback=True,
    )))
    second_request = threading.Thread(target=lambda: second_ack.append(client.emit(
        "rcon:fleet_targets", {"targets": [second_target]}, callback=True,
    )))

    first_request.start()
    assert redis.started.wait(timeout=2)
    second_request.start()
    _wait_for_fleet_tickets(rcon_fleet_gate, sid, 2)
    assert second_request.is_alive()
    redis.release.set()
    first_request.join(timeout=2)
    second_request.join(timeout=2)

    assert not first_request.is_alive() and not second_request.is_alive()
    assert first_ack == [{"targets": [
        {**first_target, "state": "connecting"},
        {**initial_target, "state": "removed"},
    ]}]
    assert second_ack == [{"targets": [
        {**second_target, "state": "connecting"},
        {**first_target, "state": "removed"},
    ]}]
    assert set(snapshot_owned(sid, "fleet")) == {(host_id, initial)}
    assert {room for room in _rooms(sid) if room.startswith("rcon:")} == {
        f"rcon:{host_id}:{initial}",
    }
    assert rcon_fleet_gate.operation_bookkeeping() == {}


def test_concurrent_reconcile_then_leave_has_no_owner_or_room_leaks(
    fleet_targets, fleet_socket,
):
    from ui import rcon_fleet_gate, rcon_transport
    from ui.rcon_ownership import snapshot_owned

    host_id, (initial, desired, _) = fleet_targets
    client, sid, _ = fleet_socket
    initial_target = _target(host_id, initial)
    desired_target = _target(host_id, desired)
    client.emit("rcon:fleet_join", {"targets": [initial_target]}, callback=True)
    redis = BlockingRedis("connect")
    rcon_transport._client = redis
    reconcile_ack = []
    leave_ack = []
    reconcile = threading.Thread(target=lambda: reconcile_ack.append(client.emit(
        "rcon:fleet_targets", {"targets": [desired_target]}, callback=True,
    )))
    leave = threading.Thread(target=lambda: leave_ack.append(client.emit(
        "rcon:fleet_leave", {}, callback=True,
    )))

    reconcile.start()
    assert redis.started.wait(timeout=2)
    leave.start()
    _wait_for_fleet_tickets(rcon_fleet_gate, sid, 2)
    assert leave.is_alive()
    redis.release.set()
    reconcile.join(timeout=2)
    leave.join(timeout=2)

    assert not reconcile.is_alive() and not leave.is_alive()
    assert reconcile_ack == [{"targets": [
        {**desired_target, "state": "connecting"},
        {**initial_target, "state": "removed"},
    ]}]
    assert leave_ack == [{"left": 1}]
    assert snapshot_owned(sid, "fleet") == {}
    assert not {room for room in _rooms(sid) if room.startswith("rcon:")}
    assert [payload["action"] for _, payload in _decoded(redis)] == [
        "connect", "disconnect", "disconnect",
    ]
    assert rcon_fleet_gate.operation_bookkeeping() == {}


def test_socket_disconnect_cleans_fleet_ownership_without_stats_publications(
    fleet_targets, fleet_socket,
):
    from ui.rcon_ownership import owns

    host_id, (first, _, _) = fleet_targets
    client, sid, redis = fleet_socket
    client.emit(
        "rcon:fleet_join", {"targets": [_target(host_id, first)]}, callback=True,
    )
    redis.clear()

    client.disconnect()

    assert not owns(sid, host_id, first, "fleet")
    assert [payload["action"] for _, payload in _decoded(redis)] == ["disconnect"]
    assert all("stats" not in channel for channel, _ in redis.publications)


def test_unauthenticated_fleet_event_disconnects_without_publication(app, fleet_targets):
    from ui import rcon_transport
    from ui.socketio_events import socketio

    redis = RecordingRedis()
    rcon_transport._client = redis
    client = socketio.test_client(app, flask_test_client=app.test_client())
    client.get_received()
    host_id, (first, _, _) = fleet_targets
    client.emit("rcon:fleet_join", {"targets": [_target(host_id, first)]})
    assert not client.is_connected()
    assert redis.publications == []
    rcon_transport._client = None


def _wait_for_fleet_tickets(gate, sid, count):
    deadline = time.monotonic() + 2
    while gate.operation_bookkeeping().get(sid, 0) < count:
        assert time.monotonic() < deadline
