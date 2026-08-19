"""qlx_pluginsPath, LD_PRELOAD composition and log filenames all follow the
host's runtime."""
import re

import pytest

from ui import db
from ui.models import Host, InstanceStatus, QLInstance
from ui.runtime import MINQLX, MINQLXTENDED
from ui.task_logic import ansible_instance_mgmt as mod


def _instance(app, runtime, port, *, lan_rate=True, hook_migrated=True, name="h"):
    with app.app_context():
        host = Host(name=f"{name}-{runtime}", provider="vultr", ip_address="1.1.1.1",
                    runtime=runtime, lan_rate_uses_hook=hook_migrated)
        db.session.add(host)
        db.session.flush()
        inst = QLInstance(
            name="i", port=port, hostname="hn", host_id=host.id,
            lan_rate_enabled=lan_rate, status=InstanceStatus.RUNNING,
            zmq_rcon_port=28888, zmq_rcon_password="a",
            zmq_stats_port=29999, zmq_stats_password="b",
        )
        db.session.add(inst)
        db.session.commit()
        db.session.refresh(inst)
        return inst


def test_qlx_plugins_path_follows_the_runtime(app):
    inst = _instance(app, MINQLXTENDED, 27960)
    with app.app_context():
        args = mod._build_qlds_args_string(db.session.get(QLInstance, inst.id))
    assert "+set qlx_pluginsPath /home/ql/qlds-27960/minqlxtended-plugins" in args
    assert "minqlx-plugins" not in args


def test_qlx_plugins_path_unchanged_for_minqlx(app):
    inst = _instance(app, MINQLX, 27961)
    with app.app_context():
        args = mod._build_qlds_args_string(db.session.get(QLInstance, inst.id))
    assert "+set qlx_pluginsPath /home/ql/qlds-27961/minqlx-plugins" in args


def test_force_rate_never_loads_on_minqlxtended(app):
    """minqlxtended hooks Sys_IsLANAddress itself; loading force_rate.so too is
    a startup-abort race decided by glibc constructor order."""
    inst = _instance(app, MINQLXTENDED, 27962)
    with app.app_context():
        paths = mod._build_ld_preload_paths(db.session.get(QLInstance, inst.id))
    assert "force_rate.so" not in paths


def test_force_rate_still_loads_on_minqlx(app):
    inst = _instance(app, MINQLX, 27963)
    with app.app_context():
        paths = mod._build_ld_preload_paths(db.session.get(QLInstance, inst.id))
    assert "/home/ql/qlds-27963/system-hooks/force_rate.so" in paths


def test_force_rate_stays_a_reserved_upload_name_on_every_runtime():
    """The upload block is about filename collisions, not about runtimes."""
    assert "force_rate.so" in mod.RESERVED_HOOK_FILENAMES


def test_legacy_scripts_hooks_resolve_into_the_runtime_plugins_dir(tmp_path):
    from ui.task_logic.hook_paths import resolve_user_hook

    inst_dir = tmp_path / "hostA" / "7" / "scripts"
    inst_dir.mkdir(parents=True)
    (inst_dir / "legacy.so").write_bytes(b"\x7fELF")

    resolved = resolve_user_hook(str(tmp_path), "hostA", 7, "legacy.so",
                                 runtime=MINQLXTENDED)
    assert resolved["host_subdir"] == "minqlxtended-plugins"

    resolved = resolve_user_hook(str(tmp_path), "hostA", 7, "legacy.so")
    assert resolved["host_subdir"] == "minqlx-plugins"


def test_user_hooks_dir_is_runtime_independent(tmp_path):
    """user-hooks/ is QLSM's own directory and never carried a runtime name."""
    from ui.task_logic.hook_paths import resolve_user_hook

    inst_dir = tmp_path / "hostB" / "8" / "user-hooks"
    inst_dir.mkdir(parents=True)
    (inst_dir / "new.so").write_bytes(b"\x7fELF")

    for runtime in (MINQLX, MINQLXTENDED):
        assert resolve_user_hook(str(tmp_path), "hostB", 8, "new.so",
                                 runtime=runtime)["host_subdir"] == "user-hooks"


@pytest.mark.parametrize("runtime,good,bad", [
    (MINQLX, "minqlx.log", "minqlxtended.log"),
    (MINQLXTENDED, "minqlxtended.log", "minqlx.log"),
])
def test_log_request_validation_is_runtime_scoped(app, runtime, good, bad):
    inst = _instance(app, runtime, 27970 if runtime == MINQLX else 27971, name="log")
    with app.app_context():
        instance = db.session.get(QLInstance, inst.id)
        assert mod._validate_minqlx_log_request("lines", 100, good, instance) is None
        assert mod._validate_minqlx_log_request("lines", 100, bad, instance) is not None


def test_default_log_filename_follows_the_runtime(app):
    inst = _instance(app, MINQLXTENDED, 27972, name="dflt")
    with app.app_context():
        from ui.runtime import runtime_paths
        instance = db.session.get(QLInstance, inst.id)
        assert runtime_paths(instance.host.runtime)["log_filename"] == "minqlxtended.log"


def test_log_list_playbook_matches_both_runtimes():
    from pathlib import Path

    text = Path("ansible/playbooks/list_minqlx_logs.yml").read_text()
    assert "log_filename" in text
    assert 'patterns: "minqlx.log*"' not in text
