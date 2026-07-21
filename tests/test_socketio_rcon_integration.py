import json
import logging
import threading
import time

import pytest
from flask_jwt_extended import create_access_token

from ui import db
from ui.models import Host, HostStatus, InstanceStatus, QLInstance


class RecordingRedis:
    def __init__(self, subscribers=1):
        self.subscribers = subscribers
        self.publications = []

    def publish(self, channel, serialized_json):
        self.publications.append((channel, serialized_json))
        return self.subscribers

    def clear(self):
        self.publications.clear()


class BlockingConnectRedis(RecordingRedis):
    def __init__(self):
        super().__init__()
        self.connect_started = threading.Event()
        self.allow_connect = threading.Event()

    def publish(self, channel, serialized_json):
        payload = json.loads(serialized_json)
        if payload["action"] == "connect":
            self.connect_started.set()
            assert self.allow_connect.wait(timeout=2)
        return super().publish(channel, serialized_json)


class BlockingActionRedis(RecordingRedis):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.started = threading.Event()
        self.release = threading.Event()

    def publish(self, channel, serialized_json):
        if json.loads(serialized_json)["action"] == self.action:
            self.started.set()
            assert self.release.wait(timeout=2)
        return super().publish(channel, serialized_json)


@pytest.fixture
def recording_redis():
    from ui import rcon_transport

    client = RecordingRedis()
    rcon_transport._client = client
    try:
        yield client
    finally:
        rcon_transport._client = None


@pytest.fixture
def rcon_target(app):
    with app.app_context():
        host = Host(
            name="SocketIO integration host",
            provider="vultr",
            ip_address="203.0.113.10",
            status=HostStatus.ACTIVE,
        )
        db.session.add(host)
        db.session.flush()
        instance = QLInstance(
            name="SocketIO integration instance",
            hostname="socketio.test",
            port=27960,
            host_id=host.id,
            status=InstanceStatus.RUNNING,
            zmq_rcon_port=28888,
            zmq_rcon_password="server-side-rcon-secret",
            zmq_stats_port=29999,
            zmq_stats_password="server-side-stats-secret",
        )
        db.session.add(instance)
        db.session.commit()
        return host.id, instance.id


@pytest.fixture
def authenticated_socket(app, recording_redis):
    from ui.socketio_events import socketio

    with app.app_context():
        token = create_access_token(identity="socketio-user")
    flask_client = app.test_client()
    flask_client.set_cookie(
        "access_token_cookie", token, domain="test.server",
    )
    client = socketio.test_client(app, flask_test_client=flask_client)
    connected = client.get_received()
    sid = next(
        event["args"][0]["sid"]
        for event in connected
        if event["name"] == "connected"
    )
    yield client, sid
    from ui.rcon_ownership import cleanup_sid

    cleanup_sid(sid)
    if client.is_connected():
        client.disconnect()



def _event_payloads(events, name):
    return [
        event["args"][0]
        for event in events
        if event["name"] == name
    ]



def _rooms_for(sid):
    from ui.socketio_events import socketio

    return set(socketio.server.manager.get_rooms(sid, "/"))



def _assert_publication(recording_redis, expected_channel, expected_payload):
    assert recording_redis.publications == [
        (expected_channel, json.dumps(expected_payload)),
    ]
    channel, serialized_json = recording_redis.publications[0]
    assert channel == expected_channel
    assert isinstance(serialized_json, str)
    assert json.loads(serialized_json) == expected_payload


def _wait_for_sid_state(lifecycle, sid, key, value):
    deadline = time.monotonic() + 2
    while lifecycle.bookkeeping().get(sid, {}).get(key) != value:
        assert time.monotonic() < deadline



def test_authenticated_individual_join_uses_existing_event_room_and_connect_contract(
    app, rcon_target, authenticated_socket, recording_redis,
):
    from ui import rcon_ownership

    host_id, instance_id = rcon_target
    client, sid = authenticated_socket
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})

    room = f"rcon:{host_id}:{instance_id}"
    browser_events = client.get_received()
    assert _event_payloads(browser_events, "rcon:joined") == [{
        "room": room, "host_id": host_id, "instance_id": instance_id,
    }]
    assert room in _rooms_for(sid)
    _assert_publication(recording_redis, f"rcon:cmd:{host_id}:{instance_id}", {
        "action": "connect",
        "ip": "203.0.113.10",
        "rcon_port": 28888,
        "rcon_password": "server-side-rcon-secret",
        "self_host": False,
    })
    serialized_connect = recording_redis.publications[0][1]
    assert "server-side-rcon-secret" in serialized_connect
    assert "server-side-stats-secret" not in serialized_connect
    assert "server-side-rcon-secret" not in repr(browser_events)
    assert "server-side-stats-secret" not in repr(browser_events)
    assert rcon_ownership.owns(sid, host_id, instance_id, "individual")



