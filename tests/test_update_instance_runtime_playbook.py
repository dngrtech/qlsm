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


def test_rollback_mode_is_inventory_restore_only():
    """Rollback must be exact: restore the recorded backups (incl. the original
    unit) and remove target-created files -- never re-copy runtime artifacts
    from a shared dir that may have been rebuilt since."""
    tasks = list(_flat(_play()["tasks"]))
    by_name = {t.get("name"): t for t in tasks}
    restore = by_name["Restore the inventory recorded by the operation being rolled back"]
    assert "restore" in restore["ansible.builtin.script"]["cmd"]
    assert "--qlds-dir" in restore["ansible.builtin.script"]["cmd"]
    assert "--unit-path" in restore["ansible.builtin.script"]["cmd"]
    assert restore["when"] == "restore_from_operation | length > 0"
    forward = by_name["Configure forward (not a rollback)"]
    assert forward["when"] == "restore_from_operation | length == 0"
    forward_names = {t.get("name") for t in _flat(forward["block"])}
    assert {"Write the managed-file plan", "Record the inventory, then install the managed files",
            "Render the systemd unit into staging", "Unpack the instance's managed files"} <= forward_names
    for task in tasks:  # nothing outside the forward block writes managed files
        if task.get("name") in forward_names:
            continue
        cmd = str((task.get("ansible.builtin.script") or {}).get("cmd", ""))
        assert " apply " not in cmd, task.get("name")
    assert _play()["vars"]["ops_dir"] == "{{ runtime_ops_root }}/ops/{{ operation_id }}/{{ instance_id | int }}"
    # Daemon reload and the still-stopped check run in both modes.
    assert "when" not in by_name["Reload systemd without starting anything"]
    assert "when" not in by_name["Require the service to still be stopped"]


def test_operation_state_lives_in_the_root_owned_tree_not_under_home_ql():
    play_vars = _play()["vars"]
    assert play_vars["runtime_ops_root"] == "/var/lib/qlsm/runtime-ops"
    assert "/home/ql" not in play_vars["ops_dir"] and "/home/ql" not in play_vars["stage_dir"]
