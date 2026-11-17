"""Bounded SSH observation of QLDS live status and systemd runtime identity."""

import base64
import json
import logging
import os
import re
import shlex
import subprocess
from dataclasses import dataclass

from ui.constants import BASE_GAME_PORT, resolve_redis_db
from ui.task_logic.self_host_network import resolve_self_host_management_target

logger = logging.getLogger(__name__)
INVOCATION_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
SSH_CONNECT_TIMEOUT = 3
REDIS_PHASE_TIMEOUT = 2
SYSTEMD_TIMEOUT = 5
RUNTIME_PROBE_HEADROOM = 2
RUNTIME_PROBE_TIMEOUT = SSH_CONNECT_TIMEOUT + REDIS_PHASE_TIMEOUT + SYSTEMD_TIMEOUT + RUNTIME_PROBE_HEADROOM

@dataclass(frozen=True)
class RuntimeObservation:
    status: object | None
    invocation_id: str | None
    active: bool
    service_started_at: int | None
    # Engine processes for the port (only when probed with_processes=True).
    processes: int | None = None


# Executed on the host by the probe (and in tests against a fake /proc).
# Counts, per port, processes in the instance's systemd unit cgroup plus any
# qzeroded engine started with `+set net_port <port>` outside it, so a server
# that outlived its unit is still seen.
PROCESS_SCAN_SOURCE = '''
def count_qlds_processes(ports, proc_root="/proc"):
    import os
    counts = {port: 0 for port in ports}
    try:
        pids = [name for name in os.listdir(proc_root) if name.isdigit()]
    except OSError:
        return None
    for pid in pids:
        try:
            with open(os.path.join(proc_root, pid, "cmdline"), "rb") as handle:
                argv = handle.read().split(b"\\0")
        except OSError:
            continue
        try:
            with open(os.path.join(proc_root, pid, "cgroup"), "rb") as handle:
                cgroup = handle.read().decode(errors="replace")
        except OSError:
            cgroup = ""
        engine = bool(argv) and os.path.basename(argv[0].decode(errors="replace")).startswith("qzeroded")
        for port in ports:
            in_unit = "qlds@%d.service" % port in cgroup
            flagged = engine and any(
                argv[i] == b"net_port" and argv[i + 1] == str(port).encode()
                for i in range(len(argv) - 1))
            if in_unit or flagged:
                counts[port] += 1
    return counts
'''

def _normalize_invocation_id(value):
    value = value.strip() if isinstance(value, str) else ""
    return value.lower() if INVOCATION_ID_RE.fullmatch(value) else None


def _positive_integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None

def _ssh_target_for_host(host):
    if getattr(host, "provider", None) == "self":
        return resolve_self_host_management_target()
    return host.ip_address

def _validated_port_db_pairs(instances):
    pairs = []
    for instance in instances:
        port_value = getattr(instance, "port", None)
        if not isinstance(port_value, int) or isinstance(port_value, bool):
            raise ValueError("Instance port must be an integer")
        port = port_value

        db_value = getattr(instance, "redis_db", None)
        if db_value is not None and (not isinstance(db_value, int) or isinstance(db_value, bool)):
            raise ValueError("Redis DB index must be an integer")
        try:
            db = resolve_redis_db(instance)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Redis DB for port {port}") from exc
        if isinstance(db, bool) or not isinstance(db, int) or db < 1:
            raise ValueError(
                f"Invalid port {port}: Redis DB index must be >= 1 "
                f"(port must be >= {BASE_GAME_PORT})"
            )
        pairs.append((port, db))
    return pairs


