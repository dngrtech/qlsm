"""Host setup rebuilds the host's own runtime on every run, forever."""
import json
from types import SimpleNamespace

import pytest
import yaml

from ui import db
from ui.models import Host, HostStatus
from ui.runtime import MINQLX, MINQLXTENDED


def _load_playbook(path):
    with open(path) as handle:
        return yaml.safe_load(handle)


def test_setup_playbook_defaults_to_minqlx():
    """A manual ansible-playbook run with no extra-vars must not silently
    switch an existing host's runtime."""
    play = _load_playbook("ansible/playbooks/setup_host.yml")[0]
    assert play["vars"]["runtime"] == "minqlx"


def test_setup_playbook_derives_paths_from_runtime():
    play = _load_playbook("ansible/playbooks/setup_host.yml")[0]
    text = json.dumps(play["vars"])
    assert "minqlxtended" in text
    assert "runtime_shared_dir" in play["vars"]
    assert "runtime_plugins_dirname" in play["vars"]


def test_setup_playbook_gates_both_build_paths():
    """Neither build block may run unconditionally, or a re-run would install
    the wrong engine over the right one."""
    play = _load_playbook("ansible/playbooks/setup_host.yml")[0]
    clones = [t for t in play["tasks"] if "git" in t]
    assert len(clones) == 2, "expected one clone task per runtime"
    whens = " ".join(str(t.get("when", "")) for t in clones)
    assert "runtime == 'minqlx'" in whens
    assert "runtime == 'minqlxtended'" in whens


def test_minqlx_patches_never_apply_to_minqlxtended():
    """Both local C patches are obsolete on minqlxtended -- damage is a native
    event and reset_acc becomes pure Python."""
    play = _load_playbook("ansible/playbooks/setup_host.yml")[0]
    patch_tasks = [t for t in play["tasks"] if "patch" in t.get("name", "").lower()]
    assert patch_tasks
    for task in patch_tasks:
        assert "runtime == 'minqlx'" in str(task.get("when", "")), task["name"]


@pytest.mark.parametrize("runtime,expected", [
    (MINQLX, "minqlx"),
    (MINQLXTENDED, "minqlxtended"),
    (None, "minqlx"),
])
def test_cloud_host_setup_passes_the_runtime(app, monkeypatch, runtime, expected):
    """Reaching the ansible-playbook Popen call also requires ssh_key_path,
    a "found" inventory snippet, and a mocked wait-for-SSH subprocess.run --
    see the equivalent _run_cloud_setup() helper in
    tests/test_host_setup_firewall_pool_flag.py for the same, already-working
    pattern."""
    import ui.task_logic.ansible_host_setup as mod

    with app.app_context():
        host = Host(name=f"setup-{expected}-{runtime}", provider="vultr",
                    ip_address="10.0.0.5", ssh_key_path="/key", ssh_user="ansible",
                    status=HostStatus.PROVISIONED_PENDING_SETUP)
        if runtime is not None:
            host.runtime = runtime
        db.session.add(host)
        db.session.commit()
        host_id = host.id

    captured = {}

    class FakeProcess:
        returncode = 0
        stdout = stderr = None

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return FakeProcess()

    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(mod.subprocess, "run",
                         lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(mod.os.path, "exists", lambda path: True)
    monkeypatch.setattr("ui.task_logic.ansible_runner._stream_output", lambda p: ("", ""))
    monkeypatch.setattr(mod, "get_current_job", lambda: SimpleNamespace(id="job"))

    with app.app_context():
        try:
            mod.setup_host_ansible_logic(host_id)
        except Exception:
            pass

    joined = " ".join(captured.get("args", []))
    assert f'"runtime": "{expected}"' in joined or f"runtime={expected}" in joined


@pytest.mark.parametrize("runtime,expected", [
    (MINQLX, "minqlx"),
    (MINQLXTENDED, "minqlxtended"),
])
def test_standalone_setup_extra_vars_include_the_runtime(app, runtime, expected):
    from ui.task_logic.standalone_host_setup import _setup_playbook_extra_vars

    with app.app_context():
        host = Host(name=f"sa-{expected}", provider="standalone", ssh_port=22,
                    is_standalone=True, runtime=runtime)
        db.session.add(host)
        db.session.commit()
        assert _setup_playbook_extra_vars(host)["runtime"] == expected


def test_minqlxtended_requirements_pin_the_redis_floors():
    """Upstream needs redis>=5.1 and hiredis>=3.0; the bundled minqlx floor is
    a different, incompatible range."""
    with open("ql-assets/data/minqlxtended-plugins/requirements.txt") as handle:
        text = handle.read()
    assert "redis>=5.1" in text.replace(" ", "")
    assert "hiredis>=3.0" in text.replace(" ", "")
