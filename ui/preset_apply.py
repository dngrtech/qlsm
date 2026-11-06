"""The new state of an instance once a preset is loaded into it.

A server-side port of what the config editor's "Load preset" does in the
browser (`applyPresetData`, `handleLoadPreset` and
`handleConfirmPresetCompatibility` in EditInstanceConfigModal.jsx, plus
`mergeReplacements` / `combineAcceptedPaths` in utils/presetCompatibility.js),
so one implementation serves the editor and the bulk apply. The result's
`payload` is a body `save_instance_config` accepts as is.

On top of the browser's rules, the cvars in `keep_cvars` keep the server's own
server.cfg lines (see `merge_keep_cvars`).
"""
import hashlib
import json
import os
import re
import shutil
import tempfile

from ui.lan_rate_policy import would_enable_unsupported_lan_rate
from ui.pending_changes import diff_snapshots, snapshot_dir
from ui.preset_keep_cvars import LAUNCH_ARG_EXCLUDED, collect_keep_cvars
from ui.routes.preset_api_routes import read_preset_payload
from ui.runtime import host_runtime
from ui.task_logic.permission_read import read_live_admins

# Keys of MANAGED_CVARS in frontend-react/src/codemirror-lang-qlcfg.js, lower
# case: cvars the app sets itself, so a value in server.cfg has no effect.
# tests/test_preset_apply.py keeps the two lists equal.
MANAGED_CVARS = frozenset({
    'sv_servertype', 'sv_lanforcerate', 'net_ip', 'net_strict',
    'qlx_redisaddress', 'qlx_redisunixsocket', 'qlx_redispassword', 'qlx_redisdatabase',
    'fs_homepath', 'qlx_pluginspath',
    'zmq_rcon_enable', 'zmq_rcon_port', 'zmq_rcon_password',
    'zmq_stats_port', 'zmq_stats_password',
    'net_port', 'qlx_plugins',
})

# The editor's file set (CONFIG_FILES_ORDER) and the legacy preset keys each
# one falls back to (CONFIG_KEY_MAP).
CONFIG_FILES_ORDER = ('server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt')
CONFIG_KEY_MAP = {
    'server.cfg': 'server_cfg',
    'mappool.txt': 'mappool_txt',
    'access.txt': 'access_txt',
    'workshop.txt': 'workshop_txt',
}

# Root-level .py files that are libraries, not plugins (pluginSelection.js).
ABSTRACT_PLUGIN_MODULES = frozenset({'iouonegirl.py'})

# JS `.` stops at these; Python's would also cross \r,   and  .
_NOT_EOL = r'[^\n\r  ]'
_MANAGED_VALUE_RE = re.compile(
    rf'^(\s*seta?\s+)(\S+)(\s+")({_NOT_EOL}*?)("{_NOT_EOL}*)', re.I | re.M)
_SET_LINE_RE = re.compile(r'^\s*seta?\s+(\S+)', re.I)
_HOSTNAME_RE = re.compile(r'set sv_hostname "([^"]*)"')


