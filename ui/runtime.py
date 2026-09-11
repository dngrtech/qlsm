"""Single source of truth for the per-host minqlx runtime split.

A host picks its runtime at creation (Host.runtime) and never changes it, so
every path this module returns is stable for the life of the host. Every
hardcoded 'minqlx-plugins' / 'minqlx.log' / '/home/ql/minqlx-shared' string in
the backend, the playbooks and the Terraform roots resolves through here, so
the two runtimes cannot drift apart.

minqlxtended (github.com/tjone270/minqlxtended) is a hard fork of minqlx with
no backwards compatibility: plugins written for one do not run on the other.
"""
import re

MINQLX = 'minqlx'
MINQLXTENDED = 'minqlxtended'
MINQLXTENDED_PATCHED = 'minqlxtended-patched'

VALID_RUNTIMES = (MINQLX, MINQLXTENDED, MINQLXTENDED_PATCHED)

# Nothing ever "flips" this: the Add Host form pre-selects no runtime at all,
# because the choice is irreversible and QLSM will not make it on an operator's
# behalf. This constant is the fallback for the two cases where no human is
# choosing -- a host row that predates the runtime column, and an API payload
# that omits the field -- and it points at minqlx because that is the
# conservative answer, not because it is anyone's default.
DEFAULT_RUNTIME = MINQLX

_RUNTIME_PATHS = {
    MINQLX: {
        'runtime': MINQLX,
        # On-host instance plugin dir, and the ql-assets/data/ baseline dir.
        'plugins_dirname': 'minqlx-plugins',
        'asset_plugins_dir': 'minqlx-plugins',
        'shared_dir': '/home/ql/minqlx-shared',
        'engine_so': 'minqlx.x64.so',
        'launch_script': 'run_server_x64_minqlx.sh',
        'log_filename': 'minqlx.log',
        'git_repo': 'https://github.com/MinoMino/minqlx.git',
        'git_version': 'fbdd915185337791d8e209dc4b686a1ee60d3721',
        'os_name': 'Debian 12 x64 (bookworm)',
        'os_family': 'debian',
        'os_type': 'debian',
        # No Python floor: existing hosts run whatever they already run, and
        # inventing a gate here would break them on the next setup re-run.
        'min_python': None,
        'excluded_system_hooks': frozenset(),
        'apply_local_patches': True,
        'apply_qlhub_patches': False,
    },
    MINQLXTENDED: {
        'runtime': MINQLXTENDED,
        'plugins_dirname': 'minqlxtended-plugins',
        'asset_plugins_dir': 'minqlxtended-plugins',
        'shared_dir': '/home/ql/minqlxtended-shared',
        'engine_so': 'minqlxtended.x64.so',
        'launch_script': 'run_server_x64_minqlxtended.sh',
        'log_filename': 'minqlxtended.log',
        'git_repo': 'https://github.com/tjone270/minqlxtended.git',
        'git_version': '97fbe6715a4802545aa7eca741d11e2486a306a4',
        'os_name': 'Ubuntu 24.04 LTS x64',
        'os_family': 'ubuntu',
        'os_type': 'ubuntu',
        # The build links -lpython3.12 explicitly.
        'min_python': (3, 12),
        # minqlxtended hooks Sys_IsLANAddress itself, unconditionally
        # (src/server/hooks.c:142). force_rate.so overwrites the same prologue
        # at 0x004518d0, and a failed STATIC_SEARCH exits the server
        # (dllmain.c:294-297). Whether that fires depends on glibc constructor
        # order, which QLSM does not control -- so never load it here. The
        # runtime provides the behaviour natively.
        'excluded_system_hooks': frozenset({'force_rate.so'}),
        'apply_local_patches': False,
        'apply_qlhub_patches': False,
    },
    # QLSM's own build: vanilla minqlxtended plus the qlhub patch chain
    # vendored under ql-assets/patches/minqlxtended/ (native item events/
    # respawn, demo capture, a bounded redis pool, set_position -- see
    # build_engine_hook.yml). Shares minqlx's plugin pool and shared dir
    # rather than minqlxtended's, since the patch chain is applied on top of
    # a vanilla minqlxtended checkout and does not touch plugin loading.
    #
    # git_version is deliberately left floating on HEAD, matching
    # build_engine_hook.yml's default: there has never been a pin for this
    # chain. Upstream minqlxtended restructured its source tree in a "v1.0.0"
    # release, and the qlhub patch scripts were verified only against the
    # pre-restructure layout. Floating HEAD today risks the patch chain
    # failing loudly (acceptable) or applying wrongly (not); pinning is a
    # known follow-up, not an oversight.
    MINQLXTENDED_PATCHED: {
        'runtime': MINQLXTENDED_PATCHED,
        'plugins_dirname': 'minqlx-plugins',
        'asset_plugins_dir': 'minqlx-plugins',
        'shared_dir': '/home/ql/minqlx-shared',
        'engine_so': 'minqlxtended.x64.so',
        'launch_script': 'run_server_x64_minqlxtended.sh',
        'log_filename': 'minqlxtended.log',
        'git_repo': 'https://github.com/tjone270/minqlxtended.git',
        'git_version': 'HEAD',
        'os_name': 'Ubuntu 24.04 LTS x64',
        'os_family': 'ubuntu',
        'os_type': 'ubuntu',
        'min_python': (3, 12),
        'excluded_system_hooks': frozenset({'force_rate.so'}),
        'apply_local_patches': False,
        'apply_qlhub_patches': True,
    },
}


def normalize_runtime(value):
    """Coerce any stored value to a valid runtime.

    None, an unknown string, or a non-string all resolve to minqlx: a NULL
    column means the row predates this feature, and nothing but minqlx has
    ever existed.
    """
    if not isinstance(value, str):
        return DEFAULT_RUNTIME
    normalized = value.strip().lower()
    return normalized if normalized in VALID_RUNTIMES else DEFAULT_RUNTIME


def is_valid_runtime(value):
    """Whether a caller-supplied value names a runtime. Used by API validation,
    where an unknown value must be rejected rather than silently defaulted."""
    return isinstance(value, str) and value.strip().lower() in VALID_RUNTIMES


def runtime_paths(runtime):
    """Return a copy of the path table for `runtime`."""
    return dict(_RUNTIME_PATHS[normalize_runtime(runtime)])


def host_runtime(host):
    """The runtime of a Host row, tolerant of None and of detached objects."""
    return normalize_runtime(getattr(host, 'runtime', None))


def log_filename_pattern(runtime):
    """Regex matching the runtime's live log file and its rotated siblings."""
    return re.escape(runtime_paths(runtime)['log_filename']) + r'(\.\d+)?'


def runtime_extravars(host):
    """The extra-vars every instance-level playbook needs to target the right
    runtime. Call sites merge this into their own extravars dict so no playbook
    can be updated without its caller."""
    paths = runtime_paths(host_runtime(host))
    return {
        'runtime': paths['runtime'],
        'runtime_plugins_dirname': paths['plugins_dirname'],
        'runtime_shared_dir': paths['shared_dir'],
        'launch_script': paths['launch_script'],
    }
