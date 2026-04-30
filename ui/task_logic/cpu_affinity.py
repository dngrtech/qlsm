import logging
import os
import subprocess

from ui.vultr_plans import get_plan

log = logging.getLogger(__name__)


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _non_negative_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _infer_vultr_cpu_count(host):
    if getattr(host, 'provider', None) != 'vultr':
        return None

    plan = get_plan(getattr(host, 'machine_size', None))
    if not plan:
        return None
    return _positive_int(plan.get('vcpu'))


def _detect_cpu_count_with_ansible(host):
    inventory_path = os.path.abspath('ansible/inventory/')
    cmd = [
        'ansible',
        '-i',
        inventory_path,
        host.name,
        '-m',
        'command',
        '-a',
        'nproc',
    ]

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            env=os.environ,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Could not detect CPU count for host %s: %s", host.name, exc)
        return None

    if result.returncode != 0:
        log.warning(
            "CPU count detection failed for host %s: %s",
            host.name,
            result.stderr.strip(),
        )
        return None

    for token in reversed(result.stdout.split()):
        parsed = _positive_int(token)
        if parsed:
            return parsed
    return None


def resolve_host_cpu_count(host):
    saved = _positive_int(getattr(host, 'cpu_count', None))
    if saved:
        return saved

    detected = _infer_vultr_cpu_count(host)
    if detected is None:
        detected = _detect_cpu_count_with_ansible(host)

    if detected:
        host.cpu_count = detected
    return detected


def choose_least_used_cpu(host, cpu_count, exclude_instance_id=None):
    counts = [0 for _ in range(cpu_count)]

    for inst in getattr(host, 'instances', []) or []:
        if exclude_instance_id is not None and inst.id == exclude_instance_id:
            continue
        affinity = _non_negative_int(getattr(inst, 'cpu_affinity', None))
        if affinity is not None and affinity < cpu_count:
            counts[affinity] += 1

    return min(range(cpu_count), key=lambda cpu: (counts[cpu], cpu))


def ensure_instance_cpu_affinity(instance):
    host = getattr(instance, 'host', None)
    if not host:
        return None

    cpu_count = resolve_host_cpu_count(host)
    if not cpu_count or cpu_count <= 1:
        instance.cpu_affinity = None
        return None

    existing = _non_negative_int(getattr(instance, 'cpu_affinity', None))
    if existing is not None and existing < cpu_count:
        return existing

    assigned = choose_least_used_cpu(
        host,
        cpu_count,
        exclude_instance_id=instance.id,
    )
    instance.cpu_affinity = assigned
    return assigned
