import os

from ui import db
from ui.models import QLInstance, InstanceStatus
from ui.task_logic.ansible_instance_mgmt import (
    _build_ld_preload_paths,
    _build_qlds_args_string,
    _run_ansible_playbook,
    ensure_instance_cpu_affinity,
)
from ui.task_logic.common import append_log


CONFIGS_BASE = "configs"
ELF_MAGIC = b"\x7fELF"


def _instance_scripts_dir(instance):
    return os.path.join(CONFIGS_BASE, instance.host.name, str(instance.id), "scripts")


def _enabled_hooks(instance):
    if not instance.ld_preload_hooks:
        return []
    return [h.strip() for h in instance.ld_preload_hooks.split(",") if h.strip()]


def _preflight(instance):
    for filename in _enabled_hooks(instance):
        full_path = os.path.join(_instance_scripts_dir(instance), filename)
        if not os.path.isfile(full_path):
            return f"{filename} missing"
        try:
            with open(full_path, "rb") as handle:
                if handle.read(4) != ELF_MAGIC:
                    return f"{filename} is not an ELF shared object"
        except OSError as exc:
            return f"{filename} could not be read: {exc}"
    return None


def apply_instance_hooks_logic(instance_id, restart_service=True):
    instance = db.session.get(QLInstance, instance_id)
    if not instance:
        return False
    if not instance.host:
        instance.status = InstanceStatus.ERROR
        append_log(instance, "apply_instance_hooks failed: associated host not found")
        db.session.commit()
        return False

    append_log(instance, "Task started: apply_instance_hooks")
    instance.status = InstanceStatus.CONFIGURING
    db.session.commit()

    preflight_error = _preflight(instance)
    if preflight_error:
        instance.status = InstanceStatus.ERROR
        append_log(instance, f"LD_PRELOAD pre-flight failed: {preflight_error}")
        db.session.commit()
        return False

    cpu_affinity = ensure_instance_cpu_affinity(instance)
    extravars = {
        "port": instance.port,
        "host_name": instance.host.name,
        "qlds_args": _build_qlds_args_string(instance),
        "ld_preload_paths": _build_ld_preload_paths(instance),
        "cpu_affinity": cpu_affinity,
        "restart_service": restart_service,
    }
    runner_result, error_msg = _run_ansible_playbook(
        instance,
        "update_instance_hooks.yml",
        extravars=extravars,
    )

    if error_msg or runner_result is None or getattr(runner_result, "rc", 1) != 0:
        instance.status = InstanceStatus.ERROR
        append_log(instance, f"apply_instance_hooks failed: {error_msg or 'ansible error'}")
        db.session.commit()
        return False

    instance.status = InstanceStatus.RUNNING if restart_service else InstanceStatus.STOPPED
    append_log(instance, "apply_instance_hooks completed")
    db.session.commit()
    return True
