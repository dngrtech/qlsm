#!/usr/bin/env python3
"""Regenerate a plugin baseline's manifest.json.

Usage: gen_plugin_manifest.py [minqlx|minqlxtended]   (default: minqlxtended)

Hashes every .py file in the baseline directory and records its origin.
An existing entry keeps its origin, so a re-vendor never silently reclassifies
QLSM's own serverchecker.py as upstream code.

Hashing goes through ui.plugin_compat.baseline_digest so the manifest and the
compatibility gate agree; see that function for why raw-byte hashing is wrong.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def main():
    runtime = sys.argv[1] if len(sys.argv) > 1 else 'minqlxtended'
    if runtime not in UPSTREAM_BY_RUNTIME:
        raise SystemExit(f"unknown runtime {runtime!r}; "
                         f"expected one of {sorted(UPSTREAM_BY_RUNTIME)}")

    baseline_dir = os.path.join('ql-assets', 'data', f'{runtime}-plugins')
    manifest_path = os.path.join(baseline_dir, 'manifest.json')

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
        files[name] = {
            'sha256': baseline_digest(text),
            'origin': previous.get(name, {}).get('origin', 'upstream'),
        }

    with open(manifest_path, 'w', encoding='utf-8') as handle:
        json.dump({'upstream': UPSTREAM_BY_RUNTIME[runtime], 'files': files},
                  handle, indent=2, sort_keys=True)
        handle.write('\n')

    print(f"wrote {manifest_path} with {len(files)} files")


if __name__ == '__main__':
    main()
