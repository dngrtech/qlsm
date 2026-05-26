from types import SimpleNamespace

import pytest

from ui import db
from ui.models import Host, QLInstance
from ui.task_logic import ansible_instance_mgmt as mod


@pytest.fixture
def instance_in_db(app, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "CONFIGS_BASE", str(tmp_path / "configs"), raising=False)
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
        # Put legacy files in scripts/ so they resolve via the legacy fallback
        scripts = tmp_path / "configs" / host.name / str(inst.id) / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "hook_a.so").write_bytes(b"\x7fELF")
        (scripts / "hook_b.so").write_bytes(b"\x7fELF")
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

    # Legacy files in scripts/ resolve to minqlx-plugins/ on the host
    expected = (
        "/home/ql/qlds-27960/minqlx-plugins/hook_a.so:"
        "/home/ql/qlds-27960/minqlx-plugins/hook_b.so"
    )
    assert captured["extravars"]["ld_preload_paths"] == expected


def test_build_ld_preload_uses_user_hooks_dir_when_present(tmp_path, app, monkeypatch):
    """Files in user-hooks/ resolve to the user-hooks host subdir."""
    from ui.models import Host, QLInstance, InstanceStatus, db
    from ui.task_logic import ansible_instance_mgmt
    from ui.task_logic.ansible_instance_mgmt import _build_ld_preload_paths

    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path / "configs"), raising=False)
    inst_dir = tmp_path / "configs" / "hostA" / "5"
    (inst_dir / "user-hooks").mkdir(parents=True)
    (inst_dir / "user-hooks" / "new.so").write_bytes(b"\x7fELF")
    (inst_dir / "scripts").mkdir(parents=True)
    (inst_dir / "scripts" / "legacy.so").write_bytes(b"\x7fELF")

    with app.app_context():
        host = Host(name="hostA", provider="vultr", ip_address="1.1.1.1", lan_rate_uses_hook=False)
        db.session.add(host); db.session.flush()
        inst = QLInstance(
            id=5, name="i", port=27970, hostname="h", host_id=host.id,
            ld_preload_hooks="new.so,legacy.so",
            status=InstanceStatus.RUNNING,
            zmq_rcon_port=28001, zmq_rcon_password="a",
            zmq_stats_port=29001, zmq_stats_password="b",
        )
        db.session.add(inst); db.session.commit()
        result = _build_ld_preload_paths(inst)

    assert "/home/ql/qlds-27970/user-hooks/new.so" in result
    assert "/home/ql/qlds-27970/minqlx-plugins/legacy.so" in result


def test_build_ld_preload_skips_and_warns_when_file_missing(tmp_path, app, monkeypatch, caplog):
    """When a hook is missing from both user-hooks/ and scripts/, the entry is
    skipped (not emitted as a dead path) and a warning is logged."""
    import logging
    from ui.models import Host, QLInstance, InstanceStatus, db
    from ui.task_logic import ansible_instance_mgmt
    from ui.task_logic.ansible_instance_mgmt import _build_ld_preload_paths

    monkeypatch.setattr(ansible_instance_mgmt, "CONFIGS_BASE", str(tmp_path / "configs"), raising=False)
    inst_dir = tmp_path / "configs" / "hostB" / "6"
    (inst_dir / "user-hooks").mkdir(parents=True)
    (inst_dir / "scripts").mkdir(parents=True)
    # No file written — hook is missing from both dirs.

    with app.app_context():
        host = Host(name="hostB", provider="vultr", ip_address="2.2.2.2", lan_rate_uses_hook=False)
        db.session.add(host); db.session.flush()
        inst = QLInstance(
            id=6, name="j", port=27971, hostname="h", host_id=host.id,
            ld_preload_hooks="ghost.so",
            status=InstanceStatus.RUNNING,
            zmq_rcon_port=28002, zmq_rcon_password="a",
            zmq_stats_port=29002, zmq_stats_password="b",
        )
        db.session.add(inst); db.session.commit()
        with caplog.at_level(logging.WARNING):
            result = _build_ld_preload_paths(inst)

    assert "ghost.so" not in result
    assert any("ghost.so" in r.message for r in caplog.records)
