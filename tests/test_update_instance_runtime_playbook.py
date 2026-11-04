"""update_instance_runtime.yml: configure an existing, stopped instance for a
runtime without starting it. Static checks here; the executable run against
a disposable container lives in tests/test_runtime_upgrade_integration.py."""
import yaml

PLAYBOOK = "ansible/playbooks/update_instance_runtime.yml"


def _play():
    with open(PLAYBOOK) as handle:
        return yaml.safe_load(handle)[0]


def _flat(tasks):
    for task in tasks:
        yield task
        for key in ("block", "rescue", "always"):
            yield from _flat(task.get(key) or [])


def _text():
    with open(PLAYBOOK) as handle:
        return "\n".join(line for line in handle.read().splitlines()
                         if not line.lstrip().startswith("#"))


def test_lock_precedes_every_side_effect():
    tasks = _play()["tasks"]
    assert "ansible.builtin.assert" in tasks[0]
    assert tasks[1]["ansible.builtin.import_tasks"] == "tasks/runtime_op_lock.yml"
    assert "block" in tasks[2] and len(tasks) == 3
    assert any(t.get("ansible.builtin.import_tasks") == "tasks/runtime_op_release.yml"
               for t in tasks[2]["always"])


def test_requires_existing_dir_and_stopped_service_before_writing():
    names = [t.get("name") for t in _flat(_play()["tasks"])]
    first_write = names.index("Reset the private staging directory")
    assert names.index("Require an existing instance directory") < first_write
    assert names.index("Require the service to be stopped") < first_write
    assert names.index("Require the service to still be stopped") > names.index(
        "Record the inventory, then install the managed files")


def test_never_starts_enables_or_restarts_the_service():
    for task in _flat(_play()["tasks"]):
        systemd = task.get("ansible.builtin.systemd") or task.get("systemd") or {}
        assert "state" not in systemd and "enabled" not in systemd, task.get("name")
        assert "notify" not in task
    assert "handlers" not in _play()


def test_never_uses_the_creation_path_mirror_delete_pip_or_redis():
    text = _text()
    for forbidden in ("add_qlds_instance", "qlds-base", "delete: yes", "synchronize",
                      "pip", "redis", "--delete", "state: started", "state: restarted"):
        assert forbidden not in text, forbidden


def test_only_runtime_engine_archive_launcher_come_from_the_shared_dir():
    sources = None
    for task in _flat(_play()["tasks"]):
        if task.get("name") == "Write the managed-file plan":
            sources = task["vars"]["plan"]["sources"]
    shared = [s for s in sources if s["from"] == "{{ runtime_shared_dir }}"]
    assert [s["names"] for s in shared] == ["{{ runtime_artifacts }}",
                                            "{{ runtime_optional_artifacts | default([]) }}"]
    kinds = {s["kind"] for s in sources}
    assert kinds == {"tree", "names", "missing_only", "file"}


def test_rollback_mode_restores_inventory_and_does_not_re_record():
    tasks = {t.get("name"): t for t in _flat(_play()["tasks"])}
    restore = tasks["Restore the inventory recorded by the operation being rolled back"]
    assert "restore" in restore["ansible.builtin.script"]["cmd"]
    assert restore["when"] == "restore_from_operation | length > 0"
    plan = tasks["Write the managed-file plan"]["vars"]["plan"]
    assert plan["record"] == "{{ restore_from_operation | length == 0 }}"
    assert plan["ops_dir"] == "{{ ops_dir }}"
    assert _play()["vars"]["ops_dir"] == "{{ runtime_ops_root }}/ops/{{ operation_id }}/{{ instance_id | int }}"
    assert "--qlds-dir" in restore["ansible.builtin.script"]["cmd"]
    assert "--unit-path" in restore["ansible.builtin.script"]["cmd"]


def test_operation_state_lives_in_the_root_owned_tree_not_under_home_ql():
    play_vars = _play()["vars"]
    assert play_vars["runtime_ops_root"] == "/var/lib/qlsm/runtime-ops"
    assert "/home/ql" not in play_vars["ops_dir"] and "/home/ql" not in play_vars["stage_dir"]
