import yaml

PLAYBOOK = "ansible/playbooks/sync_instance_configs_and_restart.yml"
SYNC_KEY = "ansible.builtin.synchronize"


def _tasks():
    with open(PLAYBOOK) as f:
        doc = yaml.safe_load(f)
    return doc[0]["tasks"]


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
