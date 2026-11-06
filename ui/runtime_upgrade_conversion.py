"""Converted per-instance state for a host runtime upgrade.

Everything here reads the operation's immutable materialized inputs (the
snapshot's `inputs/` directory, see ui/runtime_upgrade_snapshot.py), never the
live configs/ tree or live shipped assets, so what is converted is exactly
what the operator confirmed.

The operator's dialog answers (HostRuntimeUpgradeOperation.answers_json) are
the replacements they ticked, per instance:

    {"<instance_id>": ["balance.py", ...], ...}

Instances without a decision may be omitted. A list may also carry the
instance's captured `auto_accepted` paths (what combineAcceptedPaths sends);
they are applied regardless and dropped from the ticked set. The conversion
accepts the
captured `auto_accepted` replacements plus the ticked ones, the same
`auto_accepted + ticked` set the preset-load dialog hands the draft filter
(frontend combineAcceptedPaths), and recomputes the plugin selection the way
the frontend's mergeReplacements does.
"""
import json
import os
import shutil

from ui.preset_compat import baseline_hashes_from, replacement_scripts_from, shipped_scripts_from
from ui.runtime_conversion import filter_scripts_for_target
from ui.runtime_upgrade import UPGRADE_TARGET_RUNTIME, UpgradeInputsChanged
from ui.runtime_upgrade_snapshot import tree_inventory


class AnswersInvalid(UpgradeInputsChanged):
    """The operator's answers do not match the captured classification."""


# --- answers -----------------------------------------------------------------

def _captured_by_id(inputs):
    return {int(item['instance_id']): item for item in inputs.get('instances') or []}


def _offered(captured):
    """Paths the dialog offered a checkbox for: reported strips with a replacement."""
    rows = (captured.get('classification') or {}).get('stripped') or []
    return {row['path'] for row in rows if row.get('replacement')}


def parse_answers(inputs, answers_json):
    """{instance_id: sorted ticked paths} for every captured instance.

    Raises AnswersInvalid for an unknown instance id, a malformed value, or a
    path that is neither offered nor auto-accepted for that instance.
    """
    try:
        raw = json.loads(answers_json) if answers_json else {}
    except ValueError as exc:
        raise AnswersInvalid('Upgrade answers are not valid JSON') from exc
    if not isinstance(raw, dict):
        raise AnswersInvalid('Upgrade answers must be an object keyed by instance id')
    captured = _captured_by_id(inputs)
    answers = {instance_id: [] for instance_id in captured}
    for key, ticked in raw.items():
        try:
            instance_id = int(key)
        except (TypeError, ValueError):
            raise AnswersInvalid(f'Upgrade answers name an invalid instance id {key!r}') from None
        if instance_id not in captured:
            raise AnswersInvalid(f'Upgrade answers name instance {instance_id}, which was not captured')
        if not isinstance(ticked, list) or not all(isinstance(path, str) for path in ticked):
            raise AnswersInvalid(f'Upgrade answers for instance {instance_id} must be a list of paths')
        auto = set((captured[instance_id].get('classification') or {}).get('auto_accepted') or [])
        ticked = set(ticked) - auto
        unknown = sorted(ticked - _offered(captured[instance_id]))
        if unknown:
            raise AnswersInvalid(f'Instance {instance_id}: {", ".join(unknown)} was not offered a replacement')
        answers[instance_id] = sorted(ticked)
    return answers


def accepted_replacements(captured, ticked):
    """auto_accepted + ticked, as the draft filter takes them."""
    auto = (captured.get('classification') or {}).get('auto_accepted') or []
    return sorted(set(auto) | set(ticked or []))


# --- converted DB fields -------------------------------------------------------

def converted_plugin_selection(captured, ticked):
    """The converted QLInstance.qlx_plugins.

    NULL (and '') selections are kept as they are: neither means "the operator
    picked nothing". Otherwise, in the original order: a plugin keeps its tick
    unless the dialog reported it stripped and the operator did not tick its
    replacement (mergeReplacements semantics). That rule also covers plugins
    enabled from the source runtime's shared pool: the capture reports each one
    either auto-accepted (kept; the file comes from the target preset via the
    filter, or from the target pool via the host's backfill) or as a row.
    """
    effective = captured.get('qlx_plugins_effective')
    if effective is None:
        return captured.get('qlx_plugins_raw')
    stripped = {row['path'] for row in (captured.get('classification') or {}).get('stripped') or []}
    ticked = set(ticked or [])
    kept = [path for path in effective if path not in stripped or path in ticked]
    return ', '.join(path[:-3] if path.endswith('.py') else path for path in kept)


