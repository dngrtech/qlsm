"""Task logic for resizing a Vultr host through Terraform."""
import logging
import os
import shutil

from rq import get_current_job

from ui import db
from ui.models import Host, HostStatus
from .common import append_log
from .terraform_runner import _run_terraform_command, run_terraform_with_retry

log = logging.getLogger(__name__)


def _fail_host(host, message):
    host.status = HostStatus.ERROR
    append_log(host, f"Resize failed: {message}")
    db.session.commit()
    return f"Error: {message}"


def resize_host_logic(host_id, new_plan):
    """Resize an existing Vultr host by re-applying Terraform with a new plan."""
    job = get_current_job()
    job_id = job.id if job else "no-job"
    log.info("Starting resize_host for host_id=%s new_plan=%s (Job ID: %s)", host_id, new_plan, job_id)

    host = db.session.get(Host, host_id)
    if host is None:
        log.error("Host with id %s not found.", host_id)
        return f"Error: Host {host_id} not found."

    append_log(host, f"Task started: resize_host (Job ID: {job_id}) -> {new_plan}")
    db.session.commit()

    if host.status != HostStatus.CONFIGURING:
        return _fail_host(host, f"host must be CONFIGURING before resize. Current state: {host.status.value}")
    if host.provider != "vultr":
        return _fail_host(host, f"provider {host.provider} is not supported")
    if not host.workspace_name:
        return _fail_host(host, "host has no Terraform workspace_name")
    if not shutil.which("terraform"):
        return _fail_host(host, "Terraform executable not found in PATH")

    terraform_root_dir = os.path.abspath("terraform/vultr-root")
    if not os.path.isdir(terraform_root_dir):
        return _fail_host(host, f"Terraform root directory not found: {terraform_root_dir}")

    _, error = _run_terraform_command(host, ["init", "-input=false", "-no-color"], terraform_root_dir)
    if error:
        return _fail_host(host, f"terraform init failed: {error}")

    _, error = _run_terraform_command(host, ["workspace", "select", host.workspace_name], terraform_root_dir)
    if error:
        return _fail_host(host, f"Terraform workspace not found: {error}")

    apply_args = [
        "apply",
        "-auto-approve",
        "-input=false",
        "-no-color",
        f"-var=instance_name={host.name}",
        f"-var=vultr_region={host.region}",
        f"-var=vultr_plan={new_plan}",
    ]
    _, error = run_terraform_with_retry(host, apply_args, terraform_root_dir)
    if error:
        host.status = HostStatus.ERROR
        append_log(host, f"Resize failed during terraform apply: {error}")
        db.session.commit()
        return f"Error during terraform apply: {error}"

    old_plan = host.machine_size
    host.machine_size = new_plan
    host.status = HostStatus.ACTIVE
    append_log(host, f"Resize complete: {old_plan} -> {new_plan}. Status: {host.status.value}")
    db.session.commit()

    log.info("Resize complete for host_id=%s: %s -> %s", host_id, old_plan, new_plan)
    return f"Host {host_id} resize complete: {old_plan} -> {new_plan}."
