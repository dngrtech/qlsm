"""install_runtime.yml: the minimal minqlxtended installer for a runtime
upgrade. Static checks here; the executable run against a disposable
container lives in tests/test_runtime_upgrade_integration.py."""
import glob
import os

import yaml

PLAYBOOK = "ansible/playbooks/install_runtime.yml"
TASKS_DIR = "ansible/playbooks/tasks"


def _play():
    with open(PLAYBOOK) as handle:
        return yaml.safe_load(handle)[0]


def test_play_defaults_match_the_runtime_table():
    """The play's own defaults must not drift from ui.runtime, which the caller
    also passes as extra-vars."""
    from ui.runtime import MINQLXTENDED, runtime_paths

    target = runtime_paths(MINQLXTENDED)
    play_vars = _play()["vars"]
    assert play_vars["minqlxtended_git_repo"] == target["git_repo"]
    assert play_vars["minqlxtended_git_version"] == target["git_version"]
    assert play_vars["minqlxtended_shared_dir"] == target["shared_dir"]
    assert play_vars["runtime_plugins_dirname"] == target["plugins_dirname"]


def _flat(tasks):
    for task in tasks:
        yield task
        for key in ("block", "rescue", "always"):
            yield from _flat(task.get(key) or [])


def _code(text):
    """YAML without comment lines: the files explain what they avoid."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _imported_text(task_list):
    """The playbook text plus every task file it imports, transitively."""
    texts = []
    for task in _flat(task_list):
        target = task.get("ansible.builtin.import_tasks")
        if target:
            path = os.path.join("ansible/playbooks", target)
            with open(path) as handle:
                texts.append(_code(handle.read()))
            with open(path) as handle:
                texts.append(_imported_text(yaml.safe_load(handle) or []))
    return "\n".join(texts)


def _full_text():
    with open(PLAYBOOK) as handle:
        return _code(handle.read()) + "\n" + _imported_text(_play()["tasks"])


def test_python_floor_is_asserted_before_anything_else():
    first = _play()["tasks"][0]
    assert "ansible.builtin.assert" in first
    assert "ansible_python_version is version('3.12', '>=')" in first["ansible.builtin.assert"]["that"]


def test_lock_is_taken_before_any_side_effect_and_released_always():
    tasks = _play()["tasks"]
    assert tasks[1].get("ansible.builtin.import_tasks") == "tasks/runtime_op_lock.yml"
    body = tasks[2]
    assert "block" in body
    assert any(t.get("ansible.builtin.import_tasks") == "tasks/runtime_op_release.yml"
               for t in body["always"])


def test_never_reruns_host_setup_or_touches_network_firewall_or_redis():
    text = _full_text()
    assert "setup_host.yml" not in text
    for forbidden in ("iptables", "netplan", "sysctl", "/etc/hosts", "sshd", "redis.conf",
                      "redis-server", "lan_rate_uses_hook", "hostname:"):
        assert forbidden not in text, forbidden


def test_never_runs_system_pip():
    text = _full_text()
    play_vars = _play()["vars"]
    assert play_vars["skip_pip_install"] is True  # the shared pool sync's global pip
    assert "--break-system-packages" not in _code(open(PLAYBOOK).read())
    deps = _code(open(os.path.join(TASKS_DIR, "runtime_python_deps.yml")).read())
    assert "pip3" not in deps and "break-system-packages" not in deps
    assert "/bin/python', '-m', 'pip', 'install'" in deps
    assert "pip, check" in deps
    assert "ansible.builtin.pip" not in text


def test_apt_is_additive_only():
    play = _play()
    assert play["vars"]["runtime_build_packages"] == [
        "build-essential", "git", "python3-dev", "python3-pip", "python3-venv"]
    tasks = list(_flat(play["tasks"]))
    simulate = next(t for t in tasks if t.get("name") == "Refuse an apt transaction that would change installed packages")
    assert "--simulate" in simulate["ansible.builtin.script"]["cmd"]
    install = next(t for t in tasks if t.get("name") == "Install only the missing build prerequisites")
    assert install["ansible.builtin.apt"]["state"] == "present"
    assert install["ansible.builtin.apt"]["name"] == "{{ apt_missing }}"
    names = [t.get("name") for t in tasks]
    assert names.index(simulate["name"]) < names.index(install["name"])
    for task in tasks:
        apt = task.get("ansible.builtin.apt") or {}
        assert apt.get("upgrade") in (None, False, "no")
        assert apt.get("state", "present") == "present"


def test_builds_with_the_shared_patched_build_and_leaves_minqlx_alone():
    tasks = list(_flat(_play()["tasks"]))
    assert any(t.get("ansible.builtin.import_tasks") == "tasks/build_minqlxtended.yml" for t in tasks)
    text = _full_text()
    assert "minqlx_shared_dir" not in text
    assert "/home/ql/minqlx-shared" not in text


def test_common_pool_is_refreshed_from_captured_inputs_by_default_paths_unchanged():
    tasks = list(_flat(_play()["tasks"]))
    assert any(t.get("ansible.builtin.import_tasks") == "tasks/sync_common_plugins.yml" for t in tasks)
    shared = open(os.path.join(TASKS_DIR, "sync_common_plugins.yml")).read()
    assert "common_plugins_builtin_src | default(playbook_dir ~ '/../../ql-assets/data/' ~ runtime_plugins_dirname)" in shared
    assert "common_plugins_operator_src | default(playbook_dir ~ '/../../data/shared-plugins/' ~ runtime)" in shared


def test_venvs_are_operation_and_instance_scoped_without_system_site_packages():
    deps = open(os.path.join(TASKS_DIR, "runtime_python_deps.yml")).read()
    assert "'/minqlxtended/' ~ operation_id" in deps
    assert "--system-site-packages" not in deps
    assert "/usr/bin/python3, -m, venv" in deps
    assert "-lpython" in deps  # same ABI as the engine build


def test_ordinary_setup_still_imports_shared_tasks():
    with open("ansible/playbooks/setup_host.yml") as handle:
        tasks = yaml.safe_load(handle)[0]["tasks"]
    targets = {t.get("ansible.builtin.import_tasks") for t in tasks}
    assert {"tasks/build_minqlxtended.yml", "tasks/sync_common_plugins.yml"} <= targets


def test_every_new_playbook_references_existing_task_files():
    for path in ["ansible/playbooks/install_runtime.yml",
                 "ansible/playbooks/update_instance_runtime.yml"]:
        with open(path) as handle:
            play = yaml.safe_load(handle)[0]
        for task in _flat(play["tasks"]):
            target = task.get("ansible.builtin.import_tasks")
            if target:
                assert os.path.isfile(os.path.join("ansible/playbooks", target)), target
    assert glob.glob("ansible/files/qlsm_runtime_op.py")


def test_everything_under_home_ql_runs_as_ql():
    """Root must not create, chown or copy into the ql-controlled venv tree:
    a symlink planted by ql would redirect it."""
    with open(os.path.join(TASKS_DIR, "runtime_python_deps.yml")) as handle:
        tasks = yaml.safe_load(handle)
    for task in tasks:
        text = yaml.safe_dump(task)
        if "runtime_deps" in text and any(k in task for k in (
                "ansible.builtin.file", "ansible.builtin.copy", "ansible.builtin.command")):
            if "python3-config" in text or "/usr/bin/python3, -c" in text:
                continue
            assert task.get("become_user") == "ql", task["name"]
            module = task.get("ansible.builtin.file") or task.get("ansible.builtin.copy") or {}
            assert "owner" not in module, task["name"]
