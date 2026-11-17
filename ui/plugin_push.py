# ui/plugin_push.py
#
# Fans a common-pool refresh out to every host that should receive a plugin
# that just landed in the operator tier of the shared pool
# (data/shared-plugins/<runtime>/, see ui/plugin_pool.py). Each host gets the
# same RQ job "Check for Updates -> Update Selected" would enqueue with only
# the common-pool box ticked (ui/task_logic/ansible_plugin_update.py), so
# lock, failure handler and host-log behaviour are identical to that flow.
#
# Only ACTIVE hosts of a matching runtime are touched. Anything else is
# reported back as skipped with a reason so the UI can tell the operator
# which hosts still need a manual Check for Updates.

import logging
import uuid

from ui.database import get_hosts
from ui.models import HostStatus
from ui.runtime import host_runtime
from ui.runtime_upgrade_guard import active_runtime_upgrade
from ui.task_lock import acquire_lock, release_lock
from ui.task_logic.job_failure_handlers import host_job_failure_handler
from ui.tasks import apply_plugin_updates_task, enqueue_task

log = logging.getLogger(__name__)

# Same TTL as apply_plugin_updates_api in ui/routes/host_routes.py.
PUSH_LOCK_TTL = 240


def push_pool_to_hosts(runtimes):
    """Enqueue a common-pool refresh on every ACTIVE host whose runtime is in
    `runtimes`. Returns {"queued": [{"id", "name"}],
    "skipped": [{"id", "name", "reason"}]}. Never raises for a single host's
    failure: that host is reported as skipped and the rest still go out."""
    result = {"queued": [], "skipped": []}
    runtimes = set(runtimes or ())
    if not runtimes:
        return result

    for host in get_hosts():
        if host_runtime(host) not in runtimes:
            continue
        if host.status != HostStatus.ACTIVE:
            result["skipped"].append({"id": host.id, "name": host.name, "reason": f"status: {host.status.name}"})
            continue
        if active_runtime_upgrade(host.id) is not None:
            result["skipped"].append({"id": host.id, "name": host.name, "reason": "runtime upgrade in progress"})
            continue

        token = str(uuid.uuid4())
        # acquire_lock talks to Redis, so it raises when Redis is down. The
        # plugin files are already in the pool by the time we get here, so a
        # dead Redis must skip this host, not fail the operator's download.
        try:
            locked = acquire_lock('host', host.id, token, ttl=PUSH_LOCK_TTL)
        except Exception:
            log.exception(f"push_pool_to_hosts: could not take the host lock for host {host.name}")
            result["skipped"].append({"id": host.id, "name": host.name, "reason": "lock unavailable"})
            continue
        if not locked:
            result["skipped"].append({"id": host.id, "name": host.name, "reason": "busy"})
            continue
        try:
            enqueue_task(
                apply_plugin_updates_task, host.id, True, {}, [],
                lock_token=token, on_failure=host_job_failure_handler,
            )
        except Exception:
            # Whatever broke the enqueue (usually Redis) breaks the release too,
            # so the best effort here must not escape either.
            try:
                release_lock('host', host.id, token)
            except Exception:
                log.exception(f"push_pool_to_hosts: could not release the host lock for host {host.name}")
            log.exception(f"push_pool_to_hosts: could not enqueue common pool refresh for host {host.name}")
            result["skipped"].append({"id": host.id, "name": host.name, "reason": "enqueue failed"})
            continue
        log.info(f"push_pool_to_hosts: queued common pool refresh for host {host.name}")
        result["queued"].append({"id": host.id, "name": host.name})

    return result