def _remote_probe_script(ports_dbs, redis_password, with_processes=False):
    password_b64 = base64.b64encode(redis_password.encode()).decode() if redis_password is not None else None
    process_scan = PROCESS_SCAN_SOURCE if with_processes else ''
    return f'''import base64
import json
import math
import multiprocessing
import queue
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import redis

ports_dbs = {ports_dbs!r}
redis_password_b64 = {password_b64!r}
monotonic_now = time.monotonic()
wall_now = time.time()
redis_password = (
    base64.b64decode(redis_password_b64).decode()
    if redis_password_b64 is not None else None
)

def read_status(port, db):
    try:
        client = redis.Redis(
            db=db,
            password=redis_password,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        value = client.get(f"minqlx:server_status:{{port}}")
        return json.loads(value or "null")
    except Exception:
        return None

statuses = {{port: None for port, _ in ports_dbs}}
if ports_dbs:
    def collect_statuses(status_queue):
        with ThreadPoolExecutor(max_workers=min(8, len(ports_dbs))) as executor:
            futures = {{executor.submit(read_status, port, db): port for port, db in ports_dbs}}
            for future in as_completed(futures):
                port = futures[future]
                try:
                    status = future.result()
                except Exception:
                    status = None
                status_queue.put((port, status))
        status_queue.put((None, None))

    # Python 3.14 defaults to forkserver on Linux, which cannot pickle a function
    # defined in a `python3 -c` script. Pin fork; the parent has no threads yet.
    mp = multiprocessing.get_context("fork")
    status_queue = mp.Queue()
    worker = mp.Process(target=collect_statuses, args=(status_queue,), daemon=True)
    worker.start()
    redis_deadline = time.monotonic() + {REDIS_PHASE_TIMEOUT}
    while True:
        remaining = redis_deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            port, status = status_queue.get(timeout=remaining)
        except queue.Empty:
            break
        if port is None:
            break
        statuses[port] = status
    if worker.is_alive():
        worker.kill()
    worker.join(timeout=0.1)

units = [f"qlds@{{port}}.service" for port, _ in ports_dbs]
systemd_stdout = ""
if units:
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                *units,
                "--property=Id",
                "--property=ActiveState",
                "--property=InvocationID",
                "--property=ActiveEnterTimestampMonotonic",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout={SYSTEMD_TIMEOUT},
        )
        systemd_stdout = result.stdout or ""
    except subprocess.TimeoutExpired as error:
        systemd_stdout = error.stdout or ""
    except OSError:
        systemd_stdout = ""
if isinstance(systemd_stdout, bytes):
    systemd_stdout = systemd_stdout.decode(errors="replace")

records = {{}}
for block in systemd_stdout.split("\\n\\n"):
    record = {{}}
    for line in block.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            record[key] = value
    unit_id = record.get("Id")
    if unit_id:
        records[unit_id] = record

{process_scan}
process_counts = (
    count_qlds_processes([port for port, _ in ports_dbs]) if {bool(with_processes)!r} else None
)

observations = {{}}
for port, _ in ports_dbs:
    record = records.get(f"qlds@{{port}}.service", {{}})
    try:
        monotonic_usec = int(record.get("ActiveEnterTimestampMonotonic", "0"))
    except (TypeError, ValueError):
        monotonic_usec = 0
    service_started_at = (
        math.floor(wall_now - monotonic_now + monotonic_usec / 1_000_000)
        if monotonic_usec > 0 else None
    )
    observations[str(port)] = {{
        "status": statuses[port],
        "active_state": record.get("ActiveState"),
        "invocation_id": record.get("InvocationID"),
        "service_started_at": service_started_at,
        "processes": process_counts.get(port) if process_counts is not None else None,
    }}
print(json.dumps(observations))
'''