class PresetApplyError(Exception):
    """A preset that cannot be turned into a target; `status` is the HTTP code."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def strip_managed_cvars(cfg):
    """Blank the value of every managed cvar line (`set net_port "1"` -> `set net_port ""`)."""
    if not cfg:
        return cfg

    def blank(match):
        prefix, cvar, mid, _value, suffix = match.groups()
        if cvar.lower() in MANAGED_CVARS:
            return f'{prefix}{cvar}{mid}{suffix}'
        return match.group(0)
    return _MANAGED_VALUE_RE.sub(blank, cfg)


def _line_cvar(line):
    match = _SET_LINE_RE.match(line)
    return match.group(1).lower() if match else None


def merge_keep_cvars(preset_cfg, instance_cfg, keep):
    """server.cfg text of the preset with the instance's own lines for `keep`.

    Both sides go through strip_managed_cvars first. Every preset line setting
    a kept cvar is removed; the instance's lines for it go where the first one
    was, or at the end when the preset never set it; an instance without a line
    for it gets none. Returns (text, cvars whose lines changed), the cvars
    spelled as given in `keep`.
    """
    base = strip_managed_cvars(preset_cfg or '') or ''
    current = strip_managed_cvars(instance_cfg or '') or ''
    wanted = {}
    for name in keep or []:
        wanted.setdefault(name.lower(), name)
    if not wanted:
        return base, []

    instance_lines = {}
    for line in current.split('\n'):
        cvar = _line_cvar(line)
        if cvar in wanted:
            instance_lines.setdefault(cvar, []).append(line)

    out = []
    placed = set()
    preset_lines = {}
    for line in base.split('\n'):
        cvar = _line_cvar(line)
        if cvar not in wanted:
            out.append(line)
            continue
        preset_lines.setdefault(cvar, []).append(line)
        if cvar not in placed:
            placed.add(cvar)
            out.extend(instance_lines.get(cvar, []))
    for cvar in wanted:
        if cvar not in placed and cvar in instance_lines:
            out.extend(instance_lines[cvar])

    changed = [
        name for cvar, name in wanted.items()
        if preset_lines.get(cvar, []) != instance_lines.get(cvar, [])
    ]
    return '\n'.join(out), changed


def _with_server_hostname(server_cfg, hostname):
    """withServerHostname in EditInstanceConfigModal.jsx: replace the first
    `set sv_hostname "..."`, or append one."""
    server_cfg = server_cfg or ''
    if _HOSTNAME_RE.search(server_cfg):
        return _HOSTNAME_RE.sub(lambda _m: f'set sv_hostname "{hostname}"', server_cfg, count=1)
    return f'{server_cfg}\nset sv_hostname "{hostname}"'


def _depends_on(manifest):
    names = (manifest or {}).get('depends_on')
    if not isinstance(names, list):
        return []
    return [n.strip() for n in names if isinstance(n, str) and n.strip()]


def _library_names(scripts_dir, runtime):
    """collectDependencyFilenames over the tree the editor shows: the draft's
    root .py files plus the runtime's shared pool plugins it does not hold."""
    from ui.plugin_manifest import read_plugin_manifest
    from ui.plugin_pool import list_shared_plugins

    root_files = {}
    try:
        entries = sorted(os.listdir(scripts_dir))
    except OSError:
        entries = []
    for name in entries:
        full = os.path.join(scripts_dir, name)
        if name.startswith('.') or not os.path.isfile(full):
            continue
        root_files[name] = full
    for name, full in list_shared_plugins(runtime).items():
        root_files.setdefault(name, full)

    libraries = set()
    for name, full in root_files.items():
        if not name.endswith('.py'):
            continue
        for dep in _depends_on(read_plugin_manifest(full, runtime)):
            if dep.endswith('.py') and dep in root_files:
                libraries.add(dep)
    return libraries


def _enableable(path, libraries):
    return (
        path.endswith('.py') and '/' not in path
        and path not in ABSTRACT_PLUGIN_MODULES and path not in libraries
        and path != '__init__.py'
    )


def qlx_plugin_names(checked_paths, scripts_dir, runtime):
    """qlx_plugins names for checked plugin paths (partitionCheckedPaths +
    toQlxPluginNames): root .py files only, minus __init__.py, abstract
    modules and any file a plugin declares in depends_on."""
    libraries = _library_names(scripts_dir, runtime)
    names = []
    for path in checked_paths or []:
        if isinstance(path, str) and _enableable(path, libraries):
            name = path[:-3]
            if name not in names:
                names.append(name)
    return names


def diff_admin_lists(before, after):
    """diffAdminLists in utils/adminChanges.js: changed or added admins with
    their new level, removed ones with level 0."""
    previous = {e['steam_id64']: int(e['level']) for e in before or []}
    following = {e['steam_id64']: int(e['level']) for e in after or []}
    changes = [
        {'steam_id64': sid, 'level': level}
        for sid, level in following.items() if previous.get(sid) != level
    ]
    changes.extend(
        {'steam_id64': sid, 'level': 0} for sid in previous if sid not in following)
    return changes


