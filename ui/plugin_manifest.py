"""Shared plugin manifest (<plugin>.ql-plugin.json) lookup.

Used by both script_routes.py (/api/scripts/tree, not currently called by
the frontend) and draft_routes.py (the draft workspace the Plugins tab
actually reads/writes through — see useDraftAdapter / useDraftWorkspace).
Manifest metadata (label/description/commands/cvars) is purely optional
display/edit enrichment; a plugin with none still works as a plain checkbox.
"""

import json
import os

from flask import current_app

PLUGIN_MANIFEST_SUFFIX = '.ql-plugin.json'
PLUGIN_MANIFEST_MAX_SIZE = 16 * 1024  # 16KB — metadata only, not a data file

# Central plugin pool, same one ansible/backup use (see
# ui/task_logic/backup_files.py MINQLX_PLUGINS_DIR). Manifest fallback source:
# a preset/instance copy of a plugin can predate manifests entirely, or have
# been uploaded/customized without its own sidecar — falling back to the pool
# by filename means the manifest still shows up wherever the plugin does,
# without needing every preset/instance copy kept in sync by hand.
MINQLX_PLUGINS_POOL_DIR = os.path.join('ql-assets', 'data', 'minqlx-plugins')
MINQLXTENDED_PLUGINS_POOL_DIR = os.path.join('ql-assets', 'data', 'minqlxtended-plugins')


def _pool_dirs(runtime=None):
    """Pools to look a manifest up in, best match first.

    The two runtimes carry their own copy of the same plugin filenames, and
    those copies do drift (a cvar added on one side, a command renamed on the
    other), so an instance's own runtime pool has to win when we know it. The
    other pool is still tried afterwards: stale-but-close metadata is more
    useful than none, and it is what this lookup did before runtimes were
    split at all."""
    from ui.runtime import MINQLXTENDED, is_valid_runtime  # local import: no import cycle at module load

    ordered = []
    if is_valid_runtime(runtime):
        ordered.append(
            MINQLXTENDED_PLUGINS_POOL_DIR if runtime.strip().lower() == MINQLXTENDED
            else MINQLX_PLUGINS_POOL_DIR
        )
    for pool in (MINQLX_PLUGINS_POOL_DIR, MINQLXTENDED_PLUGINS_POOL_DIR):
        if pool not in ordered:
            ordered.append(pool)
    return [os.path.abspath(pool) for pool in ordered]


def load_manifest_file(manifest_path):
    """Read+parse a single manifest file. Never raises — a bad manifest just
    means no enrichment, the plugin itself still works as a plain checkbox."""
    if not os.path.isfile(manifest_path):
        return None
    try:
        if os.path.getsize(manifest_path) > PLUGIN_MANIFEST_MAX_SIZE:
            current_app.logger.warning(f"Plugin manifest too large, ignoring: {manifest_path}")
            return None
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, ValueError) as e:
        current_app.logger.warning(f"Failed to read plugin manifest {manifest_path}: {e}")
        return None


def read_plugin_manifest(script_full_path, runtime=None):
    """Manifest for a plugin .py file: the central pool wins when it has an
    entry for this filename. ql-assets is the source of truth for manifests
    (see qlsm-plugin-pool-vs-builtin-preset-duplication in project memory) —
    routing through the pool first means every preset/instance copy of a
    known plugin shows the same, current metadata, with no per-copy drift
    and no need to hand-sync a sidecar into every place the plugin is used.
    Falls back to a sidecar next to the file itself only for plugins that
    aren't in the pool at all (a custom/one-off plugin an operator wrote
    directly for one preset or instance)."""
    basename = os.path.splitext(os.path.basename(script_full_path))[0]
    tried = []
    for pool in _pool_dirs(runtime):
        pool_manifest = os.path.join(pool, basename + PLUGIN_MANIFEST_SUFFIX)
        tried.append(os.path.abspath(pool_manifest))
        manifest = load_manifest_file(pool_manifest)
        if manifest is not None:
            return manifest

    local_manifest = os.path.splitext(script_full_path)[0] + PLUGIN_MANIFEST_SUFFIX
    if os.path.abspath(local_manifest) in tried:
        return None  # already tried this exact file above (browsing the pool itself)
    return load_manifest_file(local_manifest)
