"""The cvars a preset apply must not overwrite on a server.

A preset carries server.cfg-style config, and applying it onto a running
server would also overwrite values that belong to that server alone: its port
and hostname from the launch args, an id an addon reserved for it, a plugin's
own per-server setting. `collect_keep_cvars` gathers those names from three
sources so the apply can keep the server's current value for each.
"""
import logging
import os
import re

from ui.plugin_manifest import read_plugin_manifest
from ui.runtime import host_runtime
from ui.task_logic.ansible_instance_mgmt import _build_qlds_args_string

log = logging.getLogger(__name__)

# qlx_plugins is the preset's to change (the plugin list is what an apply is
# for), so it is never kept even though the launch args always carry it.
LAUNCH_ARG_EXCLUDED = frozenset({'qlx_plugins'})

SOURCE_LAUNCH_ARGS = 'launch args'

_SET_RE = re.compile(r'\+set\s+(\S+)')


def _launch_arg_cvars(instance):
    try:
        args = _build_qlds_args_string(instance)
    except Exception as e:
        log.warning('keep_cvars: launch args of instance %s skipped: %s',
                    getattr(instance, 'id', None), e)
        return []
    return _SET_RE.findall(args or '')


def _addon_cvars(instance):
    try:
        from ui.addons import dispatch_by_addon

        pairs = dispatch_by_addon('preset.keep_cvars', instance.id, instance)
    except Exception as e:  # registry unavailable, e.g. outside an app context
        log.warning('keep_cvars: addon hook skipped for instance %s: %s',
                    getattr(instance, 'id', None), e)
        return []
    found = []
    for addon_id, names in pairs:
        if not isinstance(names, (list, tuple)):
            continue
        found.extend((f'addon:{addon_id}', n) for n in names if isinstance(n, str) and n)
    return found


def _manifest_cvars(script_path, runtime):
    """Names of the `per_server` cvars in the manifest of one plugin file."""
    manifest = read_plugin_manifest(script_path, runtime)
    entries = (manifest or {}).get('cvars')
    if not isinstance(entries, list):
        return []
    return [
        e['cvar'] for e in entries
        if isinstance(e, dict) and e.get('per_server') is True
        and isinstance(e.get('cvar'), str) and e['cvar']
    ]


def _instance_plugin_files(instance):
    """Root .py files in the instance's scripts dir that are in its qlx_plugins."""
    scripts_dir = os.path.abspath(
        os.path.join('configs', instance.host.name, str(instance.id), 'scripts'))
    enabled = {p.strip() for p in (instance.qlx_plugins or '').split(',') if p.strip()}
    if not enabled or not os.path.isdir(scripts_dir):
        return []
    return [
        os.path.join(scripts_dir, name) for name in sorted(os.listdir(scripts_dir))
        if name.endswith('.py') and name[:-3] in enabled
        and os.path.isfile(os.path.join(scripts_dir, name))
    ]


def _preset_plugin_files(preset_payload):
    checked = preset_payload.get('checked_plugins')
    preset_path = preset_payload.get('path')
    if not checked or not preset_path:
        return []
    from ui.routes.preset_api_routes import _resolve_preset_scripts_root

    try:
        root = _resolve_preset_scripts_root(preset_path)
    except ValueError as e:
        log.warning('keep_cvars: preset scripts root unusable: %s', e)
        return []
    files = []
    for rel in checked:
        if not isinstance(rel, str):
            continue
        full = os.path.realpath(os.path.join(root, rel))
        if os.path.commonpath([os.path.realpath(root), full]) != os.path.realpath(root):
            continue  # a path escaping the scripts root is not ours to read
        if full.endswith('.py') and os.path.isfile(full):
            files.append(full)
    return files


def _root_plugin_names(instance, preset_payload):
    """Enabled (qlx_plugins) and checked root plugin names, first-seen order."""
    names = [p.strip() for p in (instance.qlx_plugins or '').split(',') if p.strip()]
    for rel in preset_payload.get('checked_plugins') or []:
        if not isinstance(rel, str) or '/' in rel or '\\' in rel or not rel.endswith('.py'):
            continue
        names.append(rel[:-3])
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def collect_keep_cvars(instance, preset_payload):
    """Cvars to keep on `instance` when `preset_payload` is applied.

    Returns `[{"cvar": str, "sources": [str]}]` sorted by lower-cased cvar.
    Names compare case-insensitively; the first-seen spelling is kept and the
    sources of duplicates are merged in first-seen order. Sources are
    "launch args", "addon:<addon_id>" and "plugin:<filename>".
    """
    merged = {}  # lowered name -> {"cvar": first spelling, "sources": [...]}

    def add(name, source):
        key = name.lower()
        if key in LAUNCH_ARG_EXCLUDED:
            return
        entry = merged.setdefault(key, {'cvar': name, 'sources': []})
        if source not in entry['sources']:
            entry['sources'].append(source)

    for name in _launch_arg_cvars(instance):
        add(name, SOURCE_LAUNCH_ARGS)
    for source, name in _addon_cvars(instance):
        add(name, source)

    runtime = host_runtime(getattr(instance, 'host', None))
    preset_payload = preset_payload or {}
    plugin_files = _instance_plugin_files(instance) + _preset_plugin_files(preset_payload)
    # An enabled or checked plugin with no local copy runs from the runtime's
    # shared pool; read_plugin_manifest resolves its manifest there by name.
    local = {os.path.basename(path) for path in plugin_files}
    plugin_files += [
        f'{name}.py' for name in _root_plugin_names(instance, preset_payload)
        if f'{name}.py' not in local
    ]
    for path in plugin_files:
        try:
            names = _manifest_cvars(path, runtime)
        except Exception as e:
            log.warning('keep_cvars: manifest of %s skipped: %s', path, e)
            continue
        for name in names:
            add(name, f'plugin:{os.path.basename(path)}')

    return sorted(merged.values(), key=lambda e: e['cvar'].lower())