def test_authenticated_individual_command_preserves_publication_contract(
    app, rcon_target, authenticated_socket, recording_redis,
):
    host_id, instance_id = rcon_target
    client, _ = authenticated_socket
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    client.get_received()
    recording_redis.clear()

    client.emit("rcon:command", {
        "host_id": host_id, "instance_id": instance_id, "cmd": "status",
    })

    _assert_publication(
        recording_redis,
        f"rcon:cmd:{host_id}:{instance_id}",
        {"action": "command", "cmd": "status"},
    )
    assert client.get_received() == []



def test_authentication_is_registered_before_disconnect_and_cancels_join(
    app, rcon_target, authenticated_socket, recording_redis, monkeypatch,
):
    from ui import rcon_ownership, rcon_sid_lifecycle, socketio_events

    host_id, instance_id = rcon_target
    client, sid = authenticated_socket
    decode_started = threading.Event()
    release_decode = threading.Event()
    original_decode = socketio_events.decode_token

    def blocking_decode(token):
        decode_started.set()
        assert release_decode.wait(timeout=2)
        return original_decode(token)

    monkeypatch.setattr(socketio_events, "decode_token", blocking_decode)
    join = threading.Thread(target=lambda: client.emit(
        "rcon:join", {"host_id": host_id, "instance_id": instance_id},
    ))
    cleanup = threading.Thread(target=client.disconnect)
    join.start()
    assert decode_started.wait(timeout=2)
    _wait_for_sid_state(rcon_sid_lifecycle, sid, "active", 1)
    cleanup.start()
    _wait_for_sid_state(rcon_sid_lifecycle, sid, "closing", True)
    assert cleanup.is_alive()
    release_decode.set()
    join.join(timeout=2)
    cleanup.join(timeout=2)

    assert not join.is_alive() and not cleanup.is_alive()
    assert recording_redis.publications == []
    assert not rcon_ownership.owns(sid, host_id, instance_id)
    assert f"rcon:{host_id}:{instance_id}" not in _rooms_for(sid)
    assert rcon_sid_lifecycle.bookkeeping() == {}



def test_invalid_token_disconnects_after_sid_operation_without_deadlock(app):
    from ui import rcon_sid_lifecycle
    from ui.socketio_events import socketio

    flask_client = app.test_client()
    flask_client.set_cookie(
        "access_token_cookie", "invalid-token", domain="test.server",
    )
    client = socketio.test_client(app, flask_test_client=flask_client)
    sid = next(
        event["args"][0]["sid"] for event in client.get_received()
        if event["name"] == "connected"
    )

    client.emit("rcon:join", {"host_id": 1, "instance_id": 1})

    assert not client.is_connected()
    assert sid not in rcon_sid_lifecycle.bookkeeping()



def test_command_holds_target_gate_until_publication_before_leave(
    app, rcon_target, authenticated_socket, recording_redis,
):
    from ui import rcon_transport

    host_id, instance_id = rcon_target
    client, _ = authenticated_socket
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    client.get_received()
    redis = BlockingActionRedis("command")
    rcon_transport._client = redis
    command = threading.Thread(target=lambda: client.emit("rcon:command", {
        "host_id": host_id, "instance_id": instance_id, "cmd": "status",
    }))
    leave = threading.Thread(target=lambda: client.emit(
        "rcon:leave", {"host_id": host_id, "instance_id": instance_id},
    ))
    command.start()
    assert redis.started.wait(timeout=2)
    leave.start()
    redis.release.set()
    command.join(timeout=2)
    leave.join(timeout=2)

    assert not command.is_alive() and not leave.is_alive()
    assert [json.loads(item[1])["action"] for item in redis.publications] == [
        "command", "disconnect",
    ]



def test_leave_holding_target_gate_removes_authority_before_queued_command(
    app, rcon_target, authenticated_socket, recording_redis,
):
    from ui import rcon_transport

    host_id, instance_id = rcon_target
    client, _ = authenticated_socket
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    client.get_received()
    redis = BlockingActionRedis("disconnect")
    rcon_transport._client = redis
    leave = threading.Thread(target=lambda: client.emit(
        "rcon:leave", {"host_id": host_id, "instance_id": instance_id},
    ))
    command = threading.Thread(target=lambda: client.emit("rcon:command", {
        "host_id": host_id, "instance_id": instance_id, "cmd": "status",
    }))
    leave.start()
    assert redis.started.wait(timeout=2)
    command.start()
    redis.release.set()
    leave.join(timeout=2)
    command.join(timeout=2)

    assert not leave.is_alive() and not command.is_alive()
    assert [json.loads(item[1])["action"] for item in redis.publications] == [
        "disconnect",
    ]
    assert _event_payloads(client.get_received(), "rcon:error") == [
        {"error": "Not authorized for this instance"},
    ]



