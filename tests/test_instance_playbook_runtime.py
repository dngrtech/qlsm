"""Every instance-level playbook must be told the host's runtime.

The systemd unit's ExecStart names the launch script, so a missed call site
renders a unit pointing at a file that does not exist.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ui import db
from ui.models import Host, InstanceStatus, QLInstance
from ui.runtime import MINQLXTENDED
from ui.task_logic import ansible_instance_mgmt as mod

SERVICE_TEMPLATE = "ansible/templates/qlds@.service.j2"


@pytest.fixture
def tended_instance(app, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "CONFIGS_BASE", str(tmp_path / "configs"), raising=False)
    with app.app_context():
        host = Host(name="tended-host", provider="vultr", ip_address="10.0.0.1",
                    runtime=MINQLXTENDED)
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(
            name="ti", port=27960, hostname="hn", host_id=host.id, qlx_plugins="",
            # Set an explicit status, matching the other tests in this area.
            # apply_instance_config_logic reads and rewrites instance.status, and
            # relying on the model default here would couple the test to it.
            status=InstanceStatus.RUNNING,
            zmq_rcon_port=28888, zmq_rcon_password="x",
            zmq_stats_port=29999, zmq_stats_password="y",
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
def test_each_logic_passes_runtime_extravars(app, tended_instance, logic_fn, monkeypatch):
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
        getattr(mod, logic_fn)(tended_instance.id)

    extravars = captured["extravars"]
    assert extravars["runtime"] == "minqlxtended"
    assert extravars["runtime_plugins_dirname"] == "minqlxtended-plugins"
    assert extravars["runtime_shared_dir"] == "/home/ql/minqlxtended-shared"
    assert extravars["launch_script"] == "run_server_x64_minqlxtended.sh"


def test_hook_update_logic_passes_runtime_extravars(app, tended_instance, monkeypatch):
    from ui.task_logic import ansible_instance_hooks as hooks_mod

    captured = {}

    def fake_run(instance, playbook, extravars=None):
        captured["extravars"] = extravars
        return SimpleNamespace(rc=0, status="successful", stdout=lambda: ""), None

    monkeypatch.setattr(hooks_mod, "_run_ansible_playbook", fake_run)

    with app.app_context():
        try:
            hooks_mod.apply_instance_hooks_logic(tended_instance.id)
        except Exception:
            pass

    assert captured["extravars"]["launch_script"] == "run_server_x64_minqlxtended.sh"


def test_service_template_no_longer_hardcodes_the_minqlx_launcher():
    text = Path(SERVICE_TEMPLATE).read_text()
    assert "run_server_x64_minqlx.sh " not in text
    assert "launch_script" in text


@pytest.mark.parametrize("playbook", [
    "ansible/playbooks/add_qlds_instance.yml",
    "ansible/playbooks/sync_instance_configs_and_restart.yml",
    "ansible/playbooks/update_instance_hooks.yml",
    "ansible/playbooks/update_instance_lan_rate.yml",
])
def test_every_service_rendering_playbook_defines_launch_script(playbook):
    """A playbook that renders the unit without defining launch_script would
    produce an ExecStart of an undefined path."""
    text = Path(playbook).read_text()
    assert "qlds@.service.j2" in text, "test targets the wrong playbook"

    play = yaml.safe_load(text)[0]
    assert "launch_script" in play["vars"], f"{playbook} does not define launch_script"
    assert "runtime" in play["vars"]


@pytest.mark.parametrize("playbook", [
    "ansible/playbooks/add_qlds_instance.yml",
    "ansible/playbooks/sync_instance_configs_and_restart.yml",
    "ansible/playbooks/update_instance_hooks.yml",
    "ansible/playbooks/tasks/install_minqlx_deps.yml",
])
def test_no_playbook_hardcodes_the_minqlx_plugins_dir(playbook):
    text = Path(playbook).read_text()
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "/minqlx-plugins" not in stripped, f"{playbook}:{line_number}: {stripped}"
