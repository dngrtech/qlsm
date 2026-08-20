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


#: Baseline plugins the picker deliberately does not offer.
#:
#: serverchecker is a SYSTEM_PLUGIN, prepended to qlx_plugins for every instance
#: (ansible_instance_mgmt.py:27) and backfilled from the baseline, so an operator must
#: never be able to untick it.
#:
#: reset_acc and suppress_join_msg are not in the minqlx default preset's scripts/
#: either. The minqlxtended default mirrors the minqlx default's selection, so that an
#: operator moving between runtimes is offered the same set. Both remain available:
#: everything in the baseline lands in every instance's plugin directory regardless of
#: preset, and a host that wants them can enable them by name.
BASELINE_ONLY = {'serverchecker.py', 'reset_acc.py', 'suppress_join_msg.py'}


def test_scripts_match_the_vendored_baseline():
    """The picker offers the whole baseline bar the three that are deliberately out."""
    preset_scripts = {n for n in os.listdir(os.path.join(PRESET_DIR, 'scripts')) if n.endswith('.py')}
    baseline = {n for n in os.listdir(BASELINE_DIR) if n.endswith('.py')}
    assert preset_scripts == baseline - BASELINE_ONLY


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


# The QLSM ports that are pickable from this preset. myFun, specqueue, player_info and
# commands ship in the minqlx default preset's scripts/, so their ports ship here.
# reset_acc and suppress_join_msg do not ship in the minqlx default preset, so they stay
# baseline-only: present in every instance's plugin directory, not offered by the picker.
PRESET_VISIBLE_PORTS = ['commands.py', 'myFun.py', 'player_info.py', 'specqueue.py']


def test_the_preset_ships_the_pickable_qlsm_ports():
    missing = [name for name in PRESET_VISIBLE_PORTS
               if not os.path.isfile(os.path.join(PRESET_DIR, 'scripts', name))]
    assert missing == [], f"missing from the preset: {missing}"


def test_preset_scripts_match_the_baseline_ports():
    """The preset carries copies, and two copies drift.

    The minqlx side already has exactly this drift: its default preset's
    specqueue.py has the AFK sweep dedented out of its elif, so it spectates every
    player on every pass, while ql-assets/data/minqlx-plugins/specqueue.py is
    correct. This stops the minqlxtended side acquiring its own version of that.
    """
    import filecmp
    drifted = [
        name for name in PRESET_VISIBLE_PORTS
        if not filecmp.cmp(os.path.join(BASELINE_DIR, name),
                           os.path.join(PRESET_DIR, 'scripts', name), shallow=False)
    ]
    assert drifted == [], f"preset copies drifted from the baseline: {drifted}"


def test_the_system_plugin_is_not_pickable():
    """serverchecker is backfilled as a SYSTEM_PLUGIN and must never be untickable."""
    assert not os.path.isfile(
        os.path.join(PRESET_DIR, 'scripts', 'serverchecker.py'))
