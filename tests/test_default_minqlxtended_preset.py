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


def test_the_declared_binary_is_the_highfps_hook(manifest):
    """P4 ships one .so companion, and only one.

    _validate_binary_descriptions (ui/builtin_presets.py:27) rejects the whole preset
    at seed time if a declared key has no file behind it, so a typo here takes the
    preset out entirely rather than degrading it.
    """
    assert set(manifest.get('binary_descriptions', {})) == {'scripts/highfps_hook.so'}


def test_every_declared_binary_exists(manifest):
    """A declared key with no file behind it takes the whole preset out at seed time,
    so this is the cheap check that stops a typo becoming a missing preset."""
    for key in manifest.get('binary_descriptions', {}):
        assert os.path.isfile(os.path.join(PRESET_DIR, key)), key


#: sha256 of highfps_hook.so as built in dngrtech/qlsm_plugins at `462e3e5`.
#:
#: The hook detours SV_ClientThink inside qzeroded and knows nothing about either
#: Python runtime, so there is one build and both runtimes should ship it. Pinned by
#: hash *as well as* compared against the minqlx copy below, so that rebuilding both at
#: once still has to be a deliberate act that updates this line.
HIGHFPS_HOOK_SHA256 = '8f73853c34042c94220f7c3dd04f32c36f75b68f41346afaf865377cb573e435'


