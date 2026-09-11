"""update_common_plugins.yml is the narrow, on-demand counterpart to
force_update_workshop.yml for the minqlx plugin pool: it must refresh
/home/ql/assets/common/minqlx-plugins/ without touching the network/
firewall/SSH tasks that make setup_host.yml risky to run against a live
host. Both it and setup_host.yml share the same sync logic via
tasks/sync_common_plugins.yml, so a plugin-pool fix only needs to be
correct in one place.
"""

import yaml

UPDATE_PLAYBOOK = "ansible/playbooks/update_common_plugins.yml"
SETUP_PLAYBOOK = "ansible/playbooks/setup_host.yml"
SHARED_TASKS = "ansible/playbooks/tasks/sync_common_plugins.yml"


def _load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def test_update_common_plugins_playbook_imports_shared_sync_task():
    doc = _load(UPDATE_PLAYBOOK)
    tasks = doc[0]["tasks"]
    assert any(
        t.get("ansible.builtin.import_tasks") == "tasks/sync_common_plugins.yml"
        for t in tasks
    ), tasks


def test_update_common_plugins_playbook_has_no_network_or_firewall_tasks():
    """Regression guard: this playbook must stay narrow. setup_host.yml's 66
    tasks include netplan/iptables/hostname/SSH hardening, far too risky to
    run against a live host just to land a plugin fix."""
    doc = _load(UPDATE_PLAYBOOK)
    play = doc[0]
    assert len(play["tasks"]) <= 3, play["tasks"]
    for forbidden in ("netplan", "iptables", "hostname", "ssh", "firewall"):
        assert forbidden not in str(play).lower(), forbidden


def test_setup_host_imports_the_same_shared_sync_task():
    doc = _load(SETUP_PLAYBOOK)
    tasks = doc[0]["tasks"]
    assert any(
        t.get("ansible.builtin.import_tasks") == "tasks/sync_common_plugins.yml"
        for t in tasks
    ), "setup_host.yml must import the shared sync task, not duplicate it"


def test_setup_host_does_not_duplicate_plugin_sync():
    """Regression guard: the plugin-pool sync used to be duplicated inline
    later in setup_host.yml (steamapps/scripts sync section). It must now
    only exist once, via the shared task import."""
    doc = _load(SETUP_PLAYBOOK)
    tasks = doc[0]["tasks"]
    sync_tasks = [
        t for t in tasks
        if t.get("ansible.builtin.synchronize", t.get("synchronize", {})).get("dest", "")
        and "minqlx-plugins" in str(t.get("ansible.builtin.synchronize", t.get("synchronize", {})).get("dest", ""))
    ]
    assert sync_tasks == [], sync_tasks


def test_shared_sync_task_refreshes_pool_by_full_mirror():
    tasks = _load(SHARED_TASKS)
    sync_task = next(
        t for t in tasks
        if "synchronize" in t and "runtime_plugins_dirname" in str(t["synchronize"].get("dest", ""))
    )
    sync_args = sync_task["synchronize"]
    assert sync_args["delete"] is True
    assert sync_args["dest"] == "{{ common_assets_dir }}/{{ runtime_plugins_dirname }}/"


def test_update_common_plugins_playbook_targets_the_host_runtime():
    """runtime_plugins_dirname must resolve from a runtime var the caller can
    override — ansible_plugin_update.py passes it via runtime_extravars(host)
    (see ui/runtime.py) so a minqlxtended host's own pool gets synced, not
    minqlx's."""
    doc = _load(UPDATE_PLAYBOOK)
    play = doc[0]
    assert play["vars"]["runtime_plugins_dirname"] == (
        "{{ 'minqlxtended-plugins' if runtime == 'minqlxtended' else 'minqlx-plugins' }}"
    )
    assert play["hosts"] == "{{ target_host_name | default('all') }}"
