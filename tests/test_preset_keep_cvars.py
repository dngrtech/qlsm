"""keep_cvars: the cvars a preset apply must not overwrite on a server."""
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.test_addon_registry import addon_app, write_addon  # noqa: F401
from ui import plugin_manifest, preset_keep_cvars
from ui.preset_keep_cvars import collect_keep_cvars

BUILDER = 'ui.preset_keep_cvars._build_qlds_args_string'


def _instance(plugins='', instance_id=1):
    return SimpleNamespace(
        id=instance_id, host=SimpleNamespace(name='h1'), qlx_plugins=plugins,
    )


def _write_plugin(scripts_dir, name, cvars):
    os.makedirs(scripts_dir, exist_ok=True)
    with open(os.path.join(scripts_dir, name + '.py'), 'w', encoding='utf-8') as f:
        f.write('# plugin\n')
    with open(os.path.join(scripts_dir, name + '.ql-plugin.json'), 'w', encoding='utf-8') as f:
        json.dump({'cvars': cvars}, f)


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_launch_args_cvars_are_collected(app_context, in_tmp):
    args = '+set net_port 27960 +set sv_hostname "x" +set qlx_plugins "a, b"'
    with patch(BUILDER, return_value=args):
        result = collect_keep_cvars(_instance(), {})
    assert [c['cvar'] for c in result] == ['net_port', 'sv_hostname']
    assert result[0]['sources'] == ['launch args']


def test_builder_failure_skips_launch_args(app_context, in_tmp):
    with patch(BUILDER, side_effect=ValueError('bad instance')):
        assert collect_keep_cvars(_instance(), {}) == []


def test_addon_hook_contributes_with_its_label(addon_app, in_tmp):  # noqa: F811
    build, packages, _ = addon_app
    write_addon(packages, 'stats', manifest={'id': 'stats', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('preset.keep_cvars')
            def keep(instance):
                return ["qlx_statsHubServerId", 5]
    ''')
    app = build()
    from ui.addons import registry
    with app.app_context(), patch(BUILDER, return_value=''), \
            patch.object(registry, '_gates_open', return_value=True):
        result = collect_keep_cvars(_instance(), {})
    assert result == [{'cvar': 'qlx_statsHubServerId', 'sources': ['addon:stats']}]


def test_manifest_per_server_cvar_is_collected(app_context, in_tmp):
    scripts = in_tmp / 'configs' / 'h1' / '1' / 'scripts'
    _write_plugin(str(scripts), 'myplugin', [
        {'cvar': 'qlx_myId', 'per_server': True}, {'cvar': 'qlx_other'},
    ])
    with patch(BUILDER, return_value=''):
        result = collect_keep_cvars(_instance(plugins='myplugin'), {})
    assert result == [{'cvar': 'qlx_myId', 'sources': ['plugin:myplugin.py']}]


def test_checked_plugins_of_the_preset_are_scanned(app_context, in_tmp):
    preset = in_tmp / 'presets' / 'p1'
    _write_plugin(str(preset / 'scripts'), 'fromPreset', [
        {'cvar': 'qlx_presetId', 'per_server': True},
    ])
    payload = {'path': str(preset), 'checked_plugins': ['fromPreset.py']}
    with patch(BUILDER, return_value=''):
        result = collect_keep_cvars(_instance(), payload)
    assert result == [{'cvar': 'qlx_presetId', 'sources': ['plugin:fromPreset.py']}]


def test_duplicates_merge_sources_case_insensitively(app_context, in_tmp):
    scripts = in_tmp / 'configs' / 'h1' / '1' / 'scripts'
    _write_plugin(str(scripts), 'myplugin', [{'cvar': 'SV_HOSTNAME', 'per_server': True}])
    with patch(BUILDER, return_value='+set sv_hostname "x"'):
        result = collect_keep_cvars(_instance(plugins='myplugin'), {})
    assert result == [{'cvar': 'sv_hostname', 'sources': ['launch args', 'plugin:myplugin.py']}]


def test_qlx_plugins_is_never_kept(app_context, in_tmp):
    scripts = in_tmp / 'configs' / 'h1' / '1' / 'scripts'
    _write_plugin(str(scripts), 'myplugin', [{'cvar': 'QLX_Plugins', 'per_server': True}])
    with patch(BUILDER, return_value='+set qlx_plugins "a"'):
        assert collect_keep_cvars(_instance(plugins='myplugin'), {}) == []


def _write_pool_manifest(root, name, cvars):
    pool = root / plugin_manifest.MINQLX_PLUGINS_POOL_DIR
    os.makedirs(pool, exist_ok=True)
    with open(pool / (name + '.ql-plugin.json'), 'w', encoding='utf-8') as f:
        json.dump({'cvars': cvars}, f)


def test_enabled_pool_only_plugin_is_collected(app_context, in_tmp):
    _write_pool_manifest(in_tmp, 'poolplugin', [{'cvar': 'qlx_poolId', 'per_server': True}])
    with patch(BUILDER, return_value=''):
        result = collect_keep_cvars(_instance(plugins='poolplugin'), {})
    assert result == [{'cvar': 'qlx_poolId', 'sources': ['plugin:poolplugin.py']}]


def test_checked_pool_only_plugin_is_collected(app_context, in_tmp):
    _write_pool_manifest(in_tmp, 'poolplugin', [{'cvar': 'qlx_poolId', 'per_server': True}])
    preset = in_tmp / 'presets' / 'p1'
    os.makedirs(preset / 'scripts')
    payload = {'path': str(preset), 'checked_plugins': ['poolplugin.py']}
    with patch(BUILDER, return_value=''):
        result = collect_keep_cvars(_instance(), payload)
    assert result == [{'cvar': 'qlx_poolId', 'sources': ['plugin:poolplugin.py']}]
