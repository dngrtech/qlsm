from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import redis

from ui import db
from ui.models import Host, InstanceStatus, QLInstance


def add_target(
    *, status=InstanceStatus.RUNNING, port=28888, password="secret",
    provider="vultr", address="203.0.113.10",
):
    host = Host(name=f"Host-{id(object())}", provider=provider, ip_address=address)
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(
        name=f"Instance-{host.id}", hostname=f"Instance-{host.id}", port=27960,
        host_id=host.id, status=status, zmq_rcon_port=port,
        zmq_rcon_password=password,
    )
    db.session.add(instance)
    db.session.commit()
    return host, instance


@pytest.mark.parametrize("status", [InstanceStatus.RUNNING, InstanceStatus.UPDATED])
def test_resolve_fleet_target_returns_server_side_credentials(app, status):
    from ui.rcon_transport import resolve_fleet_target

    with app.app_context():
        host, instance = add_target(status=status)
        resolved = resolve_fleet_target(host.id, instance.id)

        assert resolved.ip == "203.0.113.10"
        assert resolved.rcon_port == 28888
        assert resolved.rcon_password == "secret"
        assert resolved.room == f"rcon:{host.id}:{instance.id}"
        assert resolved.channel.endswith(f":cmd:{host.id}:{instance.id}")
        assert resolved.self_host is False


def test_resolve_fleet_target_uses_self_host_management_address(app, monkeypatch):
    from ui import rcon_transport

    monkeypatch.setattr(
        rcon_transport, "resolve_self_host_management_target",
        lambda: "host.docker.internal",
    )
    with app.app_context():
        host, instance = add_target(provider="self", address="127.0.0.1")
        resolved = rcon_transport.resolve_fleet_target(host.id, instance.id)

    assert resolved.ip == "host.docker.internal"
    assert resolved.self_host is True


@pytest.mark.parametrize(
    ("status", "port", "password", "address", "reason"),
    [
        (InstanceStatus.STOPPED, 28888, "secret", "203.0.113.10", "Instance is not running"),
        (InstanceStatus.RUNNING, None, "secret", "203.0.113.10", "RCON not configured"),
        (InstanceStatus.RUNNING, 28888, None, "203.0.113.10", "RCON not configured"),
        (InstanceStatus.RUNNING, 28888, "secret", None, "Host address unavailable"),
    ],
)
def test_resolve_fleet_target_rejects_ineligible_targets(
    app, status, port, password, address, reason,
):
    from ui.rcon_transport import RconTargetError, resolve_fleet_target

    with app.app_context():
        host, instance = add_target(
            status=status, port=port, password=password, address=address,
        )
        with pytest.raises(RconTargetError, match=reason) as exc_info:
            resolve_fleet_target(host.id, instance.id)

    assert "secret" not in str(exc_info.value)


def test_resolve_fleet_target_rejects_host_instance_mismatch(app):
    from ui.rcon_transport import RconTargetError, resolve_fleet_target

    with app.app_context():
        host, instance = add_target()
        other = Host(name="Other", provider="vultr", ip_address="192.0.2.1")
        db.session.add(other)
        db.session.commit()
        with pytest.raises(RconTargetError, match="Instance not found on host"):
            resolve_fleet_target(other.id, instance.id)


def test_target_for_host_keeps_existing_resolution_contract(monkeypatch):
    from ui import rcon_transport

    monkeypatch.setattr(
        rcon_transport, "resolve_self_host_management_target", lambda: "management-host",
    )
    assert rcon_transport.rcon_target_for_host(SimpleNamespace(provider="self")) == "management-host"
    assert rcon_transport.rcon_target_for_host(
        SimpleNamespace(provider="vultr", ip_address="192.0.2.4")
    ) == "192.0.2.4"


def test_publish_json_reports_success_and_serializes(monkeypatch):
    from ui import rcon_transport

    fake = Mock()
    fake.publish.return_value = 2
    monkeypatch.setattr(rcon_transport, "get_redis_client", lambda: fake)
    result = rcon_transport.publish_json("rcon:cmd:1:2", {"action": "command", "cmd": "status"})

    assert result.ok is True
    assert result.subscribers == 2
    fake.publish.assert_called_once_with(
        "rcon:cmd:1:2", '{"action": "command", "cmd": "status"}',
    )


def test_publish_json_reports_zero_subscribers(monkeypatch):
    from ui import rcon_transport

    fake = Mock()
    fake.publish.return_value = 0
    monkeypatch.setattr(rcon_transport, "get_redis_client", lambda: fake)
    result = rcon_transport.publish_json("rcon:cmd:1:2", {"action": "disconnect"})

    assert result.ok is False
    assert result.subscribers == 0
    assert result.reason == "RCON service unavailable"


def test_publish_json_resets_stale_client_on_redis_error(monkeypatch, caplog):
    from ui import rcon_transport

    fake = Mock()
    fake.publish.side_effect = redis.RedisError("redis password=do-not-log")
    monkeypatch.setattr(rcon_transport, "_client", fake)
    result = rcon_transport.publish_json("rcon:cmd:1:2", {"action": "disconnect"})

    assert result.ok is False
    assert result.reason == "Communication service temporarily unavailable"
    assert rcon_transport._client is None
    assert "do-not-log" not in caplog.text


