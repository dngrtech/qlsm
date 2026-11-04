import json
import logging
import os
from dataclasses import dataclass

from flask import current_app

from ui import db
from ui.models import Host, HostStatus, InstanceStatus
from ui.runtime_upgrade_guard import reserved_host_ids
from ui.task_logic.common import append_log
from ui.task_logic.instance_runtime_reconciliation import reconcile_runtime_observations
from ui.task_logic.service_runtime import RuntimeObservation, probe_host_runtime


logger = logging.getLogger(__name__)

STATUS_KEY_PREFIX = "server:status"
STATUS_TTL = 30  # seconds


@dataclass(frozen=True)
class HostPollResult:
    active_count: int
    observations: dict[str, RuntimeObservation]


def _write_status_to_redis(redis_client, host_id, instance_id, data):
    """Write instance status to management Redis with TTL. Deletes key if data is None."""
    key = f"{STATUS_KEY_PREFIX}:{host_id}:{instance_id}"
    if data is None:
        redis_client.delete(key)
    else:
        redis_client.setex(key, STATUS_TTL, json.dumps(data))


def _fetch_and_cache_host(host, instances, redis_client):
    """Observe one host and preserve the management Redis status-cache contract."""
    redis_password = os.environ.get("REDIS_PASSWORD") if getattr(host, "provider", None) == "self" else None
    logger.debug("Polling host %s (%s) — %d instance(s)", host.name, host.ip_address, len(instances))
    try:
        observations = probe_host_runtime(host, instances, redis_password=redis_password)
    except Exception:
        logger.exception("Unexpected error polling host %s", host.ip_address)
        return None
    if observations is None:
        return None

    active_count = sum(
        1 for instance in instances
        if (observation := observations.get(str(instance.port))) and observation.status
    )
    logger.debug("Host %s — %d/%d instances returned status data", host.name, active_count, len(instances))
    for instance in instances:
        observation = observations.get(str(instance.port))
        _write_status_to_redis(
            redis_client,
            host.id,
            instance.id,
            observation.status if observation is not None else None,
        )
    return HostPollResult(active_count=active_count, observations=observations)


def poll_all_hosts():
    """Poll all active hosts with running instances. Called by the CLI daemon."""
    redis_client = current_app.extensions.get("redis")
    if redis_client is None:
        logger.error("Management Redis not available — skipping status poll")
        return

    hosts = Host.query.filter(Host.status.in_([HostStatus.ACTIVE, HostStatus.ERROR])).all()
    if not hosts:
        logger.debug("No pollable hosts — skipping poll cycle")
        return

    # A runtime upgrade owns its host's host/instance statuses until it is
    # terminal; observing mid-upgrade (or mid-rollback) would overwrite them.
    reserved = reserved_host_ids()

    total_instances = 0
    for host in hosts:
        if host.id in reserved:
            logger.debug("Skipping host %s — runtime upgrade in progress", host.name)
            continue
        running = [
            instance for instance in host.instances
            if instance.status in (InstanceStatus.RUNNING, InstanceStatus.UPDATED)
        ]
        if not running:
            continue
        if not host.ssh_key_path:
            logger.debug("Skipping host %s — no SSH key configured", host.name)
            continue
        total_instances += len(running)
        poll_result = _fetch_and_cache_host(host, running, redis_client)
        if poll_result is None:
            continue
        reconcile_runtime_observations(running, poll_result.observations)
        active_count = poll_result.active_count
        if host.status == HostStatus.ERROR and active_count:
            try:
                host.status = HostStatus.ACTIVE
                append_log(host, "Recovered automatically: status poll succeeded after ERROR.")
                db.session.commit()
                logger.info("Recovered host %s from ERROR after successful status poll", host.name)
            except Exception:
                db.session.rollback()
                logger.exception("Failed to recover host %s from ERROR", host.name)

    logger.debug("Poll cycle complete — %d host(s), %d running instance(s)", len(hosts), total_instances)
