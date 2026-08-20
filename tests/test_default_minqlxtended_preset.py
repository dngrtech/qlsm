"""The minqlxtended builtin preset must be loadable and runtime-stamped.

A preset whose runtime does not match the host is hard-blocked in the UI
(frontend-react/src/utils/presetRuntimeCompat.js), so a missing or wrong
`runtime` in preset.json makes this preset unusable on the only hosts it is for.
"""
import json
import os

import pytest

PRESET_DIR = os.path.join('configs', 'presets', '_builtin', 'default-minqlxtended')
MINQLX_PRESET_DIR = os.path.join('configs', 'presets', '_builtin', 'default')
BASELINE_DIR = os.path.join('ql-assets', 'data', 'minqlxtended-plugins')

RUNTIME_AGNOSTIC_FILES = [
    'access.txt', 'mappool.txt', 'server.cfg', 'workshop.txt',
    'factory.factories', 'checked_factories.json',
]


@pytest.fixture(scope='module')
def manifest():
    with open(os.path.join(PRESET_DIR, 'preset.json'), 'r', encoding='utf-8') as handle:
        return json.load(handle)


@pytest.fixture(scope='module')
def checked_plugins():
    with open(os.path.join(PRESET_DIR, 'checked_plugins.json'), 'r', encoding='utf-8') as handle:
        return json.load(handle)


def test_preset_is_builtin_and_stamped_minqlxtended(manifest):
    assert manifest['builtin'] is True
    assert manifest['runtime'] == 'minqlxtended'
    assert manifest['description'].strip()


def test_preset_declares_no_binaries(manifest):
    """The .so companions are P4. Declaring one that does not exist makes
    _validate_binary_descriptions reject the whole preset at seed time."""
    assert manifest.get('binary_descriptions', {}) == {}


def test_checked_plugins_mirror_the_minqlx_default(checked_plugins):
    with open(os.path.join(MINQLX_PRESET_DIR, 'checked_plugins.json'), 'r', encoding='utf-8') as handle:
        minqlx_checked = json.load(handle)
    assert sorted(checked_plugins) == sorted(minqlx_checked)


def test_every_checked_plugin_ships_in_the_preset(checked_plugins):
    scripts = set(os.listdir(os.path.join(PRESET_DIR, 'scripts')))
    missing = [name for name in checked_plugins if name not in scripts]
    assert missing == [], f"checked but not shipped: {missing}"


def test_scripts_match_the_vendored_upstream_baseline():
    """The picker offers exactly what upstream ships. serverchecker is excluded
    deliberately: it is a SYSTEM_PLUGIN, prepended to qlx_plugins for every
    instance (ansible_instance_mgmt.py:27) and backfilled from the baseline, so
    an operator must never be able to untick it."""
    preset_scripts = {n for n in os.listdir(os.path.join(PRESET_DIR, 'scripts')) if n.endswith('.py')}
    baseline = {n for n in os.listdir(BASELINE_DIR) if n.endswith('.py')}
    assert preset_scripts == baseline - {'serverchecker.py'}


def test_no_minqlx_plugin_leaked_into_the_preset():
    offenders = []
    scripts_dir = os.path.join(PRESET_DIR, 'scripts')
    for name in os.listdir(scripts_dir):
        if not name.endswith('.py'):
            continue
        with open(os.path.join(scripts_dir, name), 'r', encoding='utf-8') as handle:
            for lineno, line in enumerate(handle, 1):
                stripped = line.strip()
                if stripped == 'import minqlx' or stripped.startswith('import minqlx '):
                    offenders.append(f"{name}:{lineno}")
                elif stripped.startswith('from minqlx ') or stripped.startswith('from minqlx.'):
                    offenders.append(f"{name}:{lineno}")
    assert offenders == []


@pytest.mark.parametrize('filename', RUNTIME_AGNOSTIC_FILES)
def test_runtime_agnostic_config_matches_the_minqlx_default(filename):
    """Server config, map pool and factories have nothing to do with the
    runtime. Divergence here would be an accident, not a decision."""
    with open(os.path.join(PRESET_DIR, filename), 'rb') as handle:
        ours = handle.read()
    with open(os.path.join(MINQLX_PRESET_DIR, filename), 'rb') as handle:
        theirs = handle.read()
    assert ours == theirs


def test_factories_directory_matches_the_minqlx_default():
    ours = sorted(os.listdir(os.path.join(PRESET_DIR, 'factories')))
    theirs = sorted(os.listdir(os.path.join(MINQLX_PRESET_DIR, 'factories')))
    assert ours == theirs