def converted_ld_preload_hooks(ld_preload_hooks, excluded):
    """ld_preload_hooks without the hooks the target provides natively
    (runtime_paths(target)['excluded_system_hooks'], e.g. force_rate.so)."""
    if not ld_preload_hooks:
        return ld_preload_hooks
    names = [name.strip() for name in ld_preload_hooks.split(',') if name.strip()]
    kept = [name for name in names if name not in set(excluded or ())]
    if kept == names:
        return ld_preload_hooks
    return ','.join(kept) or None


# --- converted trees -------------------------------------------------------------

def _discard(path):
    if os.path.lexists(path):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)


def target_filter_inputs(inputs_dir):
    """What the target ships, read from the materialized inputs."""
    default_scripts = os.path.join(inputs_dir, 'target_default_preset_scripts')
    return {
        'hashes': baseline_hashes_from(os.path.join(inputs_dir, 'target_baseline', 'manifest.json')),
        'candidates': replacement_scripts_from(default_scripts),
        'shipped_by_target': shipped_scripts_from(default_scripts),
    }


def build_converted_tree(inputs_dir, captured, ticked, excluded, dest):
    """Write the converted config tree of one instance into `dest` (replaced
    if present) and return the converted DB fields.

    The source is the instance's immutable materialized copy; the filter is
    the draft runtime filter fed from the materialized target assets.
    """
    instance_id = int(captured['instance_id'])
    source = os.path.join(inputs_dir, 'instances', str(instance_id))
    if not os.path.isdir(source):
        raise UpgradeInputsChanged(f'Materialized inputs of instance {instance_id} are missing')
    _discard(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(source, dest, copy_function=shutil.copy2, symlinks=True)
    scripts = os.path.join(dest, 'scripts')
    if os.path.isdir(scripts):
        filter_scripts_for_target(
            scripts, UPGRADE_TARGET_RUNTIME,
            accepted_replacements=accepted_replacements(captured, ticked),
            **target_filter_inputs(inputs_dir))
    return {
        'qlx_plugins': converted_plugin_selection(captured, ticked),
        'ld_preload_hooks': converted_ld_preload_hooks(captured.get('ld_preload_hooks'), excluded),
    }


def excluded_hooks(inputs):
    """The target's excluded_system_hooks as captured at confirmation."""
    return set((inputs.get('target_runtime') or {}).get('excluded_system_hooks') or ())


def build_target_system_hooks(inputs_dir, excluded, dest):
    """The built-in system hooks to stage for the target: the materialized
    copy minus the hooks the target provides natively."""
    source = os.path.join(inputs_dir, 'system_hooks')
    _discard(dest)
    os.makedirs(dest)
    if os.path.isdir(source):
        for name in sorted(os.listdir(source)):
            path = os.path.join(source, name)
            if name in excluded or not os.path.isfile(path) or os.path.islink(path):
                continue
            shutil.copy2(path, os.path.join(dest, name))
    return dest


# --- swapping a converted tree into configs/ ---------------------------------------

def conversion_paths(live, tag):
    """(staged, original) sibling paths of a live instance directory.

    Named apart from the snapshot restore's `.upgrade-restore-*` and
    `.upgrade-backup-*` so a rollback after an interrupted conversion never
    collides with them.
    """
    parent = os.path.dirname(os.path.normpath(live))
    return (os.path.join(parent, f'.upgrade-convert-{tag}'),
            os.path.join(parent, f'.upgrade-original-{tag}'))


def same_tree(left, right):
    return os.path.isdir(left) and os.path.isdir(right) and tree_inventory(left) == tree_inventory(right)


def install_converted_tree(live, converted, tag):
    """Replace the live config directory with a copy of `converted`.

    live is renamed aside (to `original`) only after the staged copy is
    complete, then staged is renamed into place. Rerunning after a crash at
    any point finishes the swap. The snapshot, not `original`, is what a
    rollback restores from; `original` is removed by discard_conversion_leftovers.
    """
    staged, original = conversion_paths(live, tag)
    if same_tree(live, converted):
        _discard(staged)
        return
    if os.path.lexists(live) and os.path.lexists(original):
        raise RuntimeError(f'Both {live} and {original} exist; refusing to swap')
    _discard(staged)
    shutil.copytree(converted, staged, copy_function=shutil.copy2, symlinks=True)
    if os.path.lexists(live):
        os.rename(live, original)
    os.rename(staged, live)
    if not same_tree(live, converted):
        raise RuntimeError(f'Converted directory {live} does not match {converted}')


def discard_conversion_leftovers(live, tag):
    for path in conversion_paths(live, tag):
        _discard(path)
