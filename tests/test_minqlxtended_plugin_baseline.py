"""The vendored minqlxtended plugin baseline must match its manifest exactly.

A plugin file that drifts from the manifest is a plugin nobody can diff against
upstream, which is the whole point of pinning a commit.
"""
import hashlib
import json
import os

import pytest

BASELINE_DIR = os.path.join('ql-assets', 'data', 'minqlxtended-plugins')
MANIFEST_PATH = os.path.join(BASELINE_DIR, 'manifest.json')

UPSTREAM_COMMIT = 'd93a3ce758bac650ad1b00ff4850f06873c914a9'
UPSTREAM_REPO = 'https://github.com/tjone270/minqlxtended-plugins'

# The 33 plugins upstream ships at the pinned commit. Listed rather than
# globbed so an accidental deletion fails loudly instead of silently shrinking
# the baseline.
UPSTREAM_PLUGINS = [
    'aliases.py', 'balance.py', 'ban.py', 'branding.py', 'clan.py',
    'custom_votes.py', 'dictionary.py', 'docs.py', 'essentials.py', 'fun.py',
    'infectedmm.py', 'lan.py', 'last_in.py', 'leaverban.py', 'log.py',
    'maptools.py', 'motd.py', 'names.py', 'permission.py', 'plugin_manager.py',
    'pummel.py', 'queue.py', 'raw.py', 'scores.py', 'silence.py', 'solorace.py',
    'stats.py', 'sv_fps.py', 'untracked.py', 'votecommands.py', 'votestats.py',
    'vpnblock.py', 'workshop.py',
]


def _sha256(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture(scope='module')
def manifest():
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def test_manifest_pins_the_upstream_commit(manifest):
    assert manifest['upstream']['repo'] == UPSTREAM_REPO
    assert manifest['upstream']['commit'] == UPSTREAM_COMMIT


def test_every_upstream_plugin_is_vendored():
    missing = [name for name in UPSTREAM_PLUGINS
               if not os.path.isfile(os.path.join(BASELINE_DIR, name))]
    assert missing == [], f"missing vendored plugins: {missing}"


def test_manifest_covers_every_python_file_in_the_directory(manifest):
    on_disk = {name for name in os.listdir(BASELINE_DIR) if name.endswith('.py')}
    assert on_disk == set(manifest['files']), (
        "manifest.json and the directory disagree; regenerate it "
        "(see ql-assets/data/minqlxtended-plugins/README.md)"
    )


def test_every_manifest_hash_matches_the_file_on_disk(manifest):
    mismatched = [
        name for name, entry in manifest['files'].items()
        if _sha256(os.path.join(BASELINE_DIR, name)) != entry['sha256']
    ]
    assert mismatched == [], f"sha256 drift: {mismatched}"


def test_upstream_files_are_marked_upstream(manifest):
    for name in UPSTREAM_PLUGINS:
        assert manifest['files'][name]['origin'] == 'upstream', name


def test_no_baseline_plugin_imports_minqlx():
    """A file importing `minqlx` on this runtime fails to load, loudly.

    Matching the bare module name rather than the substring: `minqlxtended`
    contains `minqlx`, so a substring check would flag every correct file.
    """
    offenders = []
    for name in os.listdir(BASELINE_DIR):
        if not name.endswith('.py'):
            continue
        with open(os.path.join(BASELINE_DIR, name), 'r', encoding='utf-8') as handle:
            for lineno, line in enumerate(handle, 1):
                stripped = line.strip()
                if stripped.startswith('import minqlx ') or stripped == 'import minqlx':
                    offenders.append(f"{name}:{lineno}")
                elif stripped.startswith('from minqlx ') or stripped.startswith('from minqlx.'):
                    offenders.append(f"{name}:{lineno}")
    assert offenders == [], f"minqlx imports in the minqlxtended baseline: {offenders}"


def test_requirements_carry_the_upstream_floors():
    with open(os.path.join(BASELINE_DIR, 'requirements.txt'), 'r', encoding='utf-8') as handle:
        body = handle.read()
    for requirement in ('redis>=5.1.0', 'hiredis>=3.0.0', 'requests>=2.33.0', 'pyzmq>=25.1.1'):
        assert requirement in body, requirement
