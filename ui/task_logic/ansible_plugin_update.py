# ui/task_logic/ansible_plugin_update.py
#
# Applies a set of updates the operator picked from "Check for Updates"
# (ui/task_logic/plugin_update_check.py). Two independent pieces, matched to
# the two diffs the check produces:
#
#  - host common pool: re-runs the existing update_common_plugins.yml
#    playbook (full rsync --archive --delete sync of ql-assets -> the host's
#    shared pool dir) — cheap and idempotent, and safe to run even though it
#    isn't scoped to exactly the files the operator ticked.
#  - instance-selected plugins: a plain local file copy from the ql-assets
#    pool into configs/{host}/{instance}/scripts/ — no SSH involved, since
#    that directory lives on the qlsm controller itself. The next restart
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
from ui.runtime import host_runtime, runtime_extravars, runtime_paths
from .ansible_runner import _run_host_ansible_playbook


log = logging.getLogger(__name__)


def _pool_dir_for_host(host):
    """The ql-assets pool matching this host's runtime, e.g.
    ql-assets/data/minqlx-plugins/. Resolved through runtime_paths()'s
    asset_plugins_dir rather than a runtime == 'minqlx' check, so minqlx and
    minqlxtended-patched (which share this pool) don't need special-casing,
    and it keeps working once a third runtime shares it too."""
    pool_name = runtime_paths(host_runtime(host))['asset_plugins_dir']
    return os.path.abspath(os.path.join('ql-assets', 'data', pool_name))


def _copy_selected_plugin_files(host, instance, filenames):
    """Copies filenames from the ql-assets pool into this instance's
    selected-scripts directory. Returns (applied, skipped) filename lists.
    filenames are basenames only (os.path.basename applied defensively —
    this list ultimately comes from a JSON request body)."""
    pool_dir = _pool_dir_for_host(host)
    dest_dir = os.path.abspath(os.path.join('configs', host.name, str(instance.id), 'scripts'))
    os.makedirs(dest_dir, exist_ok=True)

    applied, skipped = [], []
    for raw_name in filenames:
        name = os.path.basename(raw_name)
        src = os.path.join(pool_dir, name)
        if not name or not os.path.isfile(src):
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
