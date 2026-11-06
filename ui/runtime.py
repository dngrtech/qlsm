"""Single source of truth for the per-host minqlx runtime split.

A host picks its runtime at creation (Host.runtime). It is changed only by the
"Upgrade to minqlxtended" action (ui/runtime_upgrade.py), so every path this
module returns is stable except across that one audited transition. Every
hardcoded 'minqlx-plugins' / 'minqlx.log' / '/home/ql/minqlx-shared' string in
the backend, the playbooks and the Terraform roots resolves through here, so
the two runtimes cannot drift apart.

minqlxtended (github.com/tjone270/minqlxtended) is a hard fork of minqlx with
no backwards compatibility: plugins written for one do not run on the other.
"""
import os
import re

MINQLX = 'minqlx'
MINQLXTENDED = 'minqlxtended'

VALID_RUNTIMES = (MINQLX, MINQLXTENDED)

# Nothing ever "flips" this: the Add Host form pre-selects no runtime at all,
# because the choice is changed only by the Upgrade to minqlxtended action and
# QLSM will not make it on an operator's behalf. This constant is the fallback for the two cases where no human is
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
        'os_version': '12',
        # No Python floor: existing hosts run whatever they already run, and
        # inventing a gate here would break them on the next setup re-run.
        'min_python': None,
        'excluded_system_hooks': frozenset(),
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
        'git_version': '411591a2f6f8ad26949ee4c83758149d5b95f7ab',
        'os_name': 'Ubuntu 24.04 LTS x64',
        'os_family': 'ubuntu',
        'os_type': 'ubuntu',
        'os_version': '24.04',
        # The build links -lpython3.12 explicitly.
        'min_python': (3, 12),
        # minqlxtended hooks Sys_IsLANAddress itself, unconditionally
        # (src/server/hooks.c:142). force_rate.so overwrites the same prologue
        # at 0x004518d0, and a failed STATIC_SEARCH exits the server
        # (dllmain.c:294-297). Whether that fires depends on glibc constructor
        # order, which QLSM does not control -- so never load it here. The
        # runtime provides the behaviour natively.
        'excluded_system_hooks': frozenset({'force_rate.so'}),
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


ISOLATED_INSTANCE_DEPS_ROOT = '/home/ql/runtime-deps/minqlxtended/instances'
# Controller-side core requirements for venvs built outside an upgrade
# operation (new/redeployed instances on an isolated host). Anchored at the
# repository root (as preset_compat.ASSETS_DIR is), never the worker's cwd.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_CORE_REQUIREMENTS = os.path.join(
    _REPO_ROOT, 'ql-assets', 'data', _RUNTIME_PATHS[MINQLXTENDED]['asset_plugins_dir'], 'requirements.txt')


def isolated_instance_deps_path(instance_id):
    """The venv an instance gets on a host with isolated runtime deps."""
    return f'{ISOLATED_INSTANCE_DEPS_ROOT}/{int(instance_id)}'


def instance_runtime_extravars(instance):
    """runtime_extravars() for an instance's host, plus the instance's isolated
    dependency venv when it has one (QLInstance.python_deps_path, set by the
    runtime upgrade). With no venv the result is exactly runtime_extravars(),
    so the playbooks render and install exactly as before.

    On a minqlxtended host with Host.runtime_deps_isolated (an upgraded host),
    an instance without a venv is assigned one under
    ISOLATED_INSTANCE_DEPS_ROOT (persisted with the caller's next commit), and
    python_deps_ensure asks tasks/install_minqlx_deps.yml to build or refresh
    it as ql before any pip -- system pip is never used there. The instance's
    own requirements are the copy already synced to the host.

    A venv under ISOLATED_INSTANCE_DEPS_ROOT is keyed by the instance id,
    which SQLite can reuse after a delete, so it also gets python_deps_owner
    (id + creation time): install_minqlx_deps.yml rebuilds a venv whose
    marker names another instance. Operation venvs embed the operation id."""
    host = instance.host
    extravars = runtime_extravars(host)
    isolated = (bool(getattr(host, 'runtime_deps_isolated', False))
                and host_runtime(host) == MINQLXTENDED)
    if isolated and not getattr(instance, 'python_deps_path', None):
        instance.python_deps_path = isolated_instance_deps_path(instance.id)
    deps_path = getattr(instance, 'python_deps_path', None)
    if deps_path:
        extravars['python_deps_path'] = deps_path
    if isolated:
        extravars['python_deps_ensure'] = True
        extravars['python_deps_core_requirements_src'] = _CORE_REQUIREMENTS
        if deps_path == isolated_instance_deps_path(instance.id):
            created = getattr(instance, 'created_at', None)
            extravars['python_deps_owner'] = f'{int(instance.id)}:{created.isoformat() if created else "unknown"}'
    return extravars
