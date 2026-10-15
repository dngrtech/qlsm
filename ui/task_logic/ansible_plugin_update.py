# ui/task_logic/ansible_plugin_update.py
#
# Applies a set of updates the operator picked from "Check for Updates"
# (ui/task_logic/plugin_update_check.py). Two independent pieces, matched to
# the two diffs the check produces:
#
#  - host common pool: re-runs the existing update_common_plugins.yml
#    playbook (full rsync --archive --delete sync of the merged pool, built-in
#    tier plus operator tier, -> the host's shared pool dir) — cheap and
#    idempotent, and safe to run even though it isn't scoped to exactly the
#    files the operator ticked.
#  - instance-selected plugins: a plain local file copy from the merged pool
#    (see ui/plugin_pool.py) into configs/{host}/{instance}/scripts/ — no
#    SSH involved, since that directory lives on the qlsm controller itself.
#    The next restart
#    (queued here if the operator asked for one) picks it up via the
#    existing "Sync instance-specific scripts" task, same as any other
#    config change.

import logging
import os
import shutil

from rq import get_current_job
from flask import current_app

from ui.models import HostStatus, InstanceStatus
from ui.database import get_host, update_host, update_instance
from ui.plugin_pool import resolve_pool_file, resolve_pool_path
from ui.runtime import host_runtime, runtime_extravars
from .ansible_runner import _run_host_ansible_playbook


log = logging.getLogger(__name__)


def _copy_selected_plugin_files(host, instance, filenames):
    """Copies filenames from the merged pool (operator copy wins) into this
    instance's selected-scripts directory. Returns (applied, skipped)
    filename lists. A name is a bare filename (os.path.basename applied
    defensively — this list ultimately comes from a JSON request body) or a
    forward-slash path into a plugin's helper package ('restore/items.py')."""
    runtime = host_runtime(host)
    dest_dir = os.path.abspath(os.path.join('configs', host.name, str(instance.id), 'scripts'))
    os.makedirs(dest_dir, exist_ok=True)

    applied, skipped = [], []
    for raw_name in filenames:
        if isinstance(raw_name, str) and '/' in raw_name:
            # A package member such as 'restore/items.py'. Every segment is
            # checked and the destination must stay inside dest_dir.
            parts = raw_name.split('/')
            if any(not p or p in ('.', '..') or '\\' in p or ':' in p for p in parts):
                skipped.append(raw_name)
                continue
            src = resolve_pool_path(runtime, raw_name)
            dest = os.path.abspath(os.path.join(dest_dir, *parts))
            if src is None or os.path.commonpath([dest_dir, dest]) != dest_dir:
                skipped.append(raw_name)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            applied.append(raw_name)
            continue
        name = os.path.basename(raw_name)
        src = resolve_pool_file(runtime, name) if name else None
        if src is None:
            skipped.append(raw_name)
            continue
        shutil.copy2(src, os.path.join(dest_dir, name))
        applied.append(name)
    return applied, skipped


def apply_plugin_updates_logic(host_id, apply_common_pool, instance_selections, restart_instance_ids):
    """instance_selections: {instance_id: [filename, ...]}
    restart_instance_ids: instance ids to restart once updates are applied
    (a restart is required for an instance to actually pick up either kind
    of change — this only stages the files / refreshes the common pool)."""
    host = get_host(host_id)
    if not host:
        current_app.logger.error(f"apply_plugin_updates_logic: Host {host_id} not found.")
        return False

    original_host_logs = host.logs or ""
    update_host(host.id, status=HostStatus.ACTIVE, logs=f"Applying plugin updates...\n{original_host_logs}")

    try:
        get_current_job()
        summary_lines = []

        if apply_common_pool:
            current_app.logger.info(f"Refreshing common plugin pool on host: {host.name}")
            success, stdout, stderr = _run_host_ansible_playbook(
                host=host,
                playbook_name="update_common_plugins.yml",
                extravars=runtime_extravars(host),
            )
            if not success:
                current_app.logger.error(f"Failed to update common plugin pool on {host.name}: {stderr}")
                update_host(host.id, status=HostStatus.ERROR,
                             logs=f"Common plugin pool update failed: {stderr}.\n{original_host_logs}")
                return False
            summary_lines.append("Common plugin pool refreshed.")

        instances_by_id = {i.id: i for i in host.instances}
        for instance_id, filenames in (instance_selections or {}).items():
            instance = instances_by_id.get(instance_id)
            if not instance or not filenames:
                continue
            applied, skipped = _copy_selected_plugin_files(host, instance, filenames)
            if applied:
                summary_lines.append(f"{instance.name}: staged {', '.join(applied)}.")
            if skipped:
                current_app.logger.warning(f"apply_plugin_updates_logic: skipped unknown files {skipped} for instance {instance_id}")

        update_host(host.id, status=HostStatus.ACTIVE,
                     logs=f"{' '.join(summary_lines) or 'No changes applied.'}\n{original_host_logs}")

        from ui.tasks import restart_instance
        for instance in host.instances:
            if instance.status == InstanceStatus.STOPPED or instance.id not in (restart_instance_ids or []):
                continue
            update_instance(
                instance.id,
                status=InstanceStatus.RESTARTING,
                logs=f"Plugin updates applied. Queuing restart...\n{instance.logs or ''}"
            )
            restart_instance.queue(instance.id)

        return True

    except Exception as e:
        current_app.logger.exception(f"Unexpected error in apply_plugin_updates_logic: {e}")
        job = get_current_job()
        job_str = job.id if job else "unknown_job"
        update_host(host.id, status=HostStatus.ERROR,
                     logs=f"Unexpected Python error while applying plugin updates (Job ID: {job_str}): {str(e)}\n{original_host_logs}")
        return False
