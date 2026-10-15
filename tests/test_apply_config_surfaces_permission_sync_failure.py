"""apply_instance_config_logic and deploy_instance_logic write admin level
changes to Redis after success, and surface a failed write in the instance log
instead of reporting the task as fully successful."""
from types import SimpleNamespace

import pytest

from ui import db
from ui.models import Host, InstanceStatus, QLInstance
from ui.task_logic import ansible_instance_mgmt as mod


@pytest.fixture
def instance_in_db(app, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "CONFIGS_BASE", str(tmp_path / "configs"), raising=False)
    with app.app_context():
        host = Host(name="test-host", provider="vultr", ip_address="10.0.0.1")
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(
            name="ti", port=27960, hostname="hn", host_id=host.id, qlx_plugins="",
            status=InstanceStatus.RUNNING,
            zmq_rcon_port=28888, zmq_rcon_password="x",
            zmq_stats_port=29999, zmq_stats_password="y",
        )
        db.session.add(inst)
        db.session.commit()
        yield inst


def _mock_successful_run(instance, playbook, extravars=None):
    return SimpleNamespace(rc=0, status="successful", stdout=lambda: "", _stdout="", _stderr=""), None


@pytest.fixture(autouse=True)
def _stub_ansible(monkeypatch):
    monkeypatch.setattr(mod, "_run_ansible_playbook", _mock_successful_run)
    monkeypatch.setattr(mod, "_prepare_instance_zmq", lambda inst: None)
    monkeypatch.setattr(mod, "ensure_instance_cpu_affinity", lambda inst: None)
    monkeypatch.setattr(mod, "with_self_host_network_extravars", lambda inst, e: e)
    monkeypatch.setattr(mod, "get_current_job", lambda: SimpleNamespace(id="test-job"))


ADMIN = "76561198012345678"


def _capture_writes(monkeypatch, result):
    from ui.task_logic import access_permission_sync

    calls = []
    monkeypatch.setattr(
        access_permission_sync, "write_admin_levels",
        lambda inst, changes: calls.append((inst.id, changes)) or (result if changes else None),
    )
    return calls


def test_apply_config_writes_only_the_passed_changes(app, instance_in_db, monkeypatch):
    calls = _capture_writes(monkeypatch, {"written": [ADMIN]})
    with app.app_context():
        mod.apply_instance_config_logic(instance_in_db.id, admin_levels={ADMIN: 0})
        refreshed = db.session.get(QLInstance, instance_in_db.id)
        assert calls == [(instance_in_db.id, {ADMIN: 0})]
        assert "could not be written" not in refreshed.logs


def test_apply_config_without_admin_changes_leaves_redis_alone(app, instance_in_db, monkeypatch):
    """No forcing: a save or restart that did not touch admins writes nothing."""
    calls = _capture_writes(monkeypatch, False)
    with app.app_context():
        mod.apply_instance_config_logic(instance_in_db.id)
        refreshed = db.session.get(QLInstance, instance_in_db.id)
        assert calls == [(instance_in_db.id, None)]
        assert "could not be written" not in refreshed.logs


def test_apply_config_warns_operator_when_the_write_fails(app, instance_in_db, monkeypatch):
    _capture_writes(monkeypatch, False)
    with app.app_context():
        result = mod.apply_instance_config_logic(instance_in_db.id, admin_levels={ADMIN: 4})
        refreshed = db.session.get(QLInstance, instance_in_db.id)
        assert "successful" in result
        assert "could not be written" in refreshed.logs


def test_deploy_writes_the_create_form_admins(app, instance_in_db, monkeypatch):
    calls = _capture_writes(monkeypatch, {"written": [ADMIN]})
    with app.app_context():
        result = mod.deploy_instance_logic(instance_in_db.id, admin_levels={ADMIN: 4})
        refreshed = db.session.get(QLInstance, instance_in_db.id)
        assert "successful" in result
        assert calls == [(instance_in_db.id, {ADMIN: 4})]
        assert refreshed.status == InstanceStatus.RUNNING


def test_deploy_announces_the_config_to_addons_like_an_apply(app, instance_in_db, monkeypatch):
    """A new instance must reach addons through instance.config_applied too:
    the telemetry relay builds its routing table from that hook, so an id set
    in the create form would otherwise stay unrouted until the first Apply."""
    _capture_writes(monkeypatch, False)
    hooks = []
    monkeypatch.setattr(mod, "_addon_contributions", lambda hook, inst: hooks.append((hook, inst.id)) or [])
    with app.app_context():
        mod.deploy_instance_logic(instance_in_db.id)
        assert ("instance.config_applied", instance_in_db.id) in hooks
