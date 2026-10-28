# ui/task_logic/plugin_update_check.py
#
# "Check for Updates" — replaces the old blind "Update Plugins" button.
# The merged plugin pool for the host's runtime (built-in tier in
# ql-assets/data/ overlaid by the operator tier in data/shared-plugins/, see
# ui/plugin_pool.py) is the source of truth. Two independent diffs against it:
#
#  - host common pool (/home/ql/assets/common/minqlx-plugins/ on the VPS) —
#    the shared baseline every instance backfills from on restart.
#  - each instance's own plugin files (configs/{host}/{instance}/scripts/,
#    local to the qlsm controller) — excluded from the common-pool backfill
#    on purpose (an operator may have hand-edited one via the script
#    editor), so they only ever went stale silently. This is the category
#    that caused the match_restore.py incident: an instance's copy with a
#    real upstream fix, and no path for that fix to ever reach it.
#
#    Only filenames the instance already has are compared, so this diff
#    reports "modified" and nothing else. A pool file missing from scripts/
#    is not stale: the restart backfill already delivers it from the host
#    pool. Presets also leave pool plugins out on purpose (serverchecker.py
#    is always delivered that way), so reporting them as "added" flagged
#    every instance with updates it didn't need.
#
# system-hooks (ql-assets/data/system-hooks/) is NOT checked here: that sync
# task in sync_instance_configs_and_restart.yml runs unconditionally on every
# restart with no exclude list, so it self-heals and was never the bug.

import os

from ui.update_checks import (
    hash_local_tree, hash_package_trees, parse_sha256sum_output, diff_trees, PLUGIN_EXTENSIONS,
)
from ui.plugin_pool import pool_file_hashes, pool_package_hashes
from ui.runtime import host_runtime, runtime_paths
from .ssh_command import run_host_ssh_command

COMMON_ASSETS_REMOTE_DIR = "/home/ql/assets/common"


def _pool_hashes(host):
    """{filename: sha256} of the merged pool for this host's runtime."""
    return pool_file_hashes(host_runtime(host), extensions=PLUGIN_EXTENSIONS)


def _common_pool_remote_dir(host):
    return f"{COMMON_ASSETS_REMOTE_DIR}/{runtime_paths(host_runtime(host))['asset_plugins_dir']}"


def _instance_scripts_dir(host_name, instance_id):
    return os.path.abspath(os.path.join('configs', host_name, str(instance_id), 'scripts'))


def check_common_pool(host):
    """Diffs the merged pool vs the host's shared common plugin pool
    (/home/ql/assets/common/{minqlx,minqlxtended}-plugins/, per the host's
    runtime). Returns (changes, error). error is set (changes is None) if
    the host was unreachable."""
    remote_dir = _common_pool_remote_dir(host)
    source = _pool_hashes(host)
    success, stdout, stderr = run_host_ssh_command(
        host,
        f"find {remote_dir} -maxdepth 1 -type f "
        f"\\( -name '*.py' -o -name '*.ql-plugin.json' \\) -exec sha256sum {{}} +",
    )
    if not success:
        return None, stderr or "Failed to read remote plugin pool state"

    target = parse_sha256sum_output(stdout, strip_prefix=remote_dir + "/")
    return diff_trees(source, target), None


def check_instance_selected_plugins(host, instance):
    """Diffs the merged pool vs this instance's own scripts snapshot
    (configs/{host}/{instance}/scripts/) — purely local, no SSH needed.
    Only files present in both are compared, so every change is "modified"
    (see module docstring for why missing pool files aren't reported)."""
    scripts_dir = _instance_scripts_dir(host.name, instance.id)
    source = _pool_hashes(host)
    target = hash_local_tree(scripts_dir, extensions=PLUGIN_EXTENSIONS)
    shared = source.keys() & target.keys()
    changes = diff_trees({n: source[n] for n in shared}, {n: target[n] for n in shared})

    # A package-style plugin (match_restore.py + restore/) keeps helper
    # modules in a subfolder. The flat comparison above never sees them, so a
    # new match_restore.py could sit next to an old restore/ for ever. Compare
    # every helper folder the instance already carries against the same folder
    # in the pool; a pool file new to such a folder is "added" (the package is
    # only loadable as a whole). Files only the instance has are not reported:
    # apply never deletes.
    package_dirs = _instance_package_dirs(scripts_dir)
    if package_dirs:
        source_pkg = pool_package_hashes(host_runtime(host), package_dirs, extensions=PLUGIN_EXTENSIONS)
        target_pkg = hash_package_trees(scripts_dir, package_dirs, extensions=PLUGIN_EXTENSIONS)
        changes += [c for c in diff_trees(source_pkg, target_pkg) if c["change"] != "removed"]
    return sorted(changes, key=lambda c: c["name"])


def _instance_package_dirs(scripts_dir):
    """Names of the helper folders directly under an instance's scripts dir."""
    try:
        return sorted(e.name for e in os.scandir(scripts_dir)
                      if e.is_dir() and e.name != '__pycache__' and not e.name.startswith('.'))
    except OSError:
        return []


def check_host_updates(host):
    """Full check payload for a host + all its instances."""
    common_pool_changes, common_pool_error = check_common_pool(host)
    instances_payload = []
    for instance in host.instances:
        instances_payload.append({
            "id": instance.id,
            "name": instance.name,
            "port": instance.port,
            "status": instance.status.value,
            "selected_plugin_changes": check_instance_selected_plugins(host, instance),
        })
    return {
        "host_id": host.id,
        "common_pool_changes": common_pool_changes or [],
        "common_pool_error": common_pool_error,
        "instances": instances_payload,
    }
