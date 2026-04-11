import json
import logging
import os
import subprocess

from flask import current_app

from ui.models import Host, HostStatus, InstanceStatus
from ui.routes.self_host_helpers import resolve_self_host_management_target

logger = logging.getLogger(__name__)

STATUS_KEY_PREFIX = 'server:status'
STATUS_TTL = 30  # seconds


def _ssh_target_for_host(host):
    if getattr(host, "provider", None) == "self":
        return resolve_self_host_management_target()
    return host.ip_address


def _build_ssh_command(host, instances):
    """Build SSH command that reads all instance Redis DBs in one round-trip."""
    ports_dbs = [(int(inst.port), int(inst.port) - 27959) for inst in instances]
    for port, db in ports_dbs:
        if db < 1:
            raise ValueError(f"Invalid port {port}: Redis DB index must be >= 1 (port must be >= 27960)")
    target = _ssh_target_for_host(host)
    python_snippet = (
        "import redis,json;"
        f"ports_dbs={ports_dbs!r};"
        "out={};"
        "[out.__setitem__(str(port), json.loads(r.get(f'minqlx:server_status:{port}') or 'null'))"
        " for port,db in ports_dbs"
        " for r in [redis.Redis(db=db)]];"
        "print(json.dumps(out))"
    )
    return [
        'ssh',
        '-i', os.path.abspath(host.ssh_key_path),
        '-p', str(host.ssh_port),
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=5',
        '-l', host.ssh_user,
        target,
        f'python3 -c "{python_snippet}"',
    ]


def _parse_ssh_output(output):
    """Parse JSON output from SSH command. Returns {} on any error."""
    if not output or not output.strip():
        return {}
    try:
        return json.loads(output.strip())
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse SSH status output: {output[:200]!r}")
        return {}


def _write_status_to_redis(redis_client, host_id, instance_id, data):
    """Write instance status to management Redis with TTL. Deletes key if data is None."""
    key = f'{STATUS_KEY_PREFIX}:{host_id}:{instance_id}'
    if data is None:
        redis_client.delete(key)
    else:
        redis_client.setex(key, STATUS_TTL, json.dumps(data))


def _fetch_and_cache_host(host, instances, redis_client):
    """SSH to one host, read all instance statuses, write to management Redis."""
    cmd = _build_ssh_command(host, instances)
    target = _ssh_target_for_host(host)
    logger.debug(
        "Polling host %s (connect=%s, target=%s) — %d instance(s)",
        host.name,
        host.ip_address,
        target,
        len(instances),
    )
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                f"SSH to host {host.ip_address} failed "
                f"(exit {result.returncode}): {result.stderr[:200]}"
            )
            return

        port_map = _parse_ssh_output(result.stdout)
        active = sum(1 for inst in instances if port_map.get(str(inst.port)))
        logger.debug("Host %s — %d/%d instances returned status data", host.name, active, len(instances))
        for inst in instances:
            data = port_map.get(str(inst.port))
            _write_status_to_redis(redis_client, host.id, inst.id, data)

    except subprocess.TimeoutExpired:
        logger.warning(f"SSH timeout polling host {host.ip_address}")
    except Exception as e:
        logger.error(f"Unexpected error polling host {host.ip_address}: {e}", exc_info=True)


def poll_all_hosts():
    """Poll all active hosts with running instances. Called by the CLI daemon."""
    redis_client = current_app.extensions.get('redis')
    if redis_client is None:
        logger.error("Management Redis not available — skipping status poll")
        return

    hosts = Host.query.filter_by(status=HostStatus.ACTIVE).all()
    if not hosts:
        logger.debug("No active hosts — skipping poll cycle")
        return

    total_instances = 0
    for host in hosts:
        running = [
            inst for inst in host.instances
            if inst.status in (InstanceStatus.RUNNING, InstanceStatus.UPDATED)
        ]
        if not running:
            continue
        total_instances += len(running)
        _fetch_and_cache_host(host, running, redis_client)

    logger.debug("Poll cycle complete — %d host(s), %d running instance(s)", len(hosts), total_instances)
