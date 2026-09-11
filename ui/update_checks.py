"""Content-hash diff engine for "Check for Updates".

Replaces the old blind "Update Plugins" backfill (which silently skipped any
file an instance had explicitly selected — see the match_restore.py incident)
with an explicit diff: hash the source of truth (ql-assets pool, on the qlsm
controller) against whatever's actually deployed, and let the operator pick
which changes to apply. Two comparison shapes are needed:

- Local vs local (instance-selected plugins: ql-assets pool vs
  configs/{host}/{instance}/scripts/, both live on the qlsm controller's own
  filesystem — no SSH needed).
- Local vs remote (host common plugin pool on the target VPS) — needs an
  ansible ad-hoc hash listing, see ansible_adhoc.py.
"""

import hashlib
import os

PLUGIN_EXTENSIONS = ('.py', '.ql-plugin.json')


def hash_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def hash_local_tree(root_dir, extensions=None):
    """Returns {relpath: sha256} for every file directly under root_dir
    (non-recursive — matches how minqlx-plugins pools are laid out: flat,
    no subfolders for the .py/.json pairs themselves)."""
    result = {}
    if not os.path.isdir(root_dir):
        return result
    for entry in os.scandir(root_dir):
        if not entry.is_file():
            continue
        if extensions and not entry.name.endswith(extensions):
            continue
        result[entry.name] = hash_file(entry.path)
    return result


def parse_sha256sum_output(output, strip_prefix=None):
    """Parses `sha256sum <files>` output ("<hash>  <path>\\n" per line) into
    {relpath: hash}. strip_prefix removes a leading directory so remote
    absolute paths become the same relative keys as hash_local_tree()."""
    result = {}
    for line in output.splitlines():
        line = line.rstrip('\n')
        if not line or '  ' not in line:
            continue
        digest, _, path = line.partition('  ')
        digest = digest.strip()
        path = path.strip()
        if strip_prefix and path.startswith(strip_prefix):
            path = path[len(strip_prefix):]
        path = path.lstrip('/')
        if digest and path:
            result[path] = digest
    return result


def diff_trees(source, target):
    """source = what SHOULD be deployed (pool), target = what IS deployed.
    Returns a list of {"name": ..., "change": "added"|"modified"|"removed"},
    sorted by name. "added" = in source but missing from target (new file
    upstream). "removed" = in target but gone from source (only reported for
    visibility — apply never deletes instance-selected files)."""
    changes = []
    for name, src_hash in source.items():
        tgt_hash = target.get(name)
        if tgt_hash is None:
            changes.append({"name": name, "change": "added"})
        elif tgt_hash != src_hash:
            changes.append({"name": name, "change": "modified"})
    for name in target:
        if name not in source:
            changes.append({"name": name, "change": "removed"})
    changes.sort(key=lambda c: c["name"])
    return changes