def build_runtime_probe_command(host, instances, redis_password=None, with_processes=False):
    """Build one SSH command that observes every requested instance on a host."""
    ports_dbs = _validated_port_db_pairs(instances)
    script = _remote_probe_script(ports_dbs, redis_password, with_processes=with_processes)
    return [
        "ssh",
        "-i", os.path.abspath(host.ssh_key_path),
        "-p", str(host.ssh_port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-l", host.ssh_user,
        _ssh_target_for_host(host),
        f"python3 -c {shlex.quote(script)}",
    ]


def _load_probe_payload(output):
    if not isinstance(output, str) or not output.strip():
        logger.warning("Runtime probe returned no JSON output")
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        logger.warning("Failed to parse runtime probe output: %r", output[:200])
        return None
    if not isinstance(payload, dict):
        logger.warning("Runtime probe output was not a mapping")
        return None
    return payload


def _observations_from_payload(payload):
    observations = {}
    for port, raw_observation in payload.items():
        raw_observation = raw_observation if isinstance(raw_observation, dict) else {}
        active = raw_observation.get("active_state") == "active"
        service_started_at = _positive_integer(raw_observation.get("service_started_at"))
        invocation_id = _normalize_invocation_id(raw_observation.get("invocation_id"))
        if not active or service_started_at is None:
            invocation_id = None
        processes = raw_observation.get("processes")
        if isinstance(processes, bool) or not isinstance(processes, int) or processes < 0:
            processes = None
        observations[str(port)] = RuntimeObservation(
            status=raw_observation.get("status"),
            invocation_id=invocation_id,
            active=active,
            service_started_at=service_started_at,
            processes=processes,
        )
    return observations


def parse_runtime_probe_output(output):
    """Parse successful probe JSON, returning an empty mapping for invalid output."""
    payload = _load_probe_payload(output)
    return _observations_from_payload(payload) if payload is not None else {}


def observation_has_fresh_status(observation):
    """Whether an observation can later prove a service started after its status."""
    if not isinstance(observation, RuntimeObservation) or not observation.active:
        return False
    if _normalize_invocation_id(observation.invocation_id) is None:
        return False
    service_started_at = _positive_integer(observation.service_started_at)
    status = observation.status
    if service_started_at is None or not isinstance(status, dict):
        return False
    updated = status.get("updated")
    return isinstance(updated, int) and not isinstance(updated, bool) and updated > service_started_at


def probe_host_runtime(host, instances, redis_password=None, with_processes=False):
    """Return a host observation map, or None when the SSH round-trip fails."""
    try:
        command = build_runtime_probe_command(host, instances, redis_password=redis_password,
                                              with_processes=with_processes)
    except Exception as exc:
        logger.warning("Could not build runtime probe for host %s: %s", getattr(host, "name", "?"), exc)
        return None
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=RUNTIME_PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning("SSH timeout probing runtime on host %s", getattr(host, "ip_address", "?"))
        return None
    except Exception:
        logger.exception("Runtime probe SSH failed for host %s", getattr(host, "ip_address", "?"))
        return None
    if result.returncode != 0:
        logger.warning("Runtime probe SSH failed for host %s: %s", getattr(host, "ip_address", "?"), result.stderr[:200])
        return None
    payload = _load_probe_payload(result.stdout)
    return _observations_from_payload(payload) if payload is not None else None


def _usable_identity(observation):
    if not isinstance(observation, RuntimeObservation) or not observation.active:
        return None
    if _positive_integer(observation.service_started_at) is None:
        return None
    return _normalize_invocation_id(observation.invocation_id)


def probe_host_invocation_ids(host, instances):
    """Return per-port usable systemd invocation IDs without raising into tasks."""
    try:
        instance_list = list(instances)
        result = {str(int(instance.port)): None for instance in instance_list}
        password = os.environ.get("REDIS_PASSWORD") if getattr(host, "provider", None) == "self" else None
    except Exception:
        logger.exception("Unable to prepare invocation ID probe for host %s", getattr(host, "id", "?"))
        return {}
    try:
        observations = probe_host_runtime(host, instance_list, redis_password=password)
    except Exception:
        logger.exception("Unable to collect invocation IDs for host %s", getattr(host, "id", "?"))
        return result
    if observations is None:
        return result
    for port, observation in observations.items():
        if port in result:
            result[port] = _usable_identity(observation)
    return result


def probe_instance_invocation_id(instance):
    """Return one usable invocation ID without allowing probe failures to escape."""
    try:
        host = getattr(instance, "host", None)
        if host is None:
            return None
        return probe_host_invocation_ids(host, [instance]).get(str(int(instance.port)))
    except Exception:
        logger.exception("Unable to collect invocation ID for instance %s", getattr(instance, "id", "?"))
        return None


def quiescence_state(observation):
    """'active' (systemd active), 'inactive' (systemd inactive and no engine
    process for the port), 'stray_process' (systemd inactive but a server
    process is still there) or 'unknown' (not observed, or processes not
    counted)."""
    if not isinstance(observation, RuntimeObservation):
        return 'unknown'
    if observation.active:
        return 'active'
    if observation.processes is None:
        return 'unknown'
    return 'stray_process' if observation.processes > 0 else 'inactive'
