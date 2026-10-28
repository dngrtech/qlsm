"""build_preset_target: the server-side port of the editor's "Load preset"."""
import json
import os
import re
from unittest.mock import patch

import pytest

from ui import db
from ui.models import ConfigPreset, Host, QLInstance
from ui import preset_apply
from ui.preset_apply import (
    MANAGED_CVARS,
    build_preset_target,
    diff_preset_target,
    merge_keep_cvars,
    qlx_plugin_names,
    strip_managed_cvars,
    target_hash,
)

FRONTEND_QLCFG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'frontend-react', 'src', 'codemirror-lang-qlcfg.js',
)


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    """App context with cwd at a temp dir, so configs/ and the plugin pools are empty."""
    monkeypatch.chdir(tmp_path)
    with app.app_context():
        yield tmp_path


def _host(name='h1', **kwargs):
    kwargs.setdefault('provider', 'standalone')
    kwargs.setdefault('runtime', 'minqlx')
    kwargs.setdefault('os_type', 'debian')
    host = Host(name=name, **kwargs)
    db.session.add(host)
    db.session.commit()
    return host


def _instance(host, server_cfg=None, **kwargs):
    kwargs.setdefault('name', 'inst1')
    kwargs.setdefault('port', 27960)
    kwargs.setdefault('hostname', 'My Server')
    instance = QLInstance(host_id=host.id, **kwargs)
    db.session.add(instance)
    db.session.commit()
    if server_cfg is not None:
        config_dir = os.path.join('configs', host.name, str(instance.id))
        os.makedirs(config_dir, exist_ok=True)
        with open(os.path.join(config_dir, 'server.cfg'), 'w', encoding='utf-8') as f:
            f.write(server_cfg)
    return instance


def _preset(root, name='p1', configs=None, scripts=None, factories=None, runtime='minqlx', **records):
    """A preset on disk plus its row. `records` are the optional json files
    (checked_plugins, checked_factories, enabled_hooks, lan_rate_enabled, admins)."""
    path = root / 'configs' / 'presets' / name
    path.mkdir(parents=True)
    for rel, text in (configs or {'server.cfg': ''}).items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text, encoding='utf-8')
    (path / 'scripts').mkdir()
    for rel, text in (scripts or {}).items():
        (path / 'scripts' / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / 'scripts' / rel).write_text(text, encoding='utf-8')
    if factories is not None:
        (path / 'factories').mkdir()
        for rel, text in factories.items():
            (path / 'factories' / rel).write_text(text, encoding='utf-8')
    for key, value in records.items():
        (path / f'{key}.json').write_text(json.dumps(value), encoding='utf-8')
    preset = ConfigPreset(name=name, description=name, path=str(path), runtime=runtime)
    db.session.add(preset)
    db.session.commit()
    return preset


# --- server.cfg text rules ---------------------------------------------------

def test_managed_cvars_match_the_frontend_list():
    with open(FRONTEND_QLCFG, encoding='utf-8') as f:
        source = f.read()
    block = re.search(r'const MANAGED_CVARS = \{(.*?)\n\};', source, re.S).group(1)
    keys = re.findall(r'^\s*([A-Za-z0-9_]+)\s*:', block, re.M)
    assert keys
    assert frozenset(k.lower() for k in keys) == MANAGED_CVARS


def test_strip_managed_cvars_blanks_values():
    assert strip_managed_cvars('set zmq_rcon_port "28888"\nset g_motd "hi"') == \
        'set zmq_rcon_port ""\nset g_motd "hi"'


def test_strip_managed_cvars_is_case_insensitive_and_keeps_the_tail():
    cfg = 'SETA Net_Port "27960" // comment\nset sv_tags "a"'
    assert strip_managed_cvars(cfg) == 'SETA Net_Port "" // comment\nset sv_tags "a"'


