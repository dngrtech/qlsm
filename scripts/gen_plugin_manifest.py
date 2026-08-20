#!/usr/bin/env python3
"""Regenerate ql-assets/data/minqlxtended-plugins/manifest.json.

Hashes every .py file in the baseline directory and records its origin.
An existing entry keeps its origin, so a re-vendor never silently reclassifies
QLSM's own serverchecker.py as upstream code.
"""
import hashlib
import json
import os

BASELINE_DIR = os.path.join('ql-assets', 'data', 'minqlxtended-plugins')
MANIFEST_PATH = os.path.join(BASELINE_DIR, 'manifest.json')

UPSTREAM = {
    'repo': 'https://github.com/tjone270/minqlxtended-plugins',
    'commit': 'd93a3ce758bac650ad1b00ff4850f06873c914a9',
    'version': 'plugins v1.0.0',
}


def sha256(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main():
    previous = {}
    if os.path.isfile(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as handle:
            previous = json.load(handle).get('files', {})

    files = {}
    for name in sorted(os.listdir(BASELINE_DIR)):
        if not name.endswith('.py'):
            continue
        files[name] = {
            'sha256': sha256(os.path.join(BASELINE_DIR, name)),
            'origin': previous.get(name, {}).get('origin', 'upstream'),
        }

    with open(MANIFEST_PATH, 'w', encoding='utf-8') as handle:
        json.dump({'upstream': UPSTREAM, 'files': files}, handle, indent=2, sort_keys=True)
        handle.write('\n')

    print(f"wrote {MANIFEST_PATH} with {len(files)} files")


if __name__ == '__main__':
    main()
