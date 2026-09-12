"""Keeps configs/presets/_builtin/default/scripts/ (the builtin "default"
ConfigPreset, physically copied onto every instance created from it) in sync
with ql-assets/data/minqlx-plugins/ (the host-baseline pool ansible deploys
to every fresh host, and the source of truth for plugin logic) -- but only
for the subset of files the two trees are actually meant to hold identically.

Manifest (*.ql-plugin.json) *lookup* already prefers the pool at read time
(ui/plugin_manifest.py) regardless of what sits on disk in the preset, but
plugin *code* (*.py) has no such indirection — whatever .py is physically in
the preset's scripts/ dir is what gets copied onto every new instance built
from it. A pool-only fix silently never reaches instances unless someone
remembers to hand-copy it into the preset too. This module removes the
"by hand" step and gives tests something to assert on.

The pool and the default preset are NOT meant to be byte-identical trees,
though, and this module must not pretend otherwise:

- Preset-only additions (highfps/footsteps, togglable LD_PRELOAD hooks with
  no pool equivalent at all) — see PRESET_ONLY.
- Pool plugins the default preset deliberately does not ship at all (an
  operator opts in per-instance, e.g. autokick.py/queue.py/serverchecker.py)
  — see NOT_SHIPPED_BY_DEFAULT. Treating their absence as drift and having
  `sync-plugin-pool` add them would silently change what every new instance
  ships by default.
- Files the default preset deliberately customizes beyond the pool's stock
  version (motd.py's rewritten command set, ban.py, the Discord integration
  files, etc.) — see CUSTOMIZED_IN_PRESET. Content is allowed, expected, to
  differ; ui/preset_compat.py's cross-runtime compatibility gate depends on
  exactly this divergence (it diffs the preset against the pool/manifest
  baseline to tell "operator's own edit" from "stock upstream file"), so
  `sync-plugin-pool` overwriting these would both destroy real customization
  and break that gate's test premises.

What's left — plugins present in both trees with no recorded customization —
is where accidental drift is a real bug (a pool fix landing without ever
reaching an instance built from the default preset), and that's what this
module actually keeps in sync.
"""

import os
import shutil

import click

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL_DIR = os.path.join(ROOT_DIR, 'ql-assets', 'data', 'minqlx-plugins')
PRESET_SCRIPTS_DIR = os.path.join(ROOT_DIR, 'configs', 'presets', '_builtin', 'default', 'scripts')

# Pool-tree files that are install-time infrastructure, not plugin source
# (e.g. requirements.txt is consumed directly by ansible/setup_host.yml, not
# by the preset/instance apply path) — never mirrored into the preset.
POOL_ONLY_NAMES = {'LICENSE', 'README.md', 'requirements.txt', '.gitignore'}

# Preset-tree paths that are intentionally preset-only, not part of the
# ansible host-baseline pool at all: highfps and footsteps are togglable
# per-preset LD_PRELOAD hooks, not generic pool plugins — plus their
# compiled .so files, which never live in the (Python-only) plugin pool
# (see c699cb3, "following the highfps precedent exactly").
PRESET_ONLY = {'highfps.py', 'highfps_hook.so', 'footsteps.py', 'footsteps_hook.so'}

# Pool plugins the default preset intentionally does not ship -- an operator
# opts in per-instance via the Plugins tab, not by having it pre-selected on
# every fresh instance. Never reported as 'missing', never added by
# sync_pool_to_preset. (reset_acc.py/suppress_join_msg.py's exclusion is
# already asserted by test_a_stock_plugin_absent_from_the_default_preset_is_
# not_called_the_operators in tests/test_preset_compat.py; the rest of this
# set follows the same precedent.)
NOT_SHIPPED_BY_DEFAULT = {
    '__init__.py', 'autokick.py', 'check_game_time.py', 'custom_votes.py',
    'custom_votesplus.py', 'draw.py', 'factoryvote.py', 'kickban.py',
    'lastmaps.py', 'namesplus.py', 'queue.py', 'reset_acc.py',
    'serverchecker.py', 'suppress_join_msg.py', 'team_ak.py', 'test_time.py',
    'tests/__init__.py', 'tests/test_balance.py', 'tests/test_block.py',
}

# Files the default preset deliberately customizes beyond the pool's stock
# version. Content is allowed to differ; sync_pool_to_preset never overwrites
# them, and diff_pool_preset never reports the divergence as drift. Presence
# is still checked -- if one of these ever goes missing from the preset
# entirely, that's a real bug, just not a content-sync one.
CUSTOMIZED_IN_PRESET = {
    'ban.py', 'commlink.py', 'discord_extensions/admin.py', 'iouonegirl.py',
    'motd.py', 'mybalance.py', 'mydiscordbot.py',
}

