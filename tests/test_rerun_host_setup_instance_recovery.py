from types import SimpleNamespace

import pytest

from ui import db
from ui.models import Host, InstanceStatus, QLInstance
from ui.task_logic import instance_reconciliation as reconciliation
from ui.task_logic import common


@pytest.fixture
def reconciliation_instance(app):
    with app.app_context():
        host = Host(
            name="recovery-host",
            provider="vultr",
            ip_address="1.2.3.4",
            ssh_user="ansible",
            ssh_key_path="/tmp/recovery-key",
            lan_rate_uses_hook=True,
        )
        instance = QLInstance(
            name="recovery-instance",
            hostname="Recovery Server",
            port=27960,
            host=host,
            status=InstanceStatus.ERROR,
            lan_rate_enabled=True,
            qlx_plugins="",
            zmq_rcon_port=28888,
            zmq_rcon_password="rcon-secret",
            zmq_stats_port=29999,
            zmq_stats_password="stats-secret",
        )
        db.session.add_all([host, instance])
        db.session.commit()
        return instance.id


def _stub_reconciliation_dependencies(monkeypatch):
    monkeypatch.setattr(reconciliation, "_prepare_instance_zmq", lambda instance: None)
    monkeypatch.setattr(reconciliation, "ensure_instance_cpu_affinity", lambda instance: 2)
    monkeypatch.setattr(reconciliation, "_build_qlds_args_string", lambda instance: "qlds args")
    monkeypatch.setattr(
        reconciliation,
        "_build_ld_preload_paths",
        lambda instance: "/home/ql/qlds-27960/system-hooks/force_rate.so",
    )


@pytest.mark.parametrize(
    ("restart_service", "target_status"),
    [
        (False, InstanceStatus.STOPPED),
        (True, InstanceStatus.RUNNING),
    ],
)
def test_reconcile_instance_after_host_setup_commits_deterministic_target(
    app,
    reconciliation_instance,
    monkeypatch,
    restart_service,
    target_status,
):
    _stub_reconciliation_dependencies(monkeypatch)
    calls = []

    def fake_run(instance, playbook, extravars=None):
        calls.append((instance.id, playbook, extravars))
        return SimpleNamespace(rc=0, stdout=lambda: "ok"), None

    monkeypatch.setattr(reconciliation, "_run_ansible_playbook", fake_run)

    with app.app_context():
        result = reconciliation.reconcile_instance_after_host_setup(
            reconciliation_instance,
            restart_service=restart_service,
            target_status=target_status,
        )
        db.session.expire_all()
        fresh = db.session.get(QLInstance, reconciliation_instance)

    assert result is True
    assert fresh.status == target_status
    assert len(calls) == 1
    assert calls[0][1] == "sync_instance_configs_and_restart.yml"
    assert calls[0][2]["restart_service"] is restart_service
    assert calls[0][2]["keep_service_stopped"] is (not restart_service)


@pytest.mark.parametrize(
    ("restart_service", "target_status"),
    [
        (False, InstanceStatus.RUNNING),
        (True, InstanceStatus.STOPPED),
    ],
)
def test_reconcile_instance_after_host_setup_rejects_mismatched_target(
    app,
    reconciliation_instance,
    monkeypatch,
    restart_service,
    target_status,
):
    run_calls = []

    def fake_run(*args, **kwargs):
        run_calls.append((args, kwargs))
        return SimpleNamespace(rc=0, stdout=lambda: "ok"), None

    monkeypatch.setattr(reconciliation, "_run_ansible_playbook", fake_run)

    with app.app_context():
        result = reconciliation.reconcile_instance_after_host_setup(
            reconciliation_instance,
            restart_service=restart_service,
            target_status=target_status,
        )
        db.session.expire_all()
        fresh = db.session.get(QLInstance, reconciliation_instance)

    assert result is False
    assert fresh.status == InstanceStatus.ERROR
    assert run_calls == []


def test_reconcile_instance_after_host_setup_nonzero_rc_commits_error(
    app, reconciliation_instance, monkeypatch
):
    _stub_reconciliation_dependencies(monkeypatch)
    monkeypatch.setattr(
        reconciliation,
        "_run_ansible_playbook",
        lambda *args, **kwargs: (SimpleNamespace(rc=2, stdout=lambda: "failed"), None),
    )

    with app.app_context():
        result = reconciliation.reconcile_instance_after_host_setup(
            reconciliation_instance,
            restart_service=True,
            target_status=InstanceStatus.RUNNING,
        )
        db.session.expire_all()
        fresh = db.session.get(QLInstance, reconciliation_instance)

    assert result is False
    assert fresh.status == InstanceStatus.ERROR


def test_reconcile_instance_after_host_setup_missing_connection_details_commits_error(
    app, reconciliation_instance, monkeypatch
):
    _stub_reconciliation_dependencies(monkeypatch)

    with app.app_context():
        instance = db.session.get(QLInstance, reconciliation_instance)
        instance.host.ssh_key_path = None
        db.session.commit()

        result = reconciliation.reconcile_instance_after_host_setup(
            reconciliation_instance,
            restart_service=True,
            target_status=InstanceStatus.RUNNING,
        )
        db.session.expire_all()
        fresh = db.session.get(QLInstance, reconciliation_instance)

    assert result is False
    assert fresh.status == InstanceStatus.ERROR