def _accepted_paths(compatibility, ticked):
    """combineAcceptedPaths: the auto-accepted replacements, then the ticked ones."""
    accepted = []
    for path in list((compatibility or {}).get('auto_accepted') or []) + list(ticked or []):
        if path not in accepted:
            accepted.append(path)
    return accepted


def _checked_with_replacements(preset_payload, accepted):
    """checked_plugins after mergeReplacements: an accepted replacement re-ticks
    a stripped plugin only when the preset had it ticked."""
    checked = preset_payload.get('checked_plugins')
    compatibility = preset_payload.get('compatibility')
    if not isinstance(checked, list) or not compatibility:
        return checked
    offered = compatibility.get('replacements') or {}
    taken = [path for path in accepted if path in offered]
    if not taken:
        return checked
    originally_checked = {
        entry.get('path') for entry in compatibility.get('stripped') or []
        if entry.get('originally_checked')
    }
    result = list(dict.fromkeys(checked))
    for path in taken:
        if path in originally_checked and path not in result:
            result.append(path)
    return result


def _needs_decision(compatibility, accepted, decided):
    """`decided`: the operator answered (even with no ticks); unticked replacements are declined."""
    if decided:
        return False
    covered = set(accepted)
    return any(
        entry.get('replacement') and entry['replacement'] not in covered
        for entry in (compatibility or {}).get('stripped') or []
    )


def _effective_keep(instance, preset_payload, keep_cvars):
    if keep_cvars is None:
        keep_cvars = [entry['cvar'] for entry in collect_keep_cvars(instance, preset_payload)]
    effective, seen = [], set()
    for name in keep_cvars:
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        if name.lower() in LAUNCH_ARG_EXCLUDED or name.lower() in seen:
            continue
        seen.add(name.lower())
        effective.append(name)
    return effective


def _instance_server_cfg(instance):
    """What the editor loads as the instance's server.cfg: the file on disk, or
    the default preset's when the instance has none yet."""
    path = os.path.join('configs', instance.host.name, str(instance.id), 'server.cfg')
    if os.path.isfile(path):
        with open(path, 'r') as f:
            return f.read()
    from ui.routes.instance_routes import _read_default_config
    return _read_default_config('server.cfg') or ''


def _configs(preset_payload, instance, keep):
    configs = dict(preset_payload.get('configs') or {})
    for name in CONFIG_FILES_ORDER:
        raw = configs.get(name)
        if raw is None:
            raw = preset_payload.get(CONFIG_KEY_MAP[name])
        configs[name] = raw if raw is not None else ''
    server_cfg, kept = merge_keep_cvars(configs['server.cfg'], _instance_server_cfg(instance), keep)
    if instance.hostname:
        server_cfg = _with_server_hostname(server_cfg, instance.hostname)
    configs['server.cfg'] = server_cfg
    return configs, kept


def _factories(preset_payload):
    factories = preset_payload.get('factories') or {}
    checked = preset_payload.get('checked_factories')
    if checked is None:
        return dict(factories)
    return {name: factories[name] for name in checked if name in factories}


def _draft_error(error):
    response, status = error
    body = response.get_json(silent=True) or {}
    message = (body.get('error') or {}).get('message') or 'Failed to create draft workspace'
    return PresetApplyError(message, status)


