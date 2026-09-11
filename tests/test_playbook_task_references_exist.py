"""Regression guard for the update_common_plugins.yml bug caught in review:
it imported tasks/sync_qlmatch_packer.yml, a file from an unrelated branch
that was never part of this PR or main. import_tasks/include_tasks is
resolved when the playbook is *parsed* (ansible-playbook --syntax-check
fails immediately), so a missing task file breaks the whole playbook before
any task runs -- something a plain yaml.safe_load parse of the referencing
file alone can't catch, since it never looks at whether the target exists.
"""
import glob
import os
import re

import yaml

PLAYBOOKS_DIR = "ansible/playbooks"
TASK_REF_RE = re.compile(r"(?:ansible\.builtin\.)?(?:import_tasks|include_tasks)")


def _referenced_task_files():
    """(playbook, referenced_path) for every import_tasks/include_tasks in
    ansible/playbooks/**/*.yml. Parsed via PyYAML, not a regex over the
    rendered value, so a Jinja-templated reference (none exist today) would
    just not match TASK_REF_RE's key rather than produce a false positive."""
    refs = []
    for path in glob.glob(os.path.join(PLAYBOOKS_DIR, "**", "*.yml"), recursive=True):
        with open(path, encoding="utf-8") as f:
            docs = yaml.safe_load(f)
        for play_or_task in _flatten(docs):
            if not isinstance(play_or_task, dict):
                continue
            for key, value in play_or_task.items():
                if TASK_REF_RE.fullmatch(key) and isinstance(value, str):
                    refs.append((path, value))
    return refs


def _flatten(node):
    """Yields every dict found anywhere in a playbook's task tree (tasks,
    pre_tasks, post_tasks, handlers, blocks, nested plays)."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _flatten(value)
    elif isinstance(node, list):
        for item in node:
            yield from _flatten(item)


def test_every_import_or_include_tasks_target_exists():
    missing = []
    for playbook, target in _referenced_task_files():
        resolved = os.path.join(PLAYBOOKS_DIR, target)
        if not os.path.isfile(resolved):
            missing.append(f"{playbook} -> {target}")
    assert missing == [], "Playbook references a task file that doesn't exist:\n" + "\n".join(missing)
