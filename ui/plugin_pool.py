"""The shared plugin pool, in two tiers per runtime.

- built-in: ql-assets/data/<runtime>-plugins/ -- ships inside the image and
  is only ever changed by a QLSM release. Read-only at runtime.
- operator: data/shared-plugins/<runtime>/ -- everything the operator pulls
  in from a plugin repository. `data/` is a bind mount shared by every
  container (web, workers, poller), so a download made by the web process
  is visible to the worker that later ships it to a host, and it survives
  an image update. Writing into ql-assets/ instead would land in the web
  container's own layer only, which is the bug this split fixes.

Every reader sees one merged view: the built-in files, overlaid by operator
files of the same name. Setup and Check for Updates push that merged view
to each host's /home/ql/assets/common/<runtime>-plugins/, and deploy
backfills it into every instance's plugin folder with `rsync
--ignore-existing`. So a root-level plugin in either tier is loadable by any
instance on that runtime, whether or not the instance's own scripts/
snapshot holds a copy. The config editor's Plugins tab lists these as
"shared" rows next to the draft's own files.
"""
import os

from ui.runtime import is_valid_runtime, runtime_paths

POOL_BASE = os.path.join('ql-assets', 'data')
OPERATOR_POOL_BASE = os.path.join('data', 'shared-plugins')


def builtin_pool_dir(runtime):
    return os.path.abspath(os.path.join(POOL_BASE, runtime_paths(runtime)['asset_plugins_dir']))


def operator_pool_dir(runtime):
    # Keyed by the runtime name itself ('minqlx' / 'minqlxtended'), not the
    # on-host dirname: the operator folder has no reason to mirror the
    # host-side layout, and the shorter path is what the docs show.
    return os.path.abspath(os.path.join(OPERATOR_POOL_BASE, runtime_paths(runtime)['runtime']))


def pool_dirs(runtime):
    """Both tiers, highest priority first."""
    return [operator_pool_dir(runtime), builtin_pool_dir(runtime)]


def resolve_pool_file(runtime, filename):
    """Absolute path of `filename` in the merged view (operator copy wins),
    or None when neither tier has it. `filename` is a bare root name."""
    if not is_valid_runtime(runtime):
        return None
    if not isinstance(filename, str) or os.path.basename(filename) != filename:
        return None
    for root in pool_dirs(runtime):
        path = os.path.join(root, filename)
        if os.path.isfile(path):
            return path
    return None


def resolve_pool_path(runtime, relpath):
    """Absolute path of a possibly-nested `relpath` in the merged view
    (operator copy wins), or None when neither tier has it.

    Unlike resolve_pool_file, `relpath` may contain forward-slash
    subdirectories -- for a package-style plugin that ships a helper folder
    alongside its root .py (e.g. match_restore.py's restore/ package, see
    ui/plugin_repositories.py's `package_files`). The caller is responsible
    for rejecting unsafe segments (`..`, absolute, drive-qualified) before
    calling this; this only joins and checks existence, rejecting the
    obviously-wrong shapes defensively.
    """
    if not is_valid_runtime(runtime):
        return None
    if not isinstance(relpath, str) or not relpath:
        return None
    parts = relpath.split('/')
    if any(not p or p in ('.', '..') for p in parts):
        return None
    for root in pool_dirs(runtime):
        path = os.path.join(root, *parts)
        if os.path.isfile(path):
            return path
    return None


def _root_files(root, keep):
    """{name: path} for regular files directly under `root` that pass
    `keep(name)`. Subfolders are helper modules, not plugins, and are
    skipped. A missing tier is simply empty."""
    try:
        entries = list(os.scandir(root))
    except OSError:
        return {}
    return {entry.name: entry.path for entry in entries if entry.is_file() and keep(entry.name)}


def list_shared_plugins(runtime):
    """{filename: absolute path} for every root-level plugin in `runtime`'s
    merged pool. An unknown runtime has no pool to read, so it returns {}."""
    if not is_valid_runtime(runtime):
        return {}
    # Not operator-selectable: __init__.py is package glue, and system
    # plugins are injected into qlx_plugins by QLSM itself. Local import:
    # the task module pulls in rq/ansible helpers this module doesn't need.
    from ui.task_logic.ansible_instance_mgmt import SYSTEM_PLUGINS
    excluded = {'__init__.py'} | {f'{name}.py' for name in SYSTEM_PLUGINS}
    keep = lambda name: name.endswith('.py') and name not in excluded
    merged = {}
    # Lowest priority first so a later tier overrides by name.
    for root in reversed(pool_dirs(runtime)):
        merged.update(_root_files(root, keep))
    return merged


def pool_file_hashes(runtime, extensions=None):
    """{filename: sha256} of the merged view, for Check for Updates. Same
    file rules as ui.update_checks.hash_local_tree (flat, filtered by
    `extensions`), applied per tier with the operator copy winning."""
    from ui.update_checks import hash_local_tree  # local: keeps this module free of the hashing deps at import
    if not is_valid_runtime(runtime):
        return {}
    merged = {}
    for root in reversed(pool_dirs(runtime)):
        merged.update(hash_local_tree(root, extensions=extensions))
    return merged


def pool_package_hashes(runtime, dirnames, extensions=None):
    """{relpath: sha256} of the named package folders (a plugin's helper
    package, e.g. match_restore.py's restore/) in the merged view, operator
    copy winning per file. Same relpath shape as `package_files`."""
    from ui.update_checks import hash_package_trees  # local, as in pool_file_hashes
    if not is_valid_runtime(runtime):
        return {}
    merged = {}
    for root in reversed(pool_dirs(runtime)):
        merged.update(hash_package_trees(root, dirnames, extensions=extensions))
    return merged


def shared_plugin_path(runtime, path):
    """Absolute pool path when `path` names a shared plugin exactly (a bare
    root filename, never a nested or relative path), else None."""
    if not isinstance(path, str) or os.path.basename(path) != path:
        return None
    return list_shared_plugins(runtime).get(path)


def shared_plugin_nodes(runtime, existing_root_names, read_manifest):
    """Draft-tree file nodes for shared plugins the draft doesn't already
    hold at its root. A local file of the same name always wins -- it is the
    copy that ends up on the host, since the deploy backfill never
    overwrites. `read_manifest(full_path, runtime)` attaches plugin metadata
    the same way the draft's own rows get it."""
    nodes = []
    for name, full_path in sorted(list_shared_plugins(runtime).items()):
        if name in existing_root_names:
            continue
        stat = os.stat(full_path)
        node = {
            'name': name,
            'type': 'file',
            'path': name,
            'file_type': 'python',
            'size': stat.st_size,
            'last_modified': stat.st_mtime,
            'shared': True,
        }
        manifest = read_manifest(full_path, runtime)
        if manifest:
            node['plugin_manifest'] = manifest
        nodes.append(node)
    return nodes
