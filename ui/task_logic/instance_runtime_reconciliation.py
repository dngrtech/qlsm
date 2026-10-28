"""Race-safe reconciliation of observed QLDS runtime identities."""

import logging
from dataclasses import dataclass

from sqlalchemy import select, update

from ui import db
from ui.models import InstanceStatus, QLInstance
from ui.pending_changes import clear_pending_changes
from ui.task_logic.common import append_log
from ui.task_logic.service_runtime import observation_has_fresh_status


logger = logging.getLogger(__name__)
ELIGIBLE_STATUSES = frozenset({InstanceStatus.RUNNING, InstanceStatus.UPDATED})
RESTART_CONFIRMED_LOG = (
    "Confirmed service restart; pending configuration is now active. Status: running."
)


@dataclass(frozen=True)
class RuntimeSnapshot:
    id: int
    status: InstanceStatus
    runtime_invocation_id: str | None


def _read_runtime_snapshot(instance_id):
    row = db.session.execute(
        select(
            QLInstance.id,
            QLInstance.status,
            QLInstance.runtime_invocation_id,
        ).where(QLInstance.id == instance_id)
    ).one_or_none()
    return RuntimeSnapshot(*row) if row is not None else None


def _guarded_runtime_update(snapshot, values):
    baseline_match = (
        QLInstance.runtime_invocation_id.is_(None)
        if snapshot.runtime_invocation_id is None
        else QLInstance.runtime_invocation_id == snapshot.runtime_invocation_id
    )
    statement = (
        update(QLInstance)
        .where(
            QLInstance.id == snapshot.id,
            QLInstance.status == snapshot.status,
            baseline_match,
        )
        .values(**values)
    )
    return db.session.execute(statement).rowcount == 1


def _observed_identity(observation):
    """Normalize an identity already validated by the freshness predicate."""
    return observation.invocation_id.strip().lower()


def _reconcile_observation(instance_id, observation):
    snapshot = _read_runtime_snapshot(instance_id)
    if snapshot is None or snapshot.status not in ELIGIBLE_STATUSES:
        return False, False, False

    observed_identity = _observed_identity(observation)
    if snapshot.runtime_invocation_id is None:
        changed = _guarded_runtime_update(
            snapshot, {"runtime_invocation_id": observed_identity}
        )
        return True, changed, False
    if snapshot.runtime_invocation_id == observed_identity:
        return False, False, False
    if snapshot.status is InstanceStatus.RUNNING:
        changed = _guarded_runtime_update(
            snapshot, {"runtime_invocation_id": observed_identity}
        )
        return True, changed, False

    changed = _guarded_runtime_update(
        snapshot,
        {
            "status": InstanceStatus.RUNNING,
            "runtime_invocation_id": observed_identity,
        },
    )
    if not changed:
        return True, False, False

    # The new invocation loaded every deferred change; drop their records.
    clear_pending_changes(snapshot.id)
    promoted = db.session.get(QLInstance, snapshot.id, populate_existing=True)
    if promoted is not None:
        append_log(promoted, RESTART_CONFIRMED_LOG)
    return True, True, True


def reconcile_runtime_observations(instances, observations):
    """Apply safe identity reconciliation for one successfully polled host."""
    attempted = False
    wrote = False
    promotions = 0
    try:
        for instance in instances:
            observation = observations.get(str(instance.port))
            if not observation_has_fresh_status(observation):
                continue
            attempted_cas, changed, promoted = _reconcile_observation(
                instance.id, observation
            )
            attempted = attempted or attempted_cas
            wrote = wrote or changed
            promotions += int(promoted)
        if wrote:
            db.session.commit()
        elif attempted:
            db.session.rollback()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to reconcile runtime observations")
        return 0
    return promotions