def test_the_hook_binary_is_the_current_qlsm_plugins_build():
    import hashlib
    with open(os.path.join(PRESET_DIR, 'scripts', 'highfps_hook.so'), 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    assert digest == HIGHFPS_HOOK_SHA256, (
        "highfps_hook.so is not the build this preset was written against; "
        "re-copy from qlsm_plugins/minqlxtended/highfps/ after running `make` there")


def test_the_two_presets_ship_the_same_hook_build():
    """The hook is runtime-agnostic, so there is one build and both presets ship it.

    This replaces a `test_the_minqlx_preset_hook_is_known_stale` that existed for the
    length of one commit. QLSM's minqlx preset had been shipping a highfps that predated
    the qlsm_plugins review fixes in `ad193dc` — a different .so build (16768 bytes
    against 18112) and a highfps.py missing the safe !highfps baseline. `971c5dd` on
    `main` synced both, so the two runtimes are back on one build and this can be a plain
    equality assertion again.
    """
    import filecmp
    ours = os.path.join(PRESET_DIR, 'scripts', 'highfps_hook.so')
    theirs = os.path.join(MINQLX_PRESET_DIR, 'scripts', 'highfps_hook.so')
    assert filecmp.cmp(ours, theirs, shallow=False), (
        "highfps_hook.so differs between the two presets; it is runtime-agnostic and "
        "should be the same binary in both — rebuild via `make` in qlsm_plugins and "
        "re-copy, rather than rebuilding one of them alone")


def test_the_two_presets_ship_the_same_highfps_source():
    """The .py differs only by runtime; everything else must track together."""
    with open(os.path.join(PRESET_DIR, 'scripts', 'highfps.py'), encoding='utf-8') as handle:
        ours = handle.read()
    with open(os.path.join(MINQLX_PRESET_DIR, 'scripts', 'highfps.py'), encoding='utf-8') as handle:
        theirs = handle.read()
    assert ours == theirs.replace('import minqlx\n', 'import minqlxtended\n') \
                         .replace('minqlx.Plugin', 'minqlxtended.Plugin') \
                         .replace('minqlx.console_print', 'minqlxtended.console_print') \
                         .replace('MinQLX plugin', 'minqlxtended plugin'), (
        "the two highfps copies have diverged by more than the runtime rename")


def test_the_hook_description_matches_the_minqlx_one(manifest):
    """Same binary, same explanation. The UI shows this text next to the file."""
    import json as _json
    with open(os.path.join(MINQLX_PRESET_DIR, 'preset.json'), 'r', encoding='utf-8') as handle:
        theirs = _json.load(handle)['binary_descriptions']['scripts/highfps_hook.so']
    assert manifest['binary_descriptions']['scripts/highfps_hook.so'] == theirs


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
#: reset_acc and suppress_join_msg used to sit here too, on the grounds that the minqlx
#: default preset does not ship them either. They moved into the preset when the
#: third-party ports below landed: `replacement_scripts()` (preset_compat.py:61) reads
#: THIS directory and nothing else, so a plugin absent from it is a plugin the
#: cross-runtime import dialog cannot offer as a replacement. Both were already ported
#: in P3 and needed no work -- only somewhere to be seen from.
BASELINE_ONLY = {'serverchecker.py'}


#: Pickable plugins that are not in the vendored baseline.
#:
#: highfps lives in dngrtech/qlsm_plugins, not in ql-assets/data/. It ships only in the
#: preset on both runtimes, exactly as its minqlx counterpart does, because it needs a
#: native .so companion beside it and the baseline directory carries no binaries.
#:
#: The rest are third-party plugins QLSM ported so the cross-runtime import dialog has
#: something to offer for them. They are deliberately preset-only rather than vendored:
#: the baseline is "upstream at the pinned commit, plus QLSM's own seven ports", every
#: file in it lands in every instance's plugin directory regardless of preset, and
#: neither is true of someone else's plugin that QLSM merely carries a port of.
#:
#: ServerStatus.py is absent on purpose and is not an oversight. It ships in the minqlx
#: default preset but is not a plugin at all -- it is an Oracle WebLogic admin script
#: (cmo.getServers(), ServerLifeCycleRuntimes) written in Python 2, which reads
#: sys.argv[1:6] at import. There is nothing to port.
PRESET_ONLY = {
    'highfps.py',
    # BarelyMiSSeD
    'clanmembers.py', 'getmap.py', 'listmaps.py', 'mapLimiter.py', 'players_db.py',
    'protect.py', 'restartserver.py', 'serverBDM.py', 'specall.py', 'voteban.py',
    # ShiN0 (mydiscordbot's discord_extensions/ helpers are subdirectory files and so
    # are not counted by this test, which lists the plugin root only)
    'mydiscordbot.py',
    # Mino
    'commlink.py', 'commlink_secured.py', 'irc.py',
    # iouonegirl
    'intermission.py', 'iouonegirl.py', 'mybalance.py',
    # mattiZed / Thomas Jones / cstewart90
    'kills.py', 'onjoin.py', 'servers.py',
    # unattributed
    'block.py', 'kickban.py', 'linodefw.py', 'playerpings.py', 'uberstats.py',
    # X76-preset plugins, ported at the operator's request
    'improved_timer.py', 'protected_flag.py', 'ranked.py', 'spec_switch_guard.py',
}


def test_scripts_match_the_vendored_baseline():
    """The picker offers the whole baseline bar the three that are deliberately out,
    plus the preset-only plugins that do not live in the baseline at all."""
    preset_scripts = {n for n in os.listdir(os.path.join(PRESET_DIR, 'scripts')) if n.endswith('.py')}
    baseline = {n for n in os.listdir(BASELINE_DIR) if n.endswith('.py')}
    assert preset_scripts == (baseline - BASELINE_ONLY) | PRESET_ONLY


def test_the_preset_offers_highfps_exactly_as_the_minqlx_default_does():
    """Parity is the point: an operator moving between runtimes is offered the same
    set. highfps ships in both presets' scripts/ and is checked in neither."""
    for directory in (PRESET_DIR, MINQLX_PRESET_DIR):
        assert os.path.isfile(os.path.join(directory, 'scripts', 'highfps.py')), directory
        with open(os.path.join(directory, 'checked_plugins.json'), 'r', encoding='utf-8') as handle:
            assert 'highfps.py' not in json.load(handle), directory


def test_the_ported_highfps_is_the_current_qlsm_plugins_version():
    """Ported from dngrtech/qlsm_plugins at `462e3e5`, which carries the review fixes
    from `ad193dc`.

    QLSM's *minqlx* preset copy predated those until `971c5dd` on `main` synced it, so at
    the time of the port, porting from it would have carried a false-positive source onto
    the new runtime. Both copies now carry these fixes and
    test_the_two_presets_ship_the_same_highfps_source keeps them together; these markers
    stay as the explicit record of what had to be true for the port to be correct.

    Each marker below is one of those fixes.
    """
    with open(os.path.join(PRESET_DIR, 'scripts', 'highfps.py'), 'r', encoding='utf-8') as handle:
        source = handle.read()
    # A !highfps baseline of 0 reports counts-since-connect as FPS.
    assert 'not sampled yet' in source
    # A non-numeric or zero sample interval used to raise or divide by zero.
    assert 'max(1, int(self.get_cvar("qlx_highfpsSampleInterval")' in source
    # Detection fires above threshold + padding, not at the threshold itself.
    assert 'qlx_highfpsPadding' in source


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


# The QLSM ports that are pickable from this preset, and so exist as a preset copy of a
# baseline file. myFun, specqueue, player_info and commands ship in the minqlx default
# preset's scripts/, so their ports ship here. reset_acc and suppress_join_msg joined
# them when the preset became the source the import dialog offers replacements from; see
# BASELINE_ONLY. Every name here is checked for drift against the baseline below.
PRESET_VISIBLE_PORTS = ['commands.py', 'myFun.py', 'player_info.py', 'reset_acc.py',
                        'specqueue.py', 'suppress_join_msg.py']


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
    import difflib
    import filecmp

    report = []
    for name in PRESET_VISIBLE_PORTS:
        baseline = os.path.join(BASELINE_DIR, name)
        copy = os.path.join(PRESET_DIR, 'scripts', name)
        if filecmp.cmp(baseline, copy, shallow=False):
            continue
        # "files differ" alone sends the reader off to diff 2400 lines by hand.
        with open(baseline, encoding='utf-8') as a, open(copy, encoding='utf-8') as b:
            diff = list(difflib.unified_diff(
                a.readlines(), b.readlines(),
                fromfile=baseline, tofile=copy, n=1))
        report.append(''.join(diff[:40]))

    assert report == [], (
        "preset copies drifted from the baseline; re-copy from "
        f"{BASELINE_DIR}:\n\n" + "\n".join(report))


def test_the_system_plugin_is_not_pickable():
    """serverchecker is backfilled as a SYSTEM_PLUGIN and must never be untickable."""
    assert not os.path.isfile(
        os.path.join(PRESET_DIR, 'scripts', 'serverchecker.py'))