def build_preset_target(instance, preset, accepted_replacements, keep_cvars):
    """The state `instance` gets when `preset` is loaded into it.

    `accepted_replacements`: replacement paths the operator accepted in the
    compatibility dialog (the auto-accepted ones are added here); None means
    no decision yet, any list (even empty) is the decision and the unticked
    replacements are declined. `keep_cvars`:
    cvars whose server.cfg lines stay the instance's own; None means the
    collected list. Creates a scripts draft (the payload's `draft_id`) unless the
    preset is legacy (no checked_plugins list). Raises
    PresetApplyError. Needs an app context.
    """
    from ui.routes.draft_routes import _get_draft_scripts_path, create_draft_workspace

    runtime = host_runtime(instance.host)
    try:
        preset_payload = read_preset_payload(preset, runtime)
    except FileNotFoundError:
        raise PresetApplyError('Preset configuration files not found.', 500)

    compatibility = preset_payload.get('compatibility')
    accepted = _accepted_paths(compatibility, accepted_replacements)
    keep = _effective_keep(instance, preset_payload, keep_cvars)
    configs, kept = _configs(preset_payload, instance, keep)

    payload = {
        'hostname': instance.hostname,
        'configs': configs,
        'config_folders': list(preset_payload.get('config_folders') or []),
        'factories': _factories(preset_payload),
    }
    if preset_payload.get('enabled_hooks') is not None:
        payload['enabled_hooks'] = preset_payload['enabled_hooks']
    preset_admins = preset_payload.get('admins')
    if isinstance(preset_admins, list):
        # Unreadable server list: compare against nothing, so the apply only
        # adds and re-levels and never revokes an admin it could not see.
        current, _names, _error = read_live_admins(instance)
        changes = diff_admin_lists(current or [], preset_admins)
        if changes:
            payload['admin_changes'] = changes
    if preset_payload.get('lan_rate_enabled') is not None:
        wanted = bool(preset_payload['lan_rate_enabled'])
        if would_enable_unsupported_lan_rate(
                instance.host, current_enabled=instance.lan_rate_enabled,
                requested_enabled=wanted):
            wanted = False
        payload['lan_rate_enabled'] = wanted

    # None (no checked_plugins.json, or not a list) is no selection at all:
    # the instance keeps its qlx_plugins, as apply_compatibility reads it, and
    # its scripts/ too, so a legacy preset gets no draft (a draft would
    # replace scripts/ on save).
    checked = _checked_with_replacements(preset_payload, accepted)
    if isinstance(checked, list):
        draft_id, error = create_draft_workspace({
            'source': 'preset',
            'preset': preset.name,
            'target_runtime': runtime,
            'accepted_replacements': accepted,
        })
        if error:
            raise _draft_error(error)
        payload['draft_id'] = draft_id
        payload['checked_plugins'] = qlx_plugin_names(
            checked, _get_draft_scripts_path(draft_id), runtime)

    return {
        'payload': payload,
        'compatibility': compatibility,
        'kept_cvars': kept,
        'keep_cvars': keep,
        'needs_decision': _needs_decision(compatibility, accepted, accepted_replacements is not None),
    }


def _instance_config_dir(instance):
    return os.path.join('configs', instance.host.name, str(instance.id))


def _csv(value):
    return [part.strip() for part in (value or '').split(',') if part.strip()]


