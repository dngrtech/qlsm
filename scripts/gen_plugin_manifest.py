#!/usr/bin/env python3
"""Regenerate a plugin baseline's manifest.json.

Usage: gen_plugin_manifest.py [minqlx|minqlxtended]   (default: minqlxtended)

Hashes every .py file in the baseline directory and records its origin. An
existing entry keeps its origin, so a re-vendor never silently reclassifies
QLSM's own serverchecker.py as upstream code. A file with no previous entry
falls back to QLSM_PLUGINS_BY_RUNTIME below instead of a bare 'upstream'
default, so a *first-ever* generation doesn't make that same mistake on day
one -- 'upstream' only when the file isn't a known QLSM port.

Hashing goes through ui.plugin_compat.baseline_digest so the manifest and the
compatibility gate agree; see that function for why raw-byte hashing is wrong.

REPO_ROOT anchors both the ui.plugin_compat import and the baseline directory
to the repo root rather than the working directory -- the same reasoning as
ui/preset_compat.py's ASSETS_DIR. Several sibling git worktrees on this
machine each carry their own ql-assets/data/ subtree; a CWD-relative path run
from the wrong one would silently write the wrong worktree's manifest instead
of erroring.
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from ui.plugin_compat import baseline_digest  # noqa: E402

UPSTREAM_BY_RUNTIME = {
    'minqlxtended': {
        'repo': 'https://github.com/tjone270/minqlxtended-plugins',
        'commit': 'd93a3ce758bac650ad1b00ff4850f06873c914a9',
        'version': 'plugins v1.0.0',
    },
    'minqlx': {
        'repo': 'https://github.com/MinoMino/minqlx-plugins',
        'commit': 'vendored -- QLSM has carried this baseline since before the '
                  'minqlxtended work; no single upstream commit pins it',
        'version': 'n/a',
    },
}

# QLSM's own plugins, ported to each runtime's API -- not upstream code, so a
# file with no previous manifest entry must not default to origin='upstream'.
# Mirrors QLSM_PLUGINS in tests/test_minqlxtended_plugin_baseline.py; both
# runtimes carry ports of the same seven files.
QLSM_PLUGINS_BY_RUNTIME = {
    'minqlxtended': {
        'commands.py', 'myFun.py', 'player_info.py', 'reset_acc.py',
        'serverchecker.py', 'specqueue.py', 'suppress_join_msg.py',
    },
    'minqlx': {
        'commands.py', 'myFun.py', 'player_info.py', 'reset_acc.py',
        'serverchecker.py', 'specqueue.py', 'suppress_join_msg.py',
    },
}


def main():
    runtime = sys.argv[1] if len(sys.argv) > 1 else 'minqlxtended'
    if runtime not in UPSTREAM_BY_RUNTIME:
        raise SystemExit(f"unknown runtime {runtime!r}; "
                         f"expected one of {sorted(UPSTREAM_BY_RUNTIME)}")

    baseline_dir = os.path.join(REPO_ROOT, 'ql-assets', 'data', f'{runtime}-plugins')
    manifest_path = os.path.join(baseline_dir, 'manifest.json')
    qlsm_plugins = QLSM_PLUGINS_BY_RUNTIME[runtime]

    previous = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as handle:
            previous = json.load(handle).get('files', {})

    files = {}
    for name in sorted(os.listdir(baseline_dir)):
        if not name.endswith('.py'):
            continue
        with open(os.path.join(baseline_dir, name), 'r', encoding='utf-8') as handle:
            text = handle.read()
        default_origin = 'qlsm' if name in qlsm_plugins else 'upstream'
        files[name] = {
            'sha256': baseline_digest(text),
            'origin': previous.get(name, {}).get('origin', default_origin),
        }

    with open(manifest_path, 'w', encoding='utf-8') as handle:
        json.dump({'upstream': UPSTREAM_BY_RUNTIME[runtime], 'files': files},
                  handle, indent=2, sort_keys=True)
        handle.write('\n')

    print(f"wrote {manifest_path} with {len(files)} files")


if __name__ == '__main__':
    main()
