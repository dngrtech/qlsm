from types import SimpleNamespace

import pytest

from ui import db
from ui.models import Host, QLInstance
from ui.task_logic import ansible_instance_mgmt as mod


@pytest.fixture
def instance_in_db(app):
    with app.app_context():
        host = Host(name="test-host", provider="vultr", ip_address="10.0.0.1")
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(
            name="ti",
            port=27960,
            hostname="hn",
            host_id=host.id,
            qlx_plugins="",
            ld_preload_hooks="hook_a.so,hook_b.so",
            zmq_rcon_port=28888,
            zmq_rcon_password="x",
            zmq_stats_port=29999,
            zmq_stats_password="y",
        )
        db.session.add(inst)
        db.session.commit()
        yield inst


@pytest.mark.parametrize("logic_fn", [
    "deploy_instance_logic",
    "restart_instance_logic",
    "apply_instance_config_logic",
    "reconfigure_instance_lan_rate_logic",
])
def test_each_logic_passes_ld_preload_paths(app, instance_in_db, logic_fn, monkeypatch):
    captured = {}

    def fake_run(instance, playbook, extravars=None):
        captured["extravars"] = extravars
        return SimpleNamespace(rc=0, status="successful", stdout=lambda: ""), None

    monkeypatch.setattr(mod, "_run_ansible_playbook", fake_run)
    monkeypatch.setattr(mod, "_prepare_instance_zmq", lambda inst: None)
    monkeypatch.setattr(mod, "ensure_instance_cpu_affinity", lambda inst: None)
    monkeypatch.setattr(mod, "with_self_host_network_extravars", lambda inst, e: e)
    monkeypatch.setattr(mod, "get_current_job", lambda: SimpleNamespace(id="test-job"))

    with app.app_context():
        getattr(mod, logic_fn)(instance_in_db.id)

    expected = (
        "/home/ql/qlds-27960/minqlx-plugins/hook_a.so:"
        "/home/ql/qlds-27960/minqlx-plugins/hook_b.so"
    )
    assert captured["extravars"]["ld_preload_paths"] == expected