def test_individual_leave_preserves_fleet_owner_then_final_release_disconnects_once(
    app, rcon_target, authenticated_socket, recording_redis,
):
    from ui import rcon_ownership

    host_id, instance_id = rcon_target
    client, sid = authenticated_socket
    room = f"rcon:{host_id}:{instance_id}"
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    client.get_received()
    rcon_ownership.acquire_owner(sid, host_id, instance_id, "fleet")
    recording_redis.clear()

    client.emit("rcon:leave", {"host_id": host_id, "instance_id": instance_id})

    assert _event_payloads(client.get_received(), "rcon:left") == [{"room": room}]
    assert room in _rooms_for(sid)
    assert rcon_ownership.owns(sid, host_id, instance_id, "fleet")
    assert recording_redis.publications == []

    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    client.get_received()
    rcon_ownership.release_owner(sid, host_id, instance_id, "fleet")
    recording_redis.clear()
    client.emit("rcon:leave", {"host_id": host_id, "instance_id": instance_id})

    assert _event_payloads(client.get_received(), "rcon:left") == [{"room": room}]
    assert room not in _rooms_for(sid)
    _assert_publication(
        recording_redis,
        f"rcon:cmd:{host_id}:{instance_id}",
        {"action": "disconnect"},
    )
    assert not rcon_ownership.owns(sid, host_id, instance_id)



def test_socket_disconnect_cleans_owned_targets_and_publishes_final_disconnect(
    app, rcon_target, authenticated_socket, recording_redis,
):
    from ui import rcon_ownership

    host_id, instance_id = rcon_target
    client, sid = authenticated_socket
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    recording_redis.clear()

    client.disconnect()

    _assert_publication(
        recording_redis,
        f"rcon:cmd:{host_id}:{instance_id}",
        {"action": "disconnect"},
    )
    assert not rcon_ownership.owns(sid, host_id, instance_id)
    assert rcon_ownership.cleanup_sid(sid) == []


def test_stale_success_after_disconnect_is_compensated_without_joined_event(
    app, rcon_target, authenticated_socket, recording_redis, monkeypatch,
):
    from ui import rcon_ownership, rcon_transport, socketio_events

    host_id, instance_id = rcon_target
    client, sid = authenticated_socket
    redis = BlockingConnectRedis()
    rcon_transport._client = redis
    emitted = []
    original_emit = socketio_events.emit

    def record_emit(event, *args, **kwargs):
        emitted.append(event)
        return original_emit(event, *args, **kwargs)

    monkeypatch.setattr(socketio_events, "emit", record_emit)
    join = threading.Thread(target=lambda: client.emit(
        "rcon:join", {"host_id": host_id, "instance_id": instance_id},
    ))
    join.start()
    assert redis.connect_started.wait(timeout=2)

    released = rcon_ownership.release_owner(
        sid, host_id, instance_id, "individual",
    )
    assert released.final_owner
    redis.allow_connect.set()
    join.join(timeout=2)

    assert not join.is_alive()
    assert [json.loads(item[1])["action"] for item in redis.publications] == [
        "connect", "disconnect",
    ]
    assert "rcon:joined" not in emitted
    assert not rcon_ownership.owns(sid, host_id, instance_id)
    assert rcon_ownership.cleanup_sid(sid) == []


def test_stale_success_does_not_disconnect_transport_used_by_another_participant(
    app, rcon_target, authenticated_socket, recording_redis,
):
    from ui import rcon_ownership, rcon_transport
    from ui.socketio_events import socketio

    host_id, instance_id = rcon_target
    client, sid = authenticated_socket
    room = f"rcon:{host_id}:{instance_id}"
    redis = BlockingConnectRedis()
    rcon_transport._client = redis
    with app.app_context():
        token = create_access_token(identity="surviving-participant")
    survivor_flask_client = app.test_client()
    survivor_flask_client.set_cookie(
        "access_token_cookie", token, domain="test.server",
    )
    survivor = socketio.test_client(
        app, flask_test_client=survivor_flask_client,
    )
    survivor_sid = next(
        event["args"][0]["sid"]
        for event in survivor.get_received()
        if event["name"] == "connected"
    )
    socketio.server.enter_room(survivor_sid, room, namespace="/")
    rcon_ownership.acquire_owner(
        survivor_sid, host_id, instance_id, "fleet",
    )
    join = threading.Thread(target=lambda: client.emit(
        "rcon:join", {"host_id": host_id, "instance_id": instance_id},
    ))
    try:
        join.start()
        assert redis.connect_started.wait(timeout=2)
        released = rcon_ownership.release_owner(
            sid, host_id, instance_id, "individual",
        )
        assert released.final_owner
        redis.allow_connect.set()
        join.join(timeout=2)

        assert not join.is_alive()
        assert [json.loads(item[1])["action"] for item in redis.publications] == [
            "connect",
        ]
        assert rcon_ownership.owns(
            survivor_sid, host_id, instance_id, "fleet",
        )
        assert not rcon_ownership.owns(sid, host_id, instance_id)
    finally:
        redis.allow_connect.set()
        join.join(timeout=2)
        socketio.server.leave_room(survivor_sid, room, namespace="/")
        rcon_ownership.cleanup_sid(survivor_sid)
        survivor.disconnect()