def test_keep_cvar_replaces_preset_line_with_instance_line():
    text, changed = merge_keep_cvars('seta sv_tags "a"\nset g_motd "m"', 'set SV_TAGS "b"', ['sv_tags'])
    assert 'set SV_TAGS "b"' in text
    assert '"a"' not in text
    assert text == 'set SV_TAGS "b"\nset g_motd "m"'
    assert changed == ['sv_tags']


def test_keep_cvar_multiple_instance_lines_keep_order():
    preset = 'set g_motd "m"\nset sv_tags "a"\nset fraglimit "10"\nset sv_tags "a2"'
    instance = 'set sv_tags "b1"\nset other "x"\nseta sv_tags "b2"'
    text, changed = merge_keep_cvars(preset, instance, ['sv_tags'])
    assert text == 'set g_motd "m"\nset sv_tags "b1"\nseta sv_tags "b2"\nset fraglimit "10"'
    assert changed == ['sv_tags']


def test_keep_cvar_absent_on_instance_drops_preset_line():
    text, changed = merge_keep_cvars('set sv_tags "a"\nset g_motd "m"', 'set g_motd "other"', ['sv_tags'])
    assert text == 'set g_motd "m"'
    assert changed == ['sv_tags']


def test_keep_cvar_absent_in_preset_appends_instance_line():
    text, changed = merge_keep_cvars('set g_motd "m"', 'set sv_tags "b"', ['sv_tags'])
    assert text == 'set g_motd "m"\nset sv_tags "b"'
    assert changed == ['sv_tags']


def test_keep_cvar_identical_line_is_not_reported_as_changed():
    text, changed = merge_keep_cvars('set sv_tags "a"', 'set sv_tags "a"', ['sv_tags', 'absent_both'])
    assert text == 'set sv_tags "a"'
    assert changed == []


def test_keep_cvar_merge_blanks_managed_values_of_both_sides():
    text, changed = merge_keep_cvars('set net_port "1"', 'set net_port "27961"', ['net_port'])
    assert text == 'set net_port ""'
    assert changed == []


# --- plugin names --------------------------------------------------------------

def test_qlx_plugin_names_drop_helpers_and_subfolders(env):
    scripts = env / 'scripts'
    (scripts / 'sub').mkdir(parents=True)
    for rel in ('a.py', 'helper.py', 'sub/x.py', '__init__.py', 'iouonegirl.py'):
        (scripts / rel).write_text('# plugin\n', encoding='utf-8')
    (scripts / 'a.ql-plugin.json').write_text(json.dumps({'depends_on': ['helper.py']}), encoding='utf-8')
    checked = ['a.py', 'helper.py', 'sub/x.py', '__init__.py', 'iouonegirl.py']
    assert qlx_plugin_names(checked, str(scripts), 'minqlx') == ['a']


def test_qlx_plugin_names_honour_depends_on_of_a_shared_pool_plugin(env):
    # The editor's plugin tree also lists the runtime's shared pool plugins, so
    # a pool plugin's depends_on makes its helper a library there too.
    scripts = env / 'scripts'
    scripts.mkdir()
    (scripts / 'helper.py').write_text('# helper\n', encoding='utf-8')
    (scripts / 'b.py').write_text('# b\n', encoding='utf-8')
    pool = env / 'data' / 'shared-plugins' / 'minqlx'
    pool.mkdir(parents=True)
    (pool / 'pooled.py').write_text('# pooled\n', encoding='utf-8')
    (pool / 'pooled.ql-plugin.json').write_text(json.dumps({'depends_on': ['helper.py']}), encoding='utf-8')
    assert qlx_plugin_names(['b.py', 'helper.py', 'pooled.py'], str(scripts), 'minqlx') == ['b', 'pooled']


# --- build_preset_target -------------------------------------------------------