# Plugin logic/manifest files, wherever they sit under the pool root.
SYNCED_SUFFIXES = ('.py', '.ql-plugin.json')

# Data that travels with plugin logic (the map_entities() native-lookup
# migration retired the bundled per-map JSON snapshots from the pool; a
# preset copy that still has them is running stale fallback data). Unlike
# data/checkpoints/ (operator/test artifacts, not plugin source), this dir
# is mirrored too.
MAP_ENTITIES_RELDIR = 'data/map_entities'


def _prune_dirnames(dirpath, dirnames):
    rel_dir = os.path.relpath(dirpath, POOL_DIR).replace(os.sep, '/')
    kept = []
    for name in dirnames:
        if name == '__pycache__':
            continue
        if rel_dir == 'data' and name != 'map_entities':
            continue
        kept.append(name)
    dirnames[:] = kept


def _iter_synced_relpaths(root_dir):
    """Yield '/'-separated relpaths (relative to root_dir) that are in scope
    for pool<->preset sync: *.py / *.ql-plugin.json anywhere, plus
    data/map_entities/* verbatim."""
    for dirpath, dirnames, filenames in os.walk(root_dir):
        _prune_dirnames(dirpath, dirnames)
        rel_dir = os.path.relpath(dirpath, root_dir).replace(os.sep, '/')
        in_map_entities = rel_dir == MAP_ENTITIES_RELDIR
        for name in filenames:
            if name in POOL_ONLY_NAMES:
                continue
            if not (name.endswith(SYNCED_SUFFIXES) or in_map_entities):
                continue
            relpath = name if rel_dir == '.' else f'{rel_dir}/{name}'
            if relpath in PRESET_ONLY:
                continue
            yield relpath


def diff_pool_preset():
    """Return a list of (relpath, reason) pairs describing how the preset
    would change if synced from the pool. reason is one of 'missing',
    'content_differs', 'extra_in_preset'.

    Only covers files the two trees are meant to hold identically: excludes
    NOT_SHIPPED_BY_DEFAULT entirely (never 'missing', regardless of whether
    the preset happens to lack them) and skips the content comparison (but
    not the presence check) for CUSTOMIZED_IN_PRESET."""
    full_pool_relpaths = set(_iter_synced_relpaths(POOL_DIR))
    pool_relpaths = full_pool_relpaths - NOT_SHIPPED_BY_DEFAULT
    preset_relpaths = set(_iter_synced_relpaths(PRESET_SCRIPTS_DIR))

    diffs = []
    for relpath in sorted(pool_relpaths):
        pool_path = os.path.join(POOL_DIR, *relpath.split('/'))
        preset_path = os.path.join(PRESET_SCRIPTS_DIR, *relpath.split('/'))
        if not os.path.isfile(preset_path):
            diffs.append((relpath, 'missing'))
            continue
        if relpath in CUSTOMIZED_IN_PRESET:
            continue
        with open(pool_path, 'rb') as f:
            pool_bytes = f.read()
        with open(preset_path, 'rb') as f:
            preset_bytes = f.read()
        if pool_bytes != preset_bytes:
            diffs.append((relpath, 'content_differs'))

    for relpath in sorted(preset_relpaths - full_pool_relpaths):
        diffs.append((relpath, 'extra_in_preset'))

    return diffs


def sync_pool_to_preset():
    """Make the preset's scripts/ dir match the pool for the synced domain.
    Returns the list of (relpath, reason) actions taken."""
    actions = diff_pool_preset()
    for relpath, reason in actions:
        preset_path = os.path.join(PRESET_SCRIPTS_DIR, *relpath.split('/'))
        if reason == 'extra_in_preset':
            os.remove(preset_path)
            continue
        pool_path = os.path.join(POOL_DIR, *relpath.split('/'))
        os.makedirs(os.path.dirname(preset_path), exist_ok=True)
        shutil.copyfile(pool_path, preset_path)
    return actions


@click.command('sync-plugin-pool')
@click.option('--check', is_flag=True, help='Report drift without writing; exit 1 if any found.')
def sync_plugin_pool_command(check):
    """Sync ql-assets/data/minqlx-plugins/ (pool) onto the builtin default
    preset's scripts/ dir, so plugin .py/.ql-plugin.json fixes land in both
    places. Run after any pool plugin change."""
    diffs = diff_pool_preset()
    if not diffs:
        click.echo('Builtin default preset already matches the plugin pool.')
        return
    if check:
        for relpath, reason in diffs:
            click.echo(f'DRIFT ({reason}): {relpath}')
        click.echo(f'{len(diffs)} file(s) out of sync.')
        raise SystemExit(1)
    for relpath, reason in sync_pool_to_preset():
        click.echo(f'{reason}: {relpath}')
    click.echo(f'Synced {len(diffs)} file(s) from pool to builtin default preset.')