def _target_files(instance, payload, work_dir):
    """(changed files, hooks left enabled) once `payload` is saved.

    The save is replayed on a copy of the instance's config dir with
    save_instance_config's own helpers, so files it leaves alone (other
    folders) never show up and the access.txt rewrite is part of the "after"
    side. user-hooks/ is part of the copy: a preset-sourced draft adds the
    hook files the instance lacks, and enabled_hooks is filtered against what
    is on disk after that, exactly as the save does.
    """
    from ui.routes.draft_routes import (
        _get_draft_scripts_path, _get_draft_source, _get_draft_user_hooks_path,
        _merge_draft_user_hooks_into_instance,
    )
    from ui.routes.instance_routes import (
        _filtered_enabled_hooks, _sync_configs_to_disk, _sync_factories_to_disk,
    )

    current_dir = _instance_config_dir(instance)
    copy_dir = os.path.join(work_dir, 'config')
    if os.path.isdir(current_dir):
        shutil.copytree(current_dir, copy_dir)
    else:
        os.makedirs(copy_dir)
    before = snapshot_dir(copy_dir)

    _sync_configs_to_disk(copy_dir, payload['configs'], payload.get('config_folders'))
    if 'factories' in payload:
        _sync_factories_to_disk(os.path.join(copy_dir, 'factories'), payload['factories'])
    hooks_dir = os.path.join(copy_dir, 'user-hooks')
    draft_id = payload.get('draft_id')
    if draft_id:
        draft_scripts = _get_draft_scripts_path(draft_id)
        if os.path.exists(draft_scripts):
            scripts_dir = os.path.join(copy_dir, 'scripts')
            shutil.rmtree(scripts_dir, ignore_errors=True)
            shutil.copytree(draft_scripts, scripts_dir)
        if _get_draft_source(draft_id) == 'preset':
            _merge_draft_user_hooks_into_instance(_get_draft_user_hooks_path(draft_id), hooks_dir)
    enabled = payload.get('enabled_hooks')
    after_hooks = None if enabled is None else _filtered_enabled_hooks(enabled, hooks_dir)
    return diff_snapshots(before, snapshot_dir(copy_dir)), after_hooks


def _admin_part(changes):
    if changes is None:
        return None
    return {
        'add': [c for c in changes if int(c['level']) > 0],
        'remove': [c['steam_id64'] for c in changes if int(c['level']) == 0],
    }


def _before_after(before, after):
    return None if after is None else {'before': before, 'after': list(after)}


def diff_preset_target(instance, target):
    """What loading `target` (from build_preset_target) would change on `instance`.

    Keys: `files` (diff_snapshots entries, paths relative to the instance's
    config dir), `plugins` / `hooks` (`{before, after}` lists), `admins`
    (`{add: [{steam_id64, level}], remove: [steam_id64]}`, from the payload's
    admin_changes), `lan_rate` (`{before, after}` bools), `unchanged`. A part
    the payload leaves untouched is None. Needs an app context.
    """
    from ui.routes.instance_hooks_routes import _enabled_list

    payload = target['payload']
    work_dir = tempfile.mkdtemp()
    try:
        files, enabled_hooks = _target_files(instance, payload, work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    plugins = _before_after(_csv(instance.qlx_plugins), payload.get('checked_plugins'))
    hooks = _before_after(_enabled_list(instance), enabled_hooks)
    admins = _admin_part(payload.get('admin_changes'))
    lan_rate = None
    if payload.get('lan_rate_enabled') is not None:
        lan_rate = {'before': bool(instance.lan_rate_enabled), 'after': bool(payload['lan_rate_enabled'])}

    parts = [p for p in (plugins, hooks, lan_rate) if p is not None]
    unchanged = (
        not files
        and all(p['before'] == p['after'] for p in parts)
        and not (admins and (admins['add'] or admins['remove']))
    )
    return {
        'files': files,
        'plugins': plugins,
        'hooks': hooks,
        'admins': admins,
        'lan_rate': lan_rate,
        'unchanged': unchanged,
    }


def target_hash(target):
    """sha256 of the target: its payload without the (random) draft_id, and the
    content of the draft's scripts, so two previews of the same state agree."""
    from ui.routes.draft_routes import _get_draft_scripts_path, _get_draft_user_hooks_path

    payload = target['payload']
    body = {key: value for key, value in payload.items() if key != 'draft_id'}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))
    scripts = {}
    if payload.get('draft_id'):
        for rel, entry in snapshot_dir(_get_draft_scripts_path(payload['draft_id'])).items():
            scripts[rel] = entry['sha256']
    digest.update(json.dumps(scripts, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    # Hook files the save would bring in from a preset draft.
    hooks = {}
    if payload.get('draft_id'):
        for rel, entry in snapshot_dir(_get_draft_user_hooks_path(payload['draft_id'])).items():
            hooks[rel] = entry['sha256']
    digest.update(json.dumps(hooks, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    return digest.hexdigest()