def test_authenticated_stats_subscribe_and_unsubscribe_keep_existing_contract(
    app, rcon_target, authenticated_socket, recording_redis, caplog,
):
    host_id, instance_id = rcon_target
    client, sid = authenticated_socket
    room = f"rcon:stats:{host_id}:{instance_id}"
    with caplog.at_level(logging.DEBUG):
        client.emit("rcon:subscribe_stats", {
            "host_id": host_id, "instance_id": instance_id,
        })
        assert room in _rooms_for(sid)
        _assert_publication(
            recording_redis,
            f"rcon:cmd:{host_id}:{instance_id}",
            {
                "action": "subscribe_stats",
                "ip": "203.0.113.10",
                "stats_port": 29999,
                "stats_password": "server-side-stats-secret",
            },
        )
        browser_events = client.get_received()
        assert browser_events == []
        assert "server-side-stats-secret" not in repr(browser_events)

        recording_redis.clear()
        client.emit("rcon:unsubscribe_stats", {
            "host_id": host_id, "instance_id": instance_id,
        })

    assert room not in _rooms_for(sid)
    _assert_publication(
        recording_redis,
        f"rcon:cmd:{host_id}:{instance_id}",
        {"action": "unsubscribe_stats"},
    )
    assert client.get_received() == []



def test_stats_subscribe_publication_precedes_queued_target_disconnect(
    app, rcon_target, authenticated_socket, recording_redis, caplog,
):
    from ui import rcon_transport

    host_id, instance_id = rcon_target
    client, _ = authenticated_socket
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    client.get_received()
    redis = BlockingActionRedis("subscribe_stats")
    rcon_transport._client = redis
    subscribe = threading.Thread(target=lambda: client.emit(
        "rcon:subscribe_stats", {
            "host_id": host_id, "instance_id": instance_id,
        },
    ))
    leave = threading.Thread(target=lambda: client.emit(
        "rcon:leave", {"host_id": host_id, "instance_id": instance_id},
    ))
    with caplog.at_level(logging.DEBUG):
        subscribe.start()
        assert redis.started.wait(timeout=2)
        leave.start()
        redis.release.set()
        subscribe.join(timeout=2)
        leave.join(timeout=2)

    assert not subscribe.is_alive() and not leave.is_alive()
    assert [json.loads(item[1])["action"] for item in redis.publications] == [
        "subscribe_stats", "disconnect",
    ]


def test_stats_unsubscribe_publication_precedes_queued_target_disconnect(
    app, rcon_target, authenticated_socket, recording_redis, caplog,
):
    from ui import rcon_transport

    host_id, instance_id = rcon_target
    client, _ = authenticated_socket
    with caplog.at_level(logging.DEBUG):
        client.emit("rcon:subscribe_stats", {
            "host_id": host_id, "instance_id": instance_id,
        })
    recording_redis.clear()
    client.emit("rcon:join", {"host_id": host_id, "instance_id": instance_id})
    client.get_received()
    redis = BlockingActionRedis("unsubscribe_stats")
    rcon_transport._client = redis
    unsubscribe = threading.Thread(target=lambda: client.emit(
        "rcon:unsubscribe_stats", {
            "host_id": host_id, "instance_id": instance_id,
        },
    ))
    leave = threading.Thread(target=lambda: client.emit(
        "rcon:leave", {"host_id": host_id, "instance_id": instance_id},
    ))
    unsubscribe.start()
    assert redis.started.wait(timeout=2)
    leave.start()
    redis.release.set()
    unsubscribe.join(timeout=2)
    leave.join(timeout=2)

    assert not unsubscribe.is_alive() and not leave.is_alive()
    assert [json.loads(item[1])["action"] for item in redis.publications] == [
        "unsubscribe_stats", "disconnect",
    ]
