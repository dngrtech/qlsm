"""Check for Updates for user presets.

A preset's scripts/ folder holds physical copies of the plugins it was saved
with, and every instance created from it gets those copies. Nothing refreshed
them, so a plugin fixed in the pool kept shipping its old version to every new
instance built from a preset saved before the fix.

The per-instance check and copy are reused as they are
(plugin_update_check.check_selected_plugins and
ansible_plugin_update.copy_selected_plugin_files): the merged pool for the
preset's own runtime is the source of truth, root plugin files are compared
only when the preset already holds them (a pool plugin the preset leaves out
is delivered by the deploy backfill and is not stale), and every helper
package folder the preset carries (restore/ of match_restore.py) is compared
file by file, so a refreshed plugin never ships next to an old helper.

Built-in presets are not handled here: their scripts are mirrored from the
pool by `flask sync-plugin-pool` as part of a release.
"""
from ui.plugin_pool import pool_file_hashes
from ui.runtime import normalize_runtime
from ui.task_logic.ansible_plugin_update import copy_selected_plugin_files
from ui.task_logic.plugin_update_check import check_selected_plugins
from ui.update_checks import PLUGIN_EXTENSIONS, hash_local_tree


def check_preset_plugins(runtime, scripts_dir):
    """Returns {"plugin_changes": [...], "plugins": [...]} for one preset.

    plugin_changes uses the diff_trees shape ({"name", "change"}), as the host
    check does. plugins lists every root plugin file in the preset with a
    status: "outdated" (pool has a different version), "current" (same hash)
    or "local" (not in the pool, e.g. a plugin written for this preset).
    plugins covers root files only; a stale helper package shows up in
    plugin_changes by its file names ("restore/items.py")."""
    runtime = normalize_runtime(runtime)
    changes = check_selected_plugins(runtime, scripts_dir)
    source = pool_file_hashes(runtime, extensions=PLUGIN_EXTENSIONS)
    target = hash_local_tree(scripts_dir, extensions=PLUGIN_EXTENSIONS)
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
    preset's scripts/ folder. `filenames=None` means every outdated file,
    helper package files ("restore/items.py") included.

    A name that is not currently outdated (already current, not in the
    preset, not in the pool) is skipped, never written: this only refreshes
    copies the preset already holds and completes its helper packages.
    Returns (updated, skipped), both sorted lists of names."""
    runtime = normalize_runtime(runtime)
    outdated = {c["name"] for c in check_selected_plugins(runtime, scripts_dir)}
    wanted = outdated if filenames is None else set(filenames)
    skipped = sorted(wanted - outdated)
    applied, copy_skipped = copy_selected_plugin_files(
        runtime, scripts_dir, sorted(wanted & outdated),
    )
    return sorted(applied), sorted(skipped + copy_skipped)