def test_payload_builders_match_existing_service_contract():
    from ui.rcon_transport import (
        ResolvedRconTarget, command_payload, connect_payload, disconnect_payload,
    )

    target = ResolvedRconTarget(1, 2, "host", 28888, "secret", True)
    assert connect_payload(target) == {
        "action": "connect", "ip": "host", "rcon_port": 28888,
        "rcon_password": "secret", "self_host": True,
    }
    assert command_payload("status") == {"action": "command", "cmd": "status"}
    assert disconnect_payload() == {"action": "disconnect"}


@pytest.mark.parametrize("payload", [None, 1, "bad", [], True])
def test_join_payload_requires_object(payload):
    from ui.rcon_transport import RconPayloadError, validate_join_payload

    with pytest.raises(RconPayloadError, match="Payload must be an object") as exc_info:
        validate_join_payload(payload)
    assert len(exc_info.value.safe_reason) <= 128


def test_join_payload_requires_target_list_and_caps_size():
    from ui.rcon_transport import RconPayloadError, validate_join_payload

    with pytest.raises(RconPayloadError, match="Targets must be a list"):
        validate_join_payload({"targets": None})
    accepted = validate_join_payload({
        "targets": [
            {"host_id": 1, "instance_id": instance_id}
            for instance_id in range(1, 101)
        ],
    })
    assert len(accepted) == 100
    with pytest.raises(RconPayloadError, match="Too many targets"):
        validate_join_payload({"targets": [{"host_id": 1, "instance_id": 1}] * 101})


def test_payload_validators_reject_unexpected_top_level_fields_safely():
    from ui.rcon_transport import RconPayloadError, validate_command_payload, validate_join_payload

    with pytest.raises(RconPayloadError, match="Unexpected payload fields"):
        validate_join_payload({"targets": [], "password": "must-not-appear"})
    with pytest.raises(RconPayloadError, match="Unexpected payload fields") as exc_info:
        validate_command_payload({
            "run_id": "run", "cmd": "status", "targets": [],
            "credential": "must-not-appear",
        })
    assert "must-not-appear" not in exc_info.value.safe_reason


def test_join_payload_preserves_order_dedupes_valid_and_safely_marks_malformed():
    from ui.rcon_transport import validate_join_payload

    entries = validate_join_payload({"targets": [
        {"host_id": 2, "instance_id": 3},
        None,
        {"host_id": True, "instance_id": 3},
        {"host_id": 2, "instance_id": 3},
        {"host_id": 4, "instance_id": 5},
    ]})

    assert [entry.key for entry in entries] == [(2, 3), None, None, (4, 5)]
    assert entries[1].reason == "Target must be an object"
    assert entries[2].reason == "Target IDs must be positive integers"
    assert all(len(entry.reason or "") <= 128 for entry in entries)


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", None])
def test_join_payload_rejects_invalid_ids_per_entry(value):
    from ui.rcon_transport import validate_join_payload

    entry = validate_join_payload({"targets": [{"host_id": value, "instance_id": 1}]})[0]
    assert entry.key is None
    assert entry.reason == "Target IDs must be positive integers"


def test_command_payload_run_id_boundaries_and_trims_command():
    from ui.rcon_transport import validate_command_payload

    run_id, cmd, targets = validate_command_payload({
        "run_id": "r" * 128, "cmd": "  status  ",
        "targets": [{"host_id": 1, "instance_id": 2}],
    })
    assert run_id == "r" * 128
    assert cmd == "status"
    assert targets[0].key == (1, 2)


@pytest.mark.parametrize("run_id", [None, "", " ", 1, "r" * 129])
def test_command_payload_rejects_invalid_run_id(run_id):
    from ui.rcon_transport import RconPayloadError, validate_command_payload

    with pytest.raises(RconPayloadError, match="Invalid run_id"):
        validate_command_payload({"run_id": run_id, "cmd": "status", "targets": []})


@pytest.mark.parametrize("cmd", [None, "", " ", 3, "x" * 4097, "é" * 2049])
def test_command_payload_rejects_invalid_or_oversized_command(cmd):
    from ui.rcon_transport import RconPayloadError, validate_command_payload

    with pytest.raises(RconPayloadError, match="Invalid command") as exc_info:
        validate_command_payload({"run_id": "run", "cmd": cmd, "targets": []})
    if isinstance(cmd, str) and cmd.strip():
        assert cmd not in exc_info.value.safe_reason


def test_command_payload_rejects_unencodable_unicode_safely():
    from ui.rcon_transport import RconPayloadError, validate_command_payload

    with pytest.raises(RconPayloadError, match="Invalid command") as exc_info:
        validate_command_payload({"run_id": "run", "cmd": "\ud800", "targets": []})

    assert exc_info.value.safe_reason == "Invalid command"
    assert len(exc_info.value.safe_reason) <= 128


def test_command_payload_accepts_exact_utf8_byte_limit():
    from ui.rcon_transport import validate_command_payload

    _, ascii_cmd, _ = validate_command_payload({"run_id": "run", "cmd": "x" * 4096, "targets": []})
    _, multi_cmd, _ = validate_command_payload({"run_id": "run", "cmd": "é" * 2048, "targets": []})
    assert len(ascii_cmd.encode("utf-8")) == 4096
    assert len(multi_cmd.encode("utf-8")) == 4096
