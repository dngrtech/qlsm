"""The shared plugin pool (ql-assets/data/<runtime>-plugins/).

Setup and Check for Updates push this folder to each host's
/home/ql/assets/common/<runtime>-plugins/, and deploy backfills it into every
instance's plugin folder with `rsync --ignore-existing`. So a root-level
plugin here is loadable by any instance on that runtime, whether or not the
instance's own scripts/ snapshot holds a copy. The config editor's Plugins
tab lists these as "shared" rows next to the draft's own files.
"""
import os

from ui.runtime import is_valid_runtime, runtime_paths

POOL_BASE = os.path.join('ql-assets', 'data')



def pool_dir(runtime):
    return os.path.abspath(os.path.join(POOL_BASE, runtime_paths(runtime)['asset_plugins_dir']))


def list_shared_plugins(runtime):
    """{filename: absolute path} for every root-level plugin in `runtime`'s
    pool. Subfolders are helper modules, not plugins, and are skipped. An
    unknown runtime has no single pool to read, so it returns {}."""
    if not is_valid_runtime(runtime):
        return {}
    # Not operator-selectable: __init__.py is package glue, and system
    # plugins are injected into qlx_plugins by QLSM itself. Local import:
    # the task module pulls in rq/ansible helpers this module doesn't need.
    from ui.task_logic.ansible_instance_mgmt import SYSTEM_PLUGINS
    excluded = {'__init__.py'} | {f'{name}.py' for name in SYSTEM_PLUGINS}
    root = pool_dir(runtime)
    try:
        entries = list(os.scandir(root))
    except OSError:
        return {}
    return {
        entry.name: entry.path
        for entry in entries
        if entry.is_file() and entry.name.endswith('.py') and entry.name not in excluded
    }


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
