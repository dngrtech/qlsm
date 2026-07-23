"""Shared Redis transport, target resolution, and fleet payload validation."""

from dataclasses import dataclass
import json
import logging
import os
import threading
from typing import Any

import redis

from ui.models import InstanceStatus, QLInstance
from ui.task_logic.self_host_network import resolve_self_host_management_target

MAX_FLEET_TARGETS = 100
MAX_RUN_ID_CHARS = 128
MAX_COMMAND_BYTES = 4096
READY_STATUSES = frozenset({InstanceStatus.RUNNING, InstanceStatus.UPDATED})
_SAFE_ERROR_LIMIT = 128

log = logging.getLogger(__name__)


class RconTargetError(ValueError):
    """A credential-free target rejection safe to return to a client."""


class RconPayloadError(ValueError):
    """A bounded payload rejection safe to return to a client."""

    def __init__(self, safe_reason: str):
        self.safe_reason = safe_reason[:_SAFE_ERROR_LIMIT]
        super().__init__(self.safe_reason)


@dataclass(frozen=True)
class ResolvedRconTarget:
    host_id: int
    instance_id: int
    ip: str
    rcon_port: int
    rcon_password: str
    self_host: bool

    @property
    def room(self) -> str:
        return room_name(self.host_id, self.instance_id)

    @property
    def channel(self) -> str:
        return command_channel(self.host_id, self.instance_id)


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    subscribers: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class ValidatedTarget:
    """One valid target key or a safe per-entry rejection."""

    host_id: int | None = None
    instance_id: int | None = None
    reason: str | None = None

    @property
    def key(self) -> tuple[int, int] | None:
        if self.host_id is None or self.instance_id is None:
            return None
        return self.host_id, self.instance_id


_client = None
_client_lock = threading.Lock()


def room_name(host_id: int, instance_id: int) -> str:
    return f"rcon:{host_id}:{instance_id}"


def command_channel(host_id: int, instance_id: int) -> str:
    prefix = os.environ.get("REDIS_PREFIX", "rcon")
    return f"{prefix}:cmd:{host_id}:{instance_id}"


def get_redis_client():
    """Get or create the process-local Redis client."""
    global _client
    with _client_lock:
        if _client is None:
            kwargs: dict[str, Any] = {"decode_responses": True}
            password = os.environ.get("REDIS_PASSWORD")
            if password:
                kwargs["password"] = password
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            _client = redis.from_url(redis_url, **kwargs)
        return _client


def rcon_target_for_host(host, self_host_resolver=None) -> str | None:
    if getattr(host, "provider", None) == "self":
        resolver = self_host_resolver or resolve_self_host_management_target
        return resolver()
    return getattr(host, "ip_address", None)


def resolve_fleet_target(host_id: int, instance_id: int) -> ResolvedRconTarget:
    """Resolve and validate an eligible target without exposing credentials."""
    instance = QLInstance.query.get(instance_id)
    if not instance or instance.host_id != host_id:
        raise RconTargetError("Instance not found on host")
    if instance.status not in READY_STATUSES:
        raise RconTargetError("Instance is not running")

    port = instance.zmq_rcon_port
    password = instance.zmq_rcon_password
    if (
        isinstance(port, bool) or not isinstance(port, int) or port <= 0
        or not isinstance(password, str) or not password
    ):
        raise RconTargetError("RCON not configured")

    host = instance.host
    self_host = getattr(host, "provider", None) == "self"
    ip = rcon_target_for_host(host)
    if not isinstance(ip, str) or not ip.strip():
        raise RconTargetError("Host address unavailable")

    return ResolvedRconTarget(
        host_id=host_id,
        instance_id=instance_id,
        ip=ip.strip(),
        rcon_port=port,
        rcon_password=password,
        self_host=self_host,
    )


def publish_json(channel: str, payload: dict) -> PublishResult:
    """Publish JSON and report delivery availability without raising Redis errors."""
    global _client
    try:
        subscribers = get_redis_client().publish(channel, json.dumps(payload))
    except redis.RedisError:
        log.warning("Redis publish failed for RCON channel")
        with _client_lock:
            _client = None
        return PublishResult(False, 0, "Communication service temporarily unavailable")
    if subscribers < 1:
        return PublishResult(False, subscribers, "RCON service unavailable")
    return PublishResult(True, subscribers)


def connect_payload(target: ResolvedRconTarget) -> dict:
    return {
        "action": "connect",
        "ip": target.ip,
        "rcon_port": target.rcon_port,
        "rcon_password": target.rcon_password,
        "self_host": target.self_host,
    }


def command_payload(cmd: str) -> dict:
    return {"action": "command", "cmd": cmd}


def disconnect_payload() -> dict:
    return {"action": "disconnect"}


def _validate_object(payload: Any, allowed_fields: set[str]) -> dict:
    if not isinstance(payload, dict):
        raise RconPayloadError("Payload must be an object")
    if set(payload) - allowed_fields:
        raise RconPayloadError("Unexpected payload fields")
    return payload


def _validate_targets(value: Any) -> list[ValidatedTarget]:
    if not isinstance(value, list):
        raise RconPayloadError("Targets must be a list")
    if len(value) > MAX_FLEET_TARGETS:
        raise RconPayloadError("Too many targets")

    entries = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            entries.append(ValidatedTarget(reason="Target must be an object"))
            continue
        if set(item) != {"host_id", "instance_id"}:
            entries.append(ValidatedTarget(reason="Target must contain host_id and instance_id"))
            continue
        host_id = item["host_id"]
        instance_id = item["instance_id"]
        if not _positive_int(host_id) or not _positive_int(instance_id):
            entries.append(ValidatedTarget(reason="Target IDs must be positive integers"))
            continue
        key = (host_id, instance_id)
        if key not in seen:
            entries.append(ValidatedTarget(host_id, instance_id))
            seen.add(key)
    return entries


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_join_payload(payload: Any) -> list[ValidatedTarget]:
    data = _validate_object(payload, {"targets"})
    return _validate_targets(data.get("targets"))


def validate_command_payload(
    payload: Any,
) -> tuple[str, str, list[ValidatedTarget]]:
    data = _validate_object(payload, {"run_id", "cmd", "targets"})
    run_id = data.get("run_id")
    if (
        not isinstance(run_id, str) or not run_id.strip()
        or len(run_id) > MAX_RUN_ID_CHARS
    ):
        raise RconPayloadError("Invalid run_id")
    cmd = data.get("cmd")
    if not isinstance(cmd, str):
        raise RconPayloadError("Invalid command")
    cmd = cmd.strip()
    try:
        encoded_cmd = cmd.encode("utf-8")
    except UnicodeEncodeError:
        raise RconPayloadError("Invalid command") from None
    if not cmd or len(encoded_cmd) > MAX_COMMAND_BYTES:
        raise RconPayloadError("Invalid command")
    return run_id, cmd, _validate_targets(data.get("targets"))
