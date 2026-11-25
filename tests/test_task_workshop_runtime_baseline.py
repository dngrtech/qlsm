from unittest.mock import MagicMock

from ui import db
from ui.database import create_host, get_instance
from ui.models import HostStatus, InstanceStatus, QLInstance
from ui.task_logic import ansible_workshop_update, instance_runtime_reconciliation
from ui.task_logic.service_runtime import RuntimeObservation


OLD_ID = "a" * 32
CURRENT_ID = "b" * 32
LATER_ID = "c" * 32


def _create_instances(statuses, baselines=None):
    host = create_host(
        name="workshop-baseline-host",
        provider="vultr",
        status=HostStatus.ACTIVE,
    )
    baselines = baselines or [None] * len(statuses)
    instances = [
        QLInstance(
            name=f"workshop-baseline-{index}",
            port=27960 + index,
            hostname=f"server-{index}",
            host_id=host.id,
            status=status,
            runtime_invocation_id=baseline,
        )
        for index, (status, baseline) in enumerate(zip(statuses, baselines), 1)
    ]
    db.session.add_all(instances)
    db.session.commit()
    return host, instances


def _configure_success(monkeypatch, probe):
    monkeypatch.setattr(
        ansible_workshop_update,
        "_run_host_ansible_playbook",
        MagicMock(return_value=(True, "ok", "")),
    )
    runtime = MagicMock()
    runtime.probe_host_invocation_ids = probe
    monkeypatch.setattr(
        ansible_workshop_update, "service_runtime", runtime, raising=False
    )
    queue = MagicMock()
    monkeypatch.setattr("ui.task_lock.acquire_lock", MagicMock(return_value=True))
    monkeypatch.setattr("ui.task_lock.release_lock", MagicMock())
    monkeypatch.setattr("ui.tasks.enqueue_task", queue)
    return queue


def _stored_instances(instances):
    return [get_instance(instance.id) for instance in instances]


def test_workshop_no_restart_captures_running_instance_baselines_in_one_probe(
    app, monkeypatch
):
    """Deferred Workshop updates use one current host-wide baseline probe."""
    with app.app_context():
        host, instances = _create_instances([InstanceStatus.RUNNING] * 2)
        probe = MagicMock(return_value={"27961": CURRENT_ID, "27962": LATER_ID})
        _configure_success(monkeypatch, probe)
        update = MagicMock(wraps=ansible_workshop_update.update_instance)
        monkeypatch.setattr(ansible_workshop_update, "update_instance", update)

        assert ansible_workshop_update.force_update_workshop_logic(host.id, "123456", [])

        assert probe.call_count == 1
        probe_host, pending = probe.call_args.args
        assert probe_host.id == host.id
        assert [instance.id for instance in pending] == [instance.id for instance in instances]
        final_updates = [
            call.kwargs for call in update.call_args_list
            if call.kwargs.get("status") == InstanceStatus.UPDATED
        ]
        assert [
            (values["status"], values["runtime_invocation_id"])
            for values in final_updates
        ] == [
            (InstanceStatus.UPDATED, CURRENT_ID),
            (InstanceStatus.UPDATED, LATER_ID),
        ]
        assert [instance.runtime_invocation_id for instance in _stored_instances(instances)] == [
            CURRENT_ID,
            LATER_ID,
        ]


def test_workshop_probe_failure_clears_baselines_but_preserves_success(app, monkeypatch):
    """An unusable batch probe clears old baselines without failing Workshop sync."""
    with app.app_context():
        host, instances = _create_instances([InstanceStatus.RUNNING], [OLD_ID])
        probe = MagicMock(return_value=None)
        _configure_success(monkeypatch, probe)

        assert ansible_workshop_update.force_update_workshop_logic(host.id, "123456", [])

        stored, = _stored_instances(instances)
        assert stored.status == InstanceStatus.UPDATED
        assert stored.runtime_invocation_id is None
        probe.assert_called_once()


def test_workshop_probe_exception_clears_baselines_but_preserves_success(app, monkeypatch):
    """A batch-probe exception cannot convert a successful Workshop task to ERROR."""
    with app.app_context():
        host, instances = _create_instances([InstanceStatus.RUNNING], [OLD_ID])
        probe = MagicMock(side_effect=OSError("runtime unavailable"))
        _configure_success(monkeypatch, probe)

        assert ansible_workshop_update.force_update_workshop_logic(host.id, "123456", [])

        stored, = _stored_instances(instances)
        assert stored.status == InstanceStatus.UPDATED
        assert stored.runtime_invocation_id is None
        probe.assert_called_once()


def test_workshop_no_restart_preserves_originally_stopped_instance(app, monkeypatch):
    """Workshop files update without probing or changing a stopped service's state."""
    with app.app_context():
        host, instances = _create_instances([InstanceStatus.STOPPED], [OLD_ID])
        probe = MagicMock(side_effect=AssertionError("stopped service must not probe"))
        queue = _configure_success(monkeypatch, probe)

        assert ansible_workshop_update.force_update_workshop_logic(host.id, "123456", [])

        stored, = _stored_instances(instances)
        assert stored.status == InstanceStatus.STOPPED
        assert stored.runtime_invocation_id == OLD_ID
        assert "Workshop 123456 updated while stopped; service left stopped." in stored.logs
        probe.assert_not_called()
        queue.assert_not_called()


def test_workshop_requested_restart_still_preserves_originally_stopped_instance(
    app, monkeypatch
):
    """A stale restart request cannot start or reclassify an originally stopped service."""
    with app.app_context():
        host, instances = _create_instances([InstanceStatus.STOPPED], [OLD_ID])
        probe = MagicMock(side_effect=AssertionError("stopped service must not probe"))
        queue = _configure_success(monkeypatch, probe)

        assert ansible_workshop_update.force_update_workshop_logic(
            host.id, "123456", [instances[0].id]
        )

        stored, = _stored_instances(instances)
        assert stored.status == InstanceStatus.STOPPED
        assert stored.runtime_invocation_id == OLD_ID
        assert "Workshop 123456 updated while stopped; service left stopped." in stored.logs
        probe.assert_not_called()
        queue.assert_not_called()


def test_workshop_baseline_does_not_credit_an_earlier_unobserved_restart(
    app, monkeypatch
):
    """Only an invocation after Workshop sync may promote its deferred update."""
    with app.app_context():
        host, instances = _create_instances([InstanceStatus.RUNNING], [OLD_ID])
        probe = MagicMock(return_value={"27961": CURRENT_ID})
        _configure_success(monkeypatch, probe)

        assert ansible_workshop_update.force_update_workshop_logic(host.id, "123456", [])
        stored, = _stored_instances(instances)
        assert stored.status == InstanceStatus.UPDATED
        assert stored.runtime_invocation_id == CURRENT_ID

        current = RuntimeObservation({"updated": 2}, CURRENT_ID, True, 1)
        assert instance_runtime_reconciliation.reconcile_runtime_observations(
            [stored], {"27961": current}
        ) == 0
        assert get_instance(stored.id).status == InstanceStatus.UPDATED

        later = RuntimeObservation({"updated": 2}, LATER_ID, True, 1)
        assert instance_runtime_reconciliation.reconcile_runtime_observations(
            [stored], {"27961": later}
        ) == 1
        promoted = get_instance(stored.id)
        assert promoted.status == InstanceStatus.RUNNING
        assert promoted.runtime_invocation_id == LATER_ID
