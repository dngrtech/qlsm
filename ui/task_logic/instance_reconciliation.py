import logging

from ui import db
from ui.models import InstanceStatus, QLInstance
from ui.task_logic.ansible_instance_mgmt import (
    _build_ld_preload_paths,
    _build_qlds_args_string,
    _extract_pip_warning,
    _prepare_instance_zmq,
)
from ui.task_logic.ansible_runner import _run_ansible_playbook
from ui.task_logic.common import append_log
from ui.task_logic.cpu_affinity import ensure_instance_cpu_affinity
from ui.task_logic.self_host_network import with_self_host_network_extravars

log = logging.getLogger(__name__)


def _fail_reconciliation(instance, message):
    instance.status = InstanceStatus.ERROR
    append_log(instance, f"Instance reconciliation failed: {message}")
    db.session.commit()
    return False


def reconcile_instance_after_host_setup(
    instance_id,
    *,
    restart_service,
    target_status,
):
    """Reconcile one instance after a host setup rerun.

    This private rerun path has a strict boolean result. Its caller chooses one
    of two deterministic outcomes from the status snapshot taken before any
    per-instance commits: restarted/RUNNING or untouched/STOPPED.
    """
    instance = db.session.get(QLInstance, instance_id)
    if not instance:
        return False

    expected_status = None
    if restart_service is True:
        expected_status = InstanceStatus.RUNNING
    elif restart_service is False:
        expected_status = InstanceStatus.STOPPED
    if target_status is not expected_status:
        return _fail_reconciliation(
            instance,
            "restart_service and target_status do not describe the same outcome",
        )

    try:
        _prepare_instance_zmq(instance)
        cpu_affinity = ensure_instance_cpu_affinity(instance)
        extravars = {
            "host_name": instance.host.name,
            "port": instance.port,
            "id": instance.id,
            "qlds_args": _build_qlds_args_string(instance),
            "ld_preload_paths": _build_ld_preload_paths(instance),
            "cpu_affinity": cpu_affinity,
            "lan_rate_enabled": instance.lan_rate_enabled,
            "restart_service": restart_service,
            "keep_service_stopped": not restart_service,
        }
        extravars = with_self_host_network_extravars(instance, extravars)
        runner_result, error_msg = _run_ansible_playbook(
            instance,
            "sync_instance_configs_and_restart.yml",
            extravars=extravars,
        )

        if error_msg:
            return _fail_reconciliation(instance, error_msg)
        if runner_result is None:
            return _fail_reconciliation(
                instance,
                "Ansible runner did not return a result",
            )

        stdout_content = (
            runner_result.stdout()
            if callable(getattr(runner_result, "stdout", None))
            else getattr(runner_result, "_stdout", "")
        )
        pip_warning = _extract_pip_warning(stdout_content)
        if pip_warning:
            append_log(instance, f"Warning: {pip_warning}")

        if runner_result.rc != 0:
            return _fail_reconciliation(
                instance,
                f"Ansible runner RC: {runner_result.rc}",
            )

        instance.status = target_status
        append_log(
            instance,
            f"Instance reconciliation completed. Status: {target_status.value}.",
        )
        db.session.commit()
        return True
    except Exception as exc:
        log.exception(
            "Instance reconciliation raised for instance_id %s",
            instance_id,
        )
        return _fail_reconciliation(instance, f"unexpected exception: {exc}")
