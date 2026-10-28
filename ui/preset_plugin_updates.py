"""Check for Updates for user presets.

A preset's scripts/ folder holds physical copies of the plugins it was saved
with, and every instance created from it gets those copies. Nothing refreshed
them, so a plugin fixed in the pool kept shipping its old version to every new
instance built from a preset saved before the fix.

Same rules as the per-instance diff in ui/task_logic/plugin_update_check.py:
the merged pool for the preset's own runtime is the source of truth, only root
files with a plugin extension are compared, and only filenames the preset
already holds -- a pool plugin the preset leaves out is delivered by the
deploy backfill and is not stale. So every change is "modified".

Built-in presets are not handled here: their scripts are mirrored from the
pool by `flask sync-plugin-pool` as part of a release.
"""
import os
import shutil

from ui.plugin_pool import pool_file_hashes, resolve_pool_file
from ui.runtime import normalize_runtime
from ui.update_checks import PLUGIN_EXTENSIONS, diff_trees, hash_local_tree


def check_preset_plugins(runtime, scripts_dir):
    """Returns {"plugin_changes": [...], "plugins": [...]} for one preset.

    plugin_changes uses the diff_trees shape ({"name", "change"}), as the host
    check does. plugins lists every root plugin file in the preset with a
    status: "outdated" (pool has a different version), "current" (same hash)
    or "local" (not in the pool, e.g. a plugin written for this preset)."""
    runtime = normalize_runtime(runtime)
    source = pool_file_hashes(runtime, extensions=PLUGIN_EXTENSIONS)
    target = hash_local_tree(scripts_dir, extensions=PLUGIN_EXTENSIONS)
    shared = source.keys() & target.keys()
    changes = diff_trees({n: source[n] for n in shared}, {n: target[n] for n in shared})
    outdated = {c["name"] for c in changes}

    plugins = []
    for name in sorted(target):
        if name in outdated:
            status = "outdated"
        elif name in source:
            status = "current"
        else:
            status = "local"
        plugins.append({"name": name, "status": status})
    return {"plugin_changes": changes, "plugins": plugins}


def apply_preset_plugin_updates(runtime, scripts_dir, filenames=None):
    """Copies the pool version of the selected outdated files into the
    preset's scripts/ folder. `filenames=None` means every outdated file.

    A name that is not currently outdated (already current, not in the
    preset, not in the pool, or not a bare filename) is skipped, never
    written: this only refreshes copies the preset already holds.
    Returns (updated, skipped), both sorted lists of names."""
    runtime = normalize_runtime(runtime)
    outdated = {c["name"] for c in check_preset_plugins(runtime, scripts_dir)["plugin_changes"]}
    wanted = outdated if filenames is None else set(filenames)

    updated, skipped = [], []
    for name in sorted(wanted):
        src = resolve_pool_file(runtime, name) if name in outdated else None
        if not src:
            skipped.append(name)
            continue
        shutil.copyfile(src, os.path.join(scripts_dir, name))
        updated.append(name)
    return updated, skipped