def test_hostname_is_always_the_instances(env):
    host = _host()
    instance = _instance(host, server_cfg='set sv_hostname "Old cfg name"\nset g_motd "inst"')
    preset = _preset(env, configs={'server.cfg': 'set sv_hostname "Preset Server"\nset g_motd "from preset"'})

    target = build_preset_target(instance, preset, None, [])
    assert target['payload']['hostname'] == 'My Server'
    assert target['payload']['configs']['server.cfg'] == \
        'set sv_hostname "My Server"\nset g_motd "from preset"'

    kept = build_preset_target(instance, preset, None, ['sv_hostname'])
    assert kept['payload']['configs']['server.cfg'] == \
        'set sv_hostname "My Server"\nset g_motd "from preset"'


def test_hostname_line_is_appended_when_the_preset_has_none(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, configs={'server.cfg': 'set g_motd "x"'})
    target = build_preset_target(instance, preset, None, [])
    assert target['payload']['configs']['server.cfg'] == 'set g_motd "x"\nset sv_hostname "My Server"'


def test_server_cfg_is_stripped_then_merged(env):
    host = _host()
    instance = _instance(host, server_cfg='set sv_tags "mine"\nset zmq_rcon_port "28888"')
    preset = _preset(env, configs={
        'server.cfg': 'set sv_hostname "x"\nset sv_tags "theirs"\nset zmq_rcon_port "1"',
        'mappool.txt': 'campgrounds|ffa\n',
        'extra/custom.cfg': 'set a "1"',
    })
    target = build_preset_target(instance, preset, None, ['sv_tags', 'qlx_plugins'])
    configs = target['payload']['configs']
    assert configs['server.cfg'] == 'set sv_hostname "My Server"\nset sv_tags "mine"\nset zmq_rcon_port ""'
    assert configs['mappool.txt'] == 'campgrounds|ffa\n'
    assert configs['extra/custom.cfg'] == 'set a "1"'
    assert configs['access.txt'] == '' and configs['workshop.txt'] == ''
    assert target['payload']['config_folders'] == ['extra']
    assert target['kept_cvars'] == ['sv_tags']
    assert target['keep_cvars'] == ['sv_tags']


def test_keep_cvars_none_uses_the_collected_list(env):
    host = _host()
    instance = _instance(host, server_cfg='set net_port "27961"\nset sv_tags "mine"')
    preset = _preset(env, configs={'server.cfg': 'set sv_tags "theirs"'})
    with patch('ui.preset_keep_cvars._build_qlds_args_string',
               return_value='+set sv_tags "x" +set qlx_plugins "a"'):
        target = build_preset_target(instance, preset, None, None)
    assert target['keep_cvars'] == ['sv_tags']
    assert 'set sv_tags "mine"' in target['payload']['configs']['server.cfg']


def test_legacy_preset_leaves_plugins_factories_hooks_admins_lan_rate_alone(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, scripts={'a.py': '# a\n'},
                     factories={'one.factories': '[]', 'two.factories': '[1]'})
    with patch.object(preset_apply, 'read_live_admins', side_effect=AssertionError('not read')):
        target = build_preset_target(instance, preset, None, [])
    payload = target['payload']
    for key in ('checked_plugins', 'enabled_hooks', 'admin_changes', 'lan_rate_enabled'):
        assert key not in payload
    assert payload['factories'] == {'one.factories': '[]', 'two.factories': '[1]'}
    assert 'draft_id' not in payload
    assert target['compatibility'] is None
    assert target['needs_decision'] is False


