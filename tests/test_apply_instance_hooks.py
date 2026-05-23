import os
from types import SimpleNamespace

import pytest

from ui import db
from ui.models import Host, InstanceStatus, QLInstance
from ui.task_logic import ansible_instance_hooks as mod


@pytest.fixture
def instance_with_so(app, tmp_path, monkeypatch):
    with app.app_context():
        host = Host(name="h", provider="vultr", ip_address="1.2.3.4")
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(
            name="i",
            port=27960,
            hostname="hn",
            host_id=host.id,
            qlx_plugins="",
            ld_preload_hooks="ok.so",
            zmq_rcon_port=28888,
            zmq_rcon_password="x",
            zmq_stats_port=29999,
            zmq_stats_password="y",
        )
        db.session.add(inst)
        db.session.commit()

        scripts_dir = tmp_path / "configs" / host.name / str(inst.id) / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "ok.so").write_bytes(b"\x7fELF" + b"\x00" * 64)
        monkeypatch.setattr(mod, "CONFIGS_BASE", str(tmp_path / "configs"))
        monkeypatch.setattr(mod, "ensure_instance_cpu_affinity", lambda inst: None)
        yield inst


def _success_result():
    return SimpleNamespace(rc=0, status="successful")


def test_success_restarts_and_sets_running(app, instance_with_so, monkeypatch):
    monkeypatch.setattr(
        mod,
        "_run_ansible_playbook",
        lambda inst, pb, extravars=None: (_success_result(), None),
    )
    with app.app_context():
        assert mod.apply_instance_hooks_logic(instance_with_so.id) is True
        fresh = db.session.get(QLInstance, instance_with_so.id)
        assert fresh.status == InstanceStatus.RUNNING


def test_success_when_stopped_skips_restart_and_sets_stopped(app, instance_with_so, monkeypatch):
    captured = {}

    def fake_run(inst, pb, extravars=None):
        captured["extravars"] = extravars
        return _success_result(), None

    monkeypatch.setattr(mod, "_run_ansible_playbook", fake_run)
    with app.app_context():
        assert mod.apply_instance_hooks_logic(instance_with_so.id, restart_service=False) is True
        fresh = db.session.get(QLInstance, instance_with_so.id)
        assert fresh.status == InstanceStatus.STOPPED
        assert captured["extravars"]["restart_service"] is False


def test_preserves_cpu_affinity_extravars(app, instance_with_so, monkeypatch):
    captured = {}
    monkeypatch.setattr(mod, "ensure_instance_cpu_affinity", lambda inst: 2)

    def fake_run(inst, pb, extravars=None):
        captured["extravars"] = extravars
        return _success_result(), None

    monkeypatch.setattr(mod, "_run_ansible_playbook", fake_run)
    with app.app_context():
        assert mod.apply_instance_hooks_logic(instance_with_so.id) is True
        assert captured["extravars"]["cpu_affinity"] == 2


def test_preflight_fail_when_file_missing(app, instance_with_so, monkeypatch, tmp_path):
    os.remove(tmp_path / "configs" / "h" / str(instance_with_so.id) / "scripts" / "ok.so")
    called = {"ran": False}

    def fake_run(*args, **kwargs):
        called["ran"] = True
        return _success_result(), None

    monkeypatch.setattr(mod, "_run_ansible_playbook", fake_run)
    with app.app_context():
        assert mod.apply_instance_hooks_logic(instance_with_so.id) is False
        fresh = db.session.get(QLInstance, instance_with_so.id)
        assert fresh.status == InstanceStatus.ERROR
        assert called["ran"] is False


def test_preflight_fail_when_non_elf(app, instance_with_so, monkeypatch, tmp_path):
    bad = tmp_path / "configs" / "h" / str(instance_with_so.id) / "scripts" / "ok.so"
    bad.write_bytes(b"NOT_ELF")
    monkeypatch.setattr(
        mod,
        "_run_ansible_playbook",
        lambda *args, **kwargs: (_success_result(), None),
    )
    with app.app_context():
        assert mod.apply_instance_hooks_logic(instance_with_so.id) is False
        fresh = db.session.get(QLInstance, instance_with_so.id)
        assert fresh.status == InstanceStatus.ERROR


def test_ansible_failure_sets_error(app, instance_with_so, monkeypatch):
    monkeypatch.setattr(
        mod,
        "_run_ansible_playbook",
        lambda *args, **kwargs: (None, "boom"),
    )
    with app.app_context():
        assert mod.apply_instance_hooks_logic(instance_with_so.id) is False
        fresh = db.session.get(QLInstance, instance_with_so.id)
        assert fresh.status == InstanceStatus.ERROR
