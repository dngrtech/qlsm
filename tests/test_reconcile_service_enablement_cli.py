from unittest.mock import patch

from ui import db
from ui.models import Host, QLInstance, HostStatus, InstanceStatus
from ui.task_logic.ansible_instance_mgmt import STOP_SUCCESS_MARKER


def _make_host():
    host = Host(name="h1", provider="self", status=HostStatus.ACTIVE)
    db.session.add(host)
    db.session.commit()
    return host


def _make_instance(name, port, status, host):
    inst = QLInstance(
        name=name, port=port, hostname="hn", host_id=host.id, status=status
    )
    db.session.add(inst)
    db.session.commit()
    return inst


# Mirror stop_instance_logic's success return, built from the shared marker so a
# reworded message can't let this test drift out of sync with the CLI's detection.
SUCCESS = "Instance {{}} {marker}. Status: STOPPED".format(marker=STOP_SUCCESS_MARKER)


def test_reconcile_targets_only_stopped_instances(runner, app):
    with app.app_context():
        host = _make_host()
        s1 = _make_instance("s1", 27960, InstanceStatus.STOPPED, host)
        r1 = _make_instance("r1", 27961, InstanceStatus.RUNNING, host)
        s2 = _make_instance("s2", 27962, InstanceStatus.STOPPED, host)
        stopped_ids = {s1.id, s2.id}
        running_id = r1.id

    with patch(
        "ui.task_logic.ansible_instance_mgmt.stop_instance_logic",
        side_effect=lambda iid: SUCCESS.format(iid),
    ) as mock_stop:
        result = runner.invoke(args=["reconcile-service-enablement"])

    assert result.exit_code == 0
    called_ids = {c.args[0] for c in mock_stop.call_args_list}
    assert called_ids == stopped_ids
    assert running_id not in called_ids


def test_reconcile_no_op_when_no_stopped_instances(runner, app):
    with app.app_context():
        host = _make_host()
        _make_instance("r1", 27961, InstanceStatus.RUNNING, host)

    with patch("ui.task_logic.ansible_instance_mgmt.stop_instance_logic") as mock_stop:
        result = runner.invoke(args=["reconcile-service-enablement"])

    assert result.exit_code == 0
    mock_stop.assert_not_called()


def test_reconcile_failure_keeps_instance_stopped_and_exits_nonzero(runner, app):
    """A STOPPED instance on a failing/unreachable host must stay STOPPED (never
    ERROR), and the command must report the failure with a non-zero exit."""
    with app.app_context():
        host = _make_host()
        s1 = _make_instance("s1", 27960, InstanceStatus.STOPPED, host)
        s1_id = s1.id

    def _fail(instance_id):
        # Mirror stop_instance_logic's real failure behavior: it persists ERROR and
        # returns an error string (it never raises).
        inst = db.session.get(QLInstance, instance_id)
        inst.status = InstanceStatus.ERROR
        db.session.commit()
        return f"Error during instance {instance_id} stop: host unreachable"

    with patch(
        "ui.task_logic.ansible_instance_mgmt.stop_instance_logic", side_effect=_fail
    ):
        result = runner.invoke(args=["reconcile-service-enablement"])

    # Failure tally surfaced as a non-zero exit ...
    assert result.exit_code != 0
    # ... and the correctly-stopped instance is restored to STOPPED, never ERROR.
    with app.app_context():
        assert db.session.get(QLInstance, s1_id).status == InstanceStatus.STOPPED


def test_reconcile_mixed_success_and_failure(runner, app):
    """One instance succeeds, another fails in the same run: the command exits
    non-zero (partial failure), the failed instance is restored to STOPPED, and the
    succeeded instance is left STOPPED."""
    with app.app_context():
        host = _make_host()
        good = _make_instance("good", 27960, InstanceStatus.STOPPED, host)
        bad = _make_instance("bad", 27961, InstanceStatus.STOPPED, host)
        good_id = good.id
        bad_id = bad.id

    def _mixed(instance_id):
        if instance_id == bad_id:
            inst = db.session.get(QLInstance, instance_id)
            inst.status = InstanceStatus.ERROR
            db.session.commit()
            return f"Error during instance {instance_id} stop: host unreachable"
        return SUCCESS.format(instance_id)

    with patch(
        "ui.task_logic.ansible_instance_mgmt.stop_instance_logic", side_effect=_mixed
    ):
        result = runner.invoke(args=["reconcile-service-enablement"])

    # Any failure in the batch yields a non-zero exit ...
    assert result.exit_code != 0
    # ... the failed instance is restored to STOPPED (never left ERROR) ...
    with app.app_context():
        assert db.session.get(QLInstance, bad_id).status == InstanceStatus.STOPPED
        # ... and the succeeded instance is unchanged (STOPPED).
        assert db.session.get(QLInstance, good_id).status == InstanceStatus.STOPPED