def test_recorded_preset_values_are_carried(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(
        env,
        scripts={'a.py': '# a\n', 'b.py': '# b\n', 'sub/x.py': '# x\n'},
        factories={'one.factories': '[]', 'two.factories': '[1]'},
        checked_plugins=['a.py', 'sub/x.py'],
        checked_factories=['two.factories', 'missing.factories'],
        enabled_hooks=['hook.so'],
        lan_rate_enabled=True,
        admins=[{'steam_id64': '76561198000000001', 'level': 5},
                {'steam_id64': '76561198000000002', 'level': 3}],
    )
    current = [{'steam_id64': '76561198000000002', 'level': 3},
               {'steam_id64': '76561198000000003', 'level': 4}]
    with patch.object(preset_apply, 'read_live_admins', return_value=(current, {}, None)):
        target = build_preset_target(instance, preset, None, [])
    payload = target['payload']
    assert payload['checked_plugins'] == ['a']
    assert payload['factories'] == {'two.factories': '[1]'}
    assert payload['enabled_hooks'] == ['hook.so']
    assert payload['lan_rate_enabled'] is True
    assert payload['admin_changes'] == [
        {'steam_id64': '76561198000000001', 'level': 5},
        {'steam_id64': '76561198000000003', 'level': 0},
    ]
    assert os.path.isfile(os.path.join(env, 'qlds-drafts', payload['draft_id'], 'scripts', 'a.py'))


def test_unreadable_admin_list_only_adds(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, admins=[{'steam_id64': '76561198000000001', 'level': 5}])
    with patch.object(preset_apply, 'read_live_admins', return_value=(None, None, 'unreachable')):
        target = build_preset_target(instance, preset, None, [])
    assert target['payload']['admin_changes'] == [{'steam_id64': '76561198000000001', 'level': 5}]


def test_unsupported_lan_rate_is_clamped_off(env):
    host = _host(os_type='ubuntu', lan_rate_uses_hook=False)
    instance = _instance(host, lan_rate_enabled=False)
    preset = _preset(env, lan_rate_enabled=True)
    target = build_preset_target(instance, preset, None, [])
    assert target['payload']['lan_rate_enabled'] is False

    enabled = _instance(host, name='inst2', port=27961, lan_rate_enabled=True)
    assert build_preset_target(enabled, preset, None, [])['payload']['lan_rate_enabled'] is True


def _with_compatibility(compatibility, checked_plugins):
    """read_preset_payload, plus a compatibility report as apply_compatibility
    shapes it (a real cross-runtime report needs both builtin catalogs)."""
    real = preset_apply.read_preset_payload

    def fake(preset, target_runtime=None):
        data = real(preset, target_runtime)
        data['compatibility'] = compatibility
        data['checked_plugins'] = checked_plugins
        return data
    return patch.object(preset_apply, 'read_preset_payload', side_effect=fake)


def test_needs_decision_when_stripped_replacement_not_accepted(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, scripts={'a.py': '# a\n', 'b.py': '# b\n', 'c.py': '# c\n'},
                     checked_plugins=['a.py', 'b.py'])
    compatibility = {
        'preset_runtime': 'minqlxtended', 'target_runtime': 'minqlx',
        'stripped': [
            {'path': 'b.py', 'replacement': 'b.py', 'originally_checked': True},
            {'path': 'gone.py', 'replacement': None, 'originally_checked': True},
        ],
        'replacements': {'b.py': '# b target\n', 'c.py': '# c target\n'},
        'auto_accepted': ['c.py'],
    }
    with _with_compatibility(compatibility, ['a.py']):
        undecided = build_preset_target(instance, preset, None, [])
        accepted = build_preset_target(instance, preset, ['b.py'], [])
    assert undecided['needs_decision'] is True
    assert undecided['compatibility'] == compatibility
    assert undecided['payload']['checked_plugins'] == ['a']
    assert accepted['needs_decision'] is False
    assert accepted['payload']['checked_plugins'] == ['a', 'b']


def test_explicit_empty_accepted_list_is_a_decision(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, scripts={'a.py': '# a\n', 'b.py': '# b\n'},
                     checked_plugins=['a.py', 'b.py'])
    compatibility = {
        'preset_runtime': 'minqlxtended', 'target_runtime': 'minqlx',
        'stripped': [{'path': 'b.py', 'replacement': 'b.py', 'originally_checked': True}],
        'replacements': {'b.py': '# b target\n'},
        'auto_accepted': [],
    }
    with _with_compatibility(compatibility, ['a.py']):
        declined = build_preset_target(instance, preset, [], [])
        undecided = build_preset_target(instance, preset, None, [])
    assert declined['needs_decision'] is False
    assert 'b' not in declined['payload']['checked_plugins']
    assert undecided['needs_decision'] is True


def test_payload_passes_the_save_validators(env):
    from ui.routes.draft_routes import _draft_exists, _validate_draft_id
    from ui.routes.instance_routes import (
        _validate_config_folders, _validate_configs_map, _validate_factories_map,
    )
    host = _host()
    instance = _instance(host)
    preset = _preset(env, configs={'server.cfg': 'set g_motd "x"', 'sub/a.cfg': ''},
                     factories={'one.factories': '[]'}, checked_plugins=[])
    payload = build_preset_target(instance, preset, None, [])['payload']
    assert _validate_configs_map(payload['configs'], require_protected=True) == (None, None)
    assert _validate_factories_map(payload['factories']) == (None, None)
    assert _validate_config_folders(payload['config_folders']) == (None, None)
    assert _validate_draft_id(payload['draft_id']) and _draft_exists(payload['draft_id'])
    assert payload['checked_plugins'] == []


def test_missing_preset_folder_is_an_apply_error(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env)
    preset.path = str(env / 'nowhere')
    with pytest.raises(preset_apply.PresetApplyError) as err:
        build_preset_target(instance, preset, None, [])
    assert err.value.status == 500


# --- diff and hash ---------------------------------------------------------------

def _materialize(instance, target):
    """Write the target into the instance's config dir the way save_instance_config does."""
    import shutil
    from ui.routes.draft_routes import _get_draft_scripts_path
    from ui.routes.instance_routes import _sync_configs_to_disk, _sync_factories_to_disk
    payload = target['payload']
    config_dir = os.path.join('configs', instance.host.name, str(instance.id))
    _sync_configs_to_disk(config_dir, payload['configs'], payload['config_folders'])
    _sync_factories_to_disk(os.path.join(config_dir, 'factories'), payload['factories'])
    if payload.get('draft_id'):
        shutil.copytree(_get_draft_scripts_path(payload['draft_id']),
                        os.path.join(config_dir, 'scripts'), dirs_exist_ok=True)


def test_diff_reports_server_cfg_change(env):
    host = _host()
    instance = _instance(host, server_cfg='set sv_hostname "My Server"\nset g_motd "old"',
                         qlx_plugins='a, b', lan_rate_enabled=False, ld_preload_hooks='x.so')
    preset = _preset(
        env, configs={'server.cfg': 'set g_motd "new"'}, scripts={'a.py': '# a\n'},
        factories={'one.factories': '[]'}, checked_plugins=['a.py'], enabled_hooks=['y.so'],
        lan_rate_enabled=True,
        admins=[{'steam_id64': '76561198000000001', 'level': 5}])
    _add_preset_hook(preset, 'y.so')
    with patch.object(preset_apply, 'read_live_admins',
                      return_value=([{'steam_id64': '76561198000000003', 'level': 4}], {}, None)):
        target = build_preset_target(instance, preset, None, [])
    diff = diff_preset_target(instance, target)

    by_path = {entry['path']: entry for entry in diff['files']}
    assert by_path['server.cfg']['change'] == 'modified'
    assert '-set g_motd "old"' in by_path['server.cfg']['diff']
    assert '+set g_motd "new"' in by_path['server.cfg']['diff']
    assert by_path['factories/one.factories']['change'] == 'added'
    assert by_path['scripts/a.py']['change'] == 'added'
    assert diff['plugins'] == {'before': ['a', 'b'], 'after': ['a']}
    assert diff['hooks'] == {'before': ['x.so'], 'after': ['y.so']}
    assert diff['admins'] == {'add': [{'steam_id64': '76561198000000001', 'level': 5}],
                              'remove': ['76561198000000003']}
    assert diff['lan_rate'] == {'before': False, 'after': True}
    assert diff['unchanged'] is False


def test_identical_target_is_unchanged(env):
    host = _host()
    instance = _instance(host, qlx_plugins='a', lan_rate_enabled=False)
    preset = _preset(env, configs={'server.cfg': 'set g_motd "x"'}, scripts={'a.py': '# a\n'},
                     factories={'one.factories': '[]'}, checked_plugins=['a.py'],
                     enabled_hooks=[], lan_rate_enabled=False,
                     admins=[{'steam_id64': '76561198000000001', 'level': 5}])
    same = ([{'steam_id64': '76561198000000001', 'level': 5}], {}, None)
    with patch.object(preset_apply, 'read_live_admins', return_value=same):
        target = build_preset_target(instance, preset, None, [])
    _materialize(instance, target)
    diff = diff_preset_target(instance, target)
    assert diff['files'] == []
    assert diff['plugins'] == {'before': ['a'], 'after': ['a']}
    assert diff['hooks'] == {'before': [], 'after': []}
    assert diff['admins'] is None  # identical admin lists leave no admin_changes
    assert diff['lan_rate'] == {'before': False, 'after': False}
    assert diff['unchanged'] is True


def test_unmanaged_instance_files_are_not_reported_as_removed(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, configs={'server.cfg': 'set g_motd "x"'})
    target = build_preset_target(instance, preset, None, [])
    _materialize(instance, target)
    config_dir = os.path.join('configs', host.name, str(instance.id))
    os.makedirs(os.path.join(config_dir, 'user-hooks'))
    with open(os.path.join(config_dir, 'user-hooks', 'h.so'), 'wb') as f:
        f.write(b'\x7fELF')
    assert diff_preset_target(instance, target)['unchanged'] is True


def test_legacy_preset_diff_has_no_plugin_hook_admin_lan_parts(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, configs={'server.cfg': 'set g_motd "x"'})
    target = build_preset_target(instance, preset, None, [])
    diff = diff_preset_target(instance, target)
    for key in ('plugins', 'hooks', 'admins', 'lan_rate'):
        assert diff[key] is None
    assert diff['files']
    assert diff['unchanged'] is False
    _materialize(instance, target)
    assert diff_preset_target(instance, target)['unchanged'] is True


def test_diff_removes_leftover_scripts_and_factories(env):
    host = _host()
    instance = _instance(host)
    config_dir = os.path.join('configs', host.name, str(instance.id))
    os.makedirs(os.path.join(config_dir, 'scripts'))
    os.makedirs(os.path.join(config_dir, 'factories'))
    with open(os.path.join(config_dir, 'scripts', 'old.py'), 'w') as f:
        f.write('# old\n')
    with open(os.path.join(config_dir, 'factories', 'old.factories'), 'w') as f:
        f.write('[]')
    preset = _preset(env, factories={}, checked_plugins=[])
    target = build_preset_target(instance, preset, None, [])
    changes = {e['path']: e['change'] for e in diff_preset_target(instance, target)['files']}
    assert changes['scripts/old.py'] == 'removed'
    assert changes['factories/old.factories'] == 'removed'


def test_legacy_preset_sends_no_draft_and_leaves_scripts(env):
    host = _host()
    instance = _instance(host, qlx_plugins='old')
    scripts_dir = os.path.join('configs', host.name, str(instance.id), 'scripts')
    os.makedirs(scripts_dir)
    with open(os.path.join(scripts_dir, 'old.py'), 'w') as f:
        f.write('# old\n')
    preset = _preset(env, configs={'server.cfg': 'set g_motd "x"'}, scripts={'a.py': '# a\n'})
    target = build_preset_target(instance, preset, None, [])
    assert 'draft_id' not in target['payload']
    assert 'checked_plugins' not in target['payload']
    diff = diff_preset_target(instance, target)
    assert not [e for e in diff['files'] if e['path'].startswith('scripts/')]
    assert diff['plugins'] is None


def test_target_hash_ignores_draft_id_and_changes_with_content(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, configs={'server.cfg': 'set g_motd "x"'}, scripts={'a.py': '# a\n'},
                     checked_plugins=['a.py'])
    first = build_preset_target(instance, preset, None, [])
    second = build_preset_target(instance, preset, None, [])
    assert first['payload']['draft_id'] != second['payload']['draft_id']
    assert target_hash(first) == target_hash(second)

    changed_cfg = build_preset_target(instance, preset, None, [])
    changed_cfg['payload']['configs']['server.cfg'] += '\nset a "1"'
    assert target_hash(changed_cfg) != target_hash(first)

    from ui.routes.draft_routes import _get_draft_scripts_path
    changed_script = build_preset_target(instance, preset, None, [])
    scripts = _get_draft_scripts_path(changed_script['payload']['draft_id'])
    with open(os.path.join(scripts, 'a.py'), 'w') as f:
        f.write('# changed\n')
    assert target_hash(changed_script) != target_hash(first)


def _add_preset_hook(preset, name, data=b'\x7fELF1'):
    hooks = os.path.join(preset.path, 'user-hooks')
    os.makedirs(hooks, exist_ok=True)
    with open(os.path.join(hooks, name), 'wb') as f:
        f.write(data)


def _add_instance_hook(instance, name):
    hooks = os.path.join('configs', instance.host.name, str(instance.id), 'user-hooks')
    os.makedirs(hooks, exist_ok=True)
    with open(os.path.join(hooks, name), 'wb') as f:
        f.write(b'\x7fELF')


def test_hook_without_a_file_is_dropped_like_the_save_does(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, enabled_hooks=['ghost.so'], checked_plugins=[])
    target = build_preset_target(instance, preset, None, [])
    _materialize(instance, target)
    diff = diff_preset_target(instance, target)
    assert diff['hooks'] == {'before': [], 'after': []}
    assert diff['unchanged'] is True


def test_stored_hook_whose_file_is_missing_is_a_change(env):
    host = _host()
    instance = _instance(host, ld_preload_hooks='ghost.so')
    preset = _preset(env, enabled_hooks=['ghost.so'], checked_plugins=[])
    target = build_preset_target(instance, preset, None, [])
    _materialize(instance, target)
    diff = diff_preset_target(instance, target)
    assert diff['hooks'] == {'before': ['ghost.so'], 'after': []}
    assert diff['unchanged'] is False


def test_hook_file_from_the_preset_is_added_and_enabled(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, enabled_hooks=['new.so'], checked_plugins=[])
    _add_preset_hook(preset, 'new.so')
    target = build_preset_target(instance, preset, None, [])
    _materialize(instance, target)
    diff = diff_preset_target(instance, target)
    assert {e['path']: e['change'] for e in diff['files']}['user-hooks/new.so'] == 'added'
    assert diff['hooks'] == {'before': [], 'after': ['new.so']}
    assert diff['unchanged'] is False


def test_hook_file_already_on_the_instance_wins_over_the_preset(env):
    host = _host()
    instance = _instance(host, ld_preload_hooks='h.so')
    _add_instance_hook(instance, 'h.so')
    preset = _preset(env, enabled_hooks=['h.so'], checked_plugins=[])
    _add_preset_hook(preset, 'h.so', b'\x7fELF-other')
    target = build_preset_target(instance, preset, None, [])
    _materialize(instance, target)
    diff = diff_preset_target(instance, target)
    assert not [e for e in diff['files'] if e['path'].startswith('user-hooks/')]
    assert diff['unchanged'] is True


def test_target_hash_changes_with_a_preset_hook_binary(env):
    host = _host()
    instance = _instance(host)
    preset = _preset(env, checked_plugins=[])
    _add_preset_hook(preset, 'h.so', b'\x7fELF-1')
    first = target_hash(build_preset_target(instance, preset, None, []))
    assert target_hash(build_preset_target(instance, preset, None, [])) == first
    _add_preset_hook(preset, 'h.so', b'\x7fELF-2')
    assert target_hash(build_preset_target(instance, preset, None, [])) != first
