import yaml

PLAYBOOK = "ansible/playbooks/sync_instance_configs_and_restart.yml"
SYNC_KEY = "ansible.builtin.synchronize"
COPY_KEY = "ansible.builtin.copy"


def _tasks():
    with open(PLAYBOOK) as f:
        doc = yaml.safe_load(f)
    return doc[0]["tasks"]


def _vars():
    with open(PLAYBOOK) as f:
        doc = yaml.safe_load(f)
    return doc[0]["vars"]


def _minqlx_sync_task():
    """The task that pulls minqlx from the shared build into the instance dir."""
    return next(
        t for t in _tasks()
        if COPY_KEY in t and "minqlx_shared_dir" in str(t[COPY_KEY].get("src", ""))
    )


def _service_template_index(tasks):
    return next(
        i for i, task in enumerate(tasks)
        if "qlds@{{ game_port }}.service" in str(
            task.get("ansible.builtin.template", {}).get("dest", "")
        )
    )


def test_playbook_ensures_user_hooks_dir():
    names = [t.get("name", "") for t in _tasks()]
    assert any("user-hooks directory exists" in n for n in names), names


def test_playbook_syncs_user_hooks_with_delete():
    tasks = _tasks()
    sync = next(
        t for t in tasks
        if SYNC_KEY in t and "user-hooks/" in t[SYNC_KEY].get("src", "")
    )
    s = sync[SYNC_KEY]
    assert s["dest"] == "{{ qlds_dir }}/user-hooks/"
    assert s["delete"] is True
    assert s["src"] == "../../configs/{{ host_name }}/{{ qlds_id }}/user-hooks/"
    assert "--include=*.so" in s["rsync_opts"]
    assert "--exclude=*" in s["rsync_opts"]
    assert sync["when"] == "user_hooks_source.stat.exists"


def test_playbook_checks_user_hooks_source_before_sync():
    tasks = _tasks()
    source_check = next(
        t for t in tasks
        if t.get("register") == "user_hooks_source"
    )
    assert source_check["ansible.builtin.stat"]["path"] == (
        "{{ playbook_dir }}/../../configs/{{ host_name }}/{{ qlds_id }}/user-hooks/"
    )
    assert source_check["delegate_to"] == "localhost"
    assert source_check["become"] is False


def test_playbook_unconditionally_ensures_system_hooks_dir_before_service_template():
    tasks = _tasks()
    task_index, task = next(
        (i, task) for i, task in enumerate(tasks)
        if task.get("ansible.builtin.file", {}).get("path")
        == "{{ qlds_dir }}/system-hooks"
    )
    file_args = task["ansible.builtin.file"]

    assert file_args["state"] == "directory"
    assert file_args["owner"] == "ql"
    assert file_args["group"] == "ql"
    assert "when" not in task
    assert task_index < _service_template_index(tasks)


def test_playbook_unconditionally_syncs_system_hooks_before_service_template():
    tasks = _tasks()
    task_index, task = next(
        (i, task) for i, task in enumerate(tasks)
        if task.get(SYNC_KEY, {}).get("src")
        == "../../ql-assets/data/system-hooks/"
    )
    sync_args = task[SYNC_KEY]

    assert sync_args["dest"] == "{{ qlds_dir }}/system-hooks/"
    assert "--include=*.so" in sync_args["rsync_opts"]
    assert "--exclude=*" in sync_args["rsync_opts"]
    assert task["delegate_to"] == "localhost"
    assert task["become"] is False
    assert "when" not in task
    assert task_index < _service_template_index(tasks)


def test_playbook_defines_minqlx_shared_dir_var():
    assert _vars()["minqlx_shared_dir"] == "/home/ql/minqlx-shared"


def test_playbook_mirrors_whole_minqlx_shared_dir():
    task = _minqlx_sync_task()
    c = task[COPY_KEY]
    assert c["src"] == "{{ minqlx_shared_dir }}/"
    assert c["dest"] == "{{ qlds_dir }}/"
    assert c["remote_src"] is True
    assert c["mode"] == "preserve"
    assert c["owner"] == "ql"
    assert c["group"] == "ql"
    # A whole-directory mirror must not be a per-file loop.
    assert "loop" not in task


def test_minqlx_is_never_cherry_picked_by_file():
    """Regression guard for the damage-event bug.

    The old task looped over exactly minqlx.x64.so and run_server_x64_minqlx.sh,
    never the minqlx/ Python package. That shipped a patched binary against a
    stale Python package, so EVENT_DISPATCHERS["damage"] never registered on
    existing instances. minqlx must be mirrored as a whole directory.
    """
    # Unconditional assertion first: the mirror task must exist and not be a
    # loop. Without this the scan below passes vacuously once no loops remain.
    assert "loop" not in _minqlx_sync_task()

    # And no copy task anywhere may reintroduce per-file cherry-picking.
    for task in _tasks():
        if COPY_KEY not in task:
            continue
        for item in task.get("loop") or []:
            assert "minqlx.x64.so" not in str(item), (
                "minqlx must be mirrored as a whole directory, not cherry-picked per file"
            )


def test_minqlx_sync_precedes_service_restart():
    """The synced files only take effect if the restart happens after the sync."""
    tasks = _tasks()
    sync_idx = next(
        i for i, t in enumerate(tasks)
        if COPY_KEY in t and "minqlx_shared_dir" in str(t[COPY_KEY].get("src", ""))
    )
    restart_idx = next(
        i for i, t in enumerate(tasks)
        if "Restart QLDS service" in t.get("name", "")
    )
    assert sync_idx < restart_idx


def test_playbook_explicitly_keeps_non_restarted_service_stopped():
    task = next(
        task for task in _tasks()
        if "Keep stopped QLDS service stopped" in task.get("name", "")
    )
    systemd_args = task["ansible.builtin.systemd"]

    assert systemd_args["name"] == "qlds@{{ game_port }}"
    assert systemd_args["state"] == "stopped"
    assert task["when"] == "not (restart_service | bool)"
