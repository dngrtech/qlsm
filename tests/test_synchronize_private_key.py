from pathlib import Path

import yaml


PLAYBOOKS = Path(__file__).resolve().parent.parent / "ansible" / "playbooks"
SYNC_KEYS = {"synchronize", "ansible.builtin.synchronize"}


def _active_synchronize_tasks():
    for path in PLAYBOOKS.rglob("*.yml"):
        if "old" in path.parts:
            continue
        with path.open() as playbook:
            plays = yaml.safe_load(playbook) or []
        for play in plays:
            for task in play.get("tasks", []):
                for sync_key in SYNC_KEYS.intersection(task):
                    yield path, task, task[sync_key]


def test_active_synchronize_tasks_use_inventory_private_key():
    tasks = list(_active_synchronize_tasks())

    assert tasks, "expected active synchronize tasks"
    missing = [
        f"{path.relative_to(PLAYBOOKS)}: {task.get('name', '<unnamed>')}"
        for path, task, synchronize in tasks
        if synchronize.get("private_key") != "{{ ansible_ssh_private_key_file }}"
    ]

    assert not missing, (
        "Every active synchronize task must pass Ansible's inventory private "
        "key to rsync's separate SSH client:\n" + "\n".join(missing)
    )