def test_reconcile_instance_after_host_setup_unexpected_empty_runner_result_commits_error(
    app, reconciliation_instance, monkeypatch
):
    _stub_reconciliation_dependencies(monkeypatch)
    monkeypatch.setattr(
        reconciliation,
        "_run_ansible_playbook",
        lambda *args, **kwargs: (None, None),
    )

    with app.app_context():
        result = reconciliation.reconcile_instance_after_host_setup(
            reconciliation_instance,
            restart_service=True,
            target_status=InstanceStatus.RUNNING,
        )
        db.session.expire_all()
        fresh = db.session.get(QLInstance, reconciliation_instance)

    assert result is False
    assert fresh.status == InstanceStatus.ERROR


@pytest.mark.parametrize("failure_point", ["prepare", "runner"])
def test_reconcile_instance_after_host_setup_exception_commits_error(
    app, reconciliation_instance, monkeypatch, failure_point
):
    _stub_reconciliation_dependencies(monkeypatch)

    def raise_failure(*args, **kwargs):
        raise RuntimeError(f"{failure_point} exploded")

    if failure_point == "prepare":
        monkeypatch.setattr(reconciliation, "_prepare_instance_zmq", raise_failure)
        monkeypatch.setattr(reconciliation, "_run_ansible_playbook", pytest.fail)
    else:
        monkeypatch.setattr(reconciliation, "_run_ansible_playbook", raise_failure)

    with app.app_context():
        result = reconciliation.reconcile_instance_after_host_setup(
            reconciliation_instance,
            restart_service=True,
            target_status=InstanceStatus.RUNNING,
        )
        db.session.expire_all()
        fresh = db.session.get(QLInstance, reconciliation_instance)

    assert result is False
    assert fresh.status == InstanceStatus.ERROR


def test_reconcile_instance_after_host_setup_missing_instance_returns_false_without_commit(
    app, monkeypatch
):
    commit_calls = []
    monkeypatch.setattr(db.session, "commit", lambda: commit_calls.append(True))

    with app.app_context():
        result = reconciliation.reconcile_instance_after_host_setup(
            9999,
            restart_service=True,
            target_status=InstanceStatus.RUNNING,
        )

    assert result is False
    assert commit_calls == []


def test_host_reconciliation_snapshots_every_original_status_before_inner_commits(
    app, monkeypatch
):
    original_statuses = [
        InstanceStatus.STOPPED,
        InstanceStatus.RUNNING,
        InstanceStatus.RESTARTING,
        InstanceStatus.CONFIGURING,
        InstanceStatus.ERROR,
    ]
    with app.app_context():
        host = Host(
            name="snapshot-host",
            provider="vultr",
            lan_rate_uses_hook=False,
        )
        db.session.add(host)
        db.session.flush()
        instances = [
            QLInstance(
                name=f"snapshot-{index}",
                hostname=f"Snapshot {index}",
                port=27960 + index,
                host_id=host.id,
                status=status,
            )
            for index, status in enumerate(original_statuses)
        ]
        db.session.add_all(instances)
        db.session.commit()
        host_id = host.id
        original_by_id = {
            instance.id: instance.status for instance in instances
        }

    calls = []

    def fake_reconcile(instance_id, *, restart_service, target_status):
        calls.append((instance_id, restart_service, target_status))
        if len(calls) == 1:
            for instance in QLInstance.query.filter_by(host_id=host_id):
                instance.status = InstanceStatus.STOPPED
            db.session.commit()
        return True

    monkeypatch.setattr(
        reconciliation,
        "reconcile_instance_after_host_setup",
        fake_reconcile,
    )

    with app.app_context():
        host = db.session.get(Host, host_id)
        result = common._reconcile_host_instances_after_setup(host)
        db.session.expire_all()
        migrated_host = db.session.get(Host, host_id)

    assert result == (len(original_statuses), 0)
    assert migrated_host.lan_rate_uses_hook is True
    assert len(calls) == len(original_statuses)
    assert len({instance_id for instance_id, _, _ in calls}) == len(calls)

    actual_by_id = {
        instance_id: (restart_service, target_status)
        for instance_id, restart_service, target_status in calls
    }
    assert set(actual_by_id) == set(original_by_id)
    for instance_id, original_status in original_by_id.items():
        if original_status is InstanceStatus.STOPPED:
            assert actual_by_id[instance_id] == (
                False,
                InstanceStatus.STOPPED,
            )
        else:
            assert actual_by_id[instance_id] == (
                True,
                InstanceStatus.RUNNING,
            )


def test_host_reconciliation_counts_only_strict_true_as_success(app, monkeypatch):
    with app.app_context():
        host = Host(
            name="count-host",
            provider="vultr",
            lan_rate_uses_hook=False,
        )
        db.session.add(host)
        db.session.flush()
        instances = [
            QLInstance(
                name=f"count-{index}",
                hostname=f"Count {index}",
                port=27970 + index,
                host_id=host.id,
                status=InstanceStatus.RUNNING,
            )
            for index in range(3)
        ]
        db.session.add_all(instances)
        db.session.commit()
        host_id = host.id
        instance_ids = [instance.id for instance in instances]

    results = iter([True, False, "Instance restart successful"])
    monkeypatch.setattr(
        reconciliation,
        "reconcile_instance_after_host_setup",
        lambda *args, **kwargs: next(results),
    )

    with app.app_context():
        host = db.session.get(Host, host_id)
        result = common._reconcile_host_instances_after_setup(host)
        host_logs = host.logs or ""

    assert result == (1, 2)
    assert f"instance id={instance_ids[1]} reconciliation failed" in host_logs
    assert f"instance id={instance_ids[2]} reconciliation failed" in host_logs
