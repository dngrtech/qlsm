"""Per-instance compatibility dry-run and the confirmation fingerprint."""
import json
import os
import shutil
from types import SimpleNamespace

import pytest

from ui import plugin_pool, preset_compat, runtime_upgrade
from ui.models import InstanceStatus
from ui.runtime_upgrade import (
    UpgradeInputsChanged,
    capture_upgrade_inputs,
    classification_fingerprint,
    classify_instance,
    instance_plugin_snapshot,
    materialize_upgrade_inputs,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REAL_BUILTIN_PRESETS = os.path.join(REPO_ROOT, 'configs', 'presets', '_builtin')
STOCK_MINQLX_SCRIPTS = os.path.join(REAL_BUILTIN_PRESETS, 'default', 'scripts')


def _stock(name):
    with open(os.path.join(STOCK_MINQLX_SCRIPTS, name), 'r', encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Instance configs and the operator plugin pool live under tmp_path.

    The shipped, git-tracked builtin presets and ql-assets are read in place
    (as tests/test_preset_compat.py does); nothing under the real configs/<host>
    trees or data/ is touched.
    """
    configs = tmp_path / 'configs'
    configs.mkdir()
    operator_pool = tmp_path / 'shared-plugins'
    operator_pool.mkdir()
    monkeypatch.setattr(runtime_upgrade, 'CONFIGS_BASE', str(configs))
    monkeypatch.setattr(plugin_pool, 'OPERATOR_POOL_BASE', str(operator_pool))
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', REAL_BUILTIN_PRESETS)
    return SimpleNamespace(tmp=tmp_path, configs=configs, operator_pool=operator_pool)


def _host(env, instances=(), name='h1'):
    host = SimpleNamespace(id=7, name=name, runtime='minqlx', lan_rate_uses_hook=False,
                           provider='vultr', redis_unix_socket=False, instances=[])
    for spec in instances:
        host.instances.append(_instance(env, host, **spec))
    return host


def _instance(env, host, id=1, qlx_plugins=None, scripts=None, files=None,
              status=InstanceStatus.RUNNING, **fields):
    inst = SimpleNamespace(
        id=id, name=f'inst{id}', port=27960 + id, hostname=f'Server {id}',
        lan_rate_enabled=False, config='{"server.cfg": "x"}', qlx_plugins=qlx_plugins,
        ld_preload_hooks=None, cpu_affinity=None, redis_db=None,
        zmq_rcon_port=28888 + id, zmq_rcon_password='rcon', zmq_stats_port=29999 + id,
        zmq_stats_password='stats', status=status, host=host, logs='log line',
        last_updated='2026-11-03T00:00:00', created_at='2026-11-01T00:00:00',
        runtime_invocation_id='inv-1',
    )
    for key, value in fields.items():
        setattr(inst, key, value)
    root = env.configs / host.name / str(id)
    (root / 'scripts').mkdir(parents=True, exist_ok=True)
    for rel, content in (scripts or {}).items():
        _write(root / 'scripts' / rel, content)
    for rel, content in (files or {}).items():
        _write(root / rel, content)
    return inst


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding='utf-8')


def _fp(host):
    return classification_fingerprint(capture_upgrade_inputs(host))


# --- classification ---------------------------------------------------------

def test_untouched_stock_plugin_auto_accepted(env):
    host = _host(env, [dict(scripts={'balance.py': _stock('balance.py')},
                            qlx_plugins='balance')])
    result = classify_instance(host.instances[0])
    assert 'balance.py' in result['auto_accepted']
    assert result['stripped'] == []
    assert result['checked_plugins'] == ['balance.py']
    assert result['instance_id'] == 1
    assert result['instance_name'] == 'inst1'


def test_edited_plugin_reported_replaceable(env):
    host = _host(env, [dict(scripts={'branding.py': _stock('branding.py') + '\n# mine\n'})])
    result = classify_instance(host.instances[0])
    assert [row['path'] for row in result['stripped']] == ['branding.py']
    assert result['stripped'][0]['kind'] == 'replaceable'
    assert 'branding.py' in result['replacements']


def test_enabled_custom_plugin_reported_unavailable(env):
    host = _host(env, [dict(scripts={'my_custom.py': 'import minqlx\n'},
                            qlx_plugins='my_custom')])
    result = classify_instance(host.instances[0])
    assert len(result['stripped']) == 1
    row = result['stripped'][0]
    assert row['kind'] == 'unavailable'
    assert row['originally_checked'] is True
    assert result['checked_plugins'] == []


@pytest.mark.parametrize('raw', [None, ''])
def test_classify_instance_with_null_qlx_plugins(env, raw):
    host = _host(env, [dict(scripts={'my_custom.py': 'import minqlx\n'}, qlx_plugins=raw)])
    result = classify_instance(host.instances[0])
    assert result['checked_plugins'] is None


def test_snapshot_reads_py_only_and_skips_undecodable(env):
    host = _host(env, [dict(
        qlx_plugins=' balance , ,essentials',
        scripts={'balance.py': 'x = 1\n', 'sub/helper.py': 'y = 2\n',
                 'bad.py': b'\xff\xfe\x00broken', 'requirements.txt': 'requests\n'})])
    snapshot = instance_plugin_snapshot(host.instances[0])
    assert snapshot['scripts'] == {'balance.py': 'x = 1\n', 'sub/helper.py': 'y = 2\n'}
    assert snapshot['checked_plugins'] == ['balance.py', 'essentials.py']


def test_snapshot_of_missing_config_dir_is_empty(env):
    host = _host(env, [dict()])
    shutil.rmtree(env.configs / 'h1' / '1')
    assert instance_plugin_snapshot(host.instances[0])['scripts'] == {}
    inputs = capture_upgrade_inputs(host)
    assert inputs['instances'][0]['config_files'] == {}


# --- capture shape ----------------------------------------------------------

def test_capture_is_json_serializable_and_holds_digests_not_text(env):
    host = _host(env, [dict(id=2, scripts={'branding.py': _stock('branding.py') + '#x\n'},
                            qlx_plugins='branding'),
                       dict(id=10, scripts={'balance.py': _stock('balance.py')})])
    inputs = capture_upgrade_inputs(host)
    round_tripped = json.loads(json.dumps(inputs))
    assert round_tripped == inputs
    assert classification_fingerprint(round_tripped) == classification_fingerprint(inputs)
    first = inputs['instances'][0]
    assert first['instance_id'] == 2
    assert first['original_status'] == 'running'
    assert first['qlx_plugins_raw'] == 'branding'
    stripped = first['classification']['stripped']
    assert stripped[0]['kind'] == 'replaceable' and stripped[0]['originally_checked'] is True
    # Replacement rows carry a digest, never the file text.
    digest = first['classification']['replacements']['branding.py']
    assert isinstance(digest, str) and len(digest) == 64
    assert inputs['target_runtime']['excluded_system_hooks'] == ['force_rate.so']
    assert inputs['target_runtime']['runtime'] == 'minqlxtended'
    assert 'requirements.txt' in inputs['target_runtime']['builtin_pool']


def test_null_and_empty_qlx_plugins_are_distinguished(env):
    null_fp = _fp(_host(env, [dict(qlx_plugins=None)]))
    empty_fp = _fp(_host(env, [dict(qlx_plugins='')]))
    assert null_fp != empty_fp


# --- fingerprint sensitivity ------------------------------------------------

def test_fingerprint_changes_when_plugin_edited(env):
    """Two edits to an already-incompatible plugin keep path and verdict the
    same; only content identity can tell them apart."""
    host = _host(env, [dict(scripts={'branding.py': _stock('branding.py') + '# a\n'},
                            qlx_plugins='branding')])
    before_classify = classify_instance(host.instances[0])
    before = _fp(host)
    _write(env.configs / 'h1' / '1' / 'scripts' / 'branding.py', _stock('branding.py') + '# b\n')
    after_classify = classify_instance(host.instances[0])
    assert before_classify['stripped'] == after_classify['stripped']
    assert _fp(host) != before


def test_fingerprint_changes_on_selection_only_edit(env):
    host = _host(env, [dict(scripts={'balance.py': _stock('balance.py')}, qlx_plugins='')])
    before = _fp(host)
    host.instances[0].qlx_plugins = 'balance'
    assert _fp(host) != before


def test_fingerprint_changes_when_undecodable_file_changes(env):
    host = _host(env, [dict(scripts={'bad.py': b'\xff\x00one'})])
    before_classify = classify_instance(host.instances[0])
    before = _fp(host)
    _write(env.configs / 'h1' / '1' / 'scripts' / 'bad.py', b'\xff\x00two')
    assert classify_instance(host.instances[0]) == before_classify
    assert _fp(host) != before


@pytest.mark.parametrize('rel', [
    'scripts/requirements.txt', 'server.cfg', 'factories/ffa.factories',
    'user-hooks/anti_null.so',
])
def test_fingerprint_changes_when_config_tree_file_changes(env, rel):
    host = _host(env, [dict(files={rel: b'one'})])
    before = _fp(host)
    _write(env.configs / 'h1' / '1' / rel, b'two')
    assert _fp(host) != before


def test_fingerprint_changes_when_config_tree_file_added(env):
    host = _host(env, [dict()])
    before = _fp(host)
    _write(env.configs / 'h1' / '1' / 'access.txt', 'x')
    assert _fp(host) != before


@pytest.mark.parametrize('field,value', [
    ('ld_preload_hooks', 'anti_null.so'),
    ('lan_rate_enabled', True),
    ('port', 27999),
    ('hostname', 'Renamed'),
    ('config', '{"server.cfg": "y"}'),
    ('cpu_affinity', 3),
    ('redis_db', 4),
    ('zmq_rcon_password', 'changed'),
    ('status', InstanceStatus.STOPPED),
])
def test_fingerprint_changes_on_instance_field(env, field, value):
    host = _host(env, [dict()])
    before = _fp(host)
    setattr(host.instances[0], field, value)
    assert _fp(host) != before


def test_fingerprint_changes_on_host_hook_mode(env):
    host = _host(env, [dict()])
    before = _fp(host)
    host.lan_rate_uses_hook = True
    assert _fp(host) != before


@pytest.mark.parametrize('field,value', [
    ('redis_unix_socket', True),
    ('provider', 'self'),  # flips is_self_host(): TCP Redis instead of the socket
])
def test_fingerprint_changes_on_host_redis_inputs(env, field, value):
    host = _host(env, [dict()])
    before = capture_upgrade_inputs(host)
    setattr(host, field, value)
    after = capture_upgrade_inputs(host)
    assert classification_fingerprint(after) != classification_fingerprint(before)
    if field == 'provider':
        assert before['host']['is_self_host'] is False
        assert after['host']['is_self_host'] is True


@pytest.mark.parametrize('hook', ['instance.plugins', 'instance.launch_args',
                                  'instance.ld_preload'])
def test_fingerprint_changes_when_addon_contribution_changes(env, monkeypatch, hook):
    import ui.addons

    contributions = {}

    def fake_dispatch(name, scope_id=0, *args, **kwargs):
        return list(contributions.get(name, []))

    monkeypatch.setattr(ui.addons, 'dispatch', fake_dispatch)
    host = _host(env, [dict()])
    contributions[hook] = ['first']
    before = capture_upgrade_inputs(host)
    assert before['instances'][0]['addon_contributions'][hook] == ['first']
    contributions[hook] = ['second']
    after = capture_upgrade_inputs(host)
    assert json.loads(json.dumps(after)) == after
    assert classification_fingerprint(after) != classification_fingerprint(before)


def test_fingerprint_ignores_logs_and_timestamps(env):
    host = _host(env, [dict()])
    before = _fp(host)
    inst = host.instances[0]
    inst.logs = 'something else entirely'
    inst.last_updated = '2030-01-01T00:00:00'
    inst.created_at = '2030-01-01T00:00:00'
    inst.runtime_invocation_id = 'inv-2'
    assert _fp(host) == before


def test_fingerprint_changes_when_operator_pool_changes(env):
    host = _host(env, [dict()])
    pool = env.operator_pool / 'minqlxtended'
    _write(pool / 'extra.py', 'one')
    before = _fp(host)
    _write(pool / 'extra.py', 'two')
    assert _fp(host) != before


def test_fingerprint_changes_when_target_replacement_content_changes(env, monkeypatch):
    builtin = env.tmp / 'builtin'
    shutil.copytree(REAL_BUILTIN_PRESETS, builtin)
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', str(builtin))
    host = _host(env, [dict(scripts={'branding.py': _stock('branding.py') + '# a\n'})])
    before_classify = classify_instance(host.instances[0])
    before = _fp(host)
    target = builtin / 'default-minqlxtended' / 'scripts' / 'branding.py'
    target.write_text(target.read_text(encoding='utf-8') + '\n# target edit\n', encoding='utf-8')
    after_classify = classify_instance(host.instances[0])
    assert [r['path'] for r in after_classify['stripped']] == \
        [r['path'] for r in before_classify['stripped']]
    assert _fp(host) != before


def test_fingerprint_changes_when_source_stock_changes(env, monkeypatch):
    builtin = env.tmp / 'builtin'
    shutil.copytree(REAL_BUILTIN_PRESETS, builtin)
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', str(builtin))
    host = _host(env, [dict()])
    before = _fp(host)
    stock = builtin / 'default' / 'scripts' / 'motd.py'
    stock.write_text(stock.read_text(encoding='utf-8') + '\n# drift\n', encoding='utf-8')
    assert _fp(host) != before


def test_fingerprint_is_deterministic_regardless_of_ordering(env):
    host = _host(env, [
        dict(id=2, scripts={'branding.py': _stock('branding.py') + '#x\n',
                            'my_custom.py': 'import minqlx\n'},
             qlx_plugins='my_custom,branding'),
        dict(id=10, scripts={'balance.py': _stock('balance.py')}),
    ])
    inputs = capture_upgrade_inputs(host)
    host.instances.reverse()
    assert classification_fingerprint(capture_upgrade_inputs(host)) == \
        classification_fingerprint(inputs)

    def scramble(value):
        if isinstance(value, dict):
            return {k: scramble(value[k]) for k in reversed(list(value))}
        if isinstance(value, list):
            return [scramble(v) for v in value]
        return value

    scrambled = scramble(inputs)
    scrambled['instances'].reverse()
    for inst in scrambled['instances']:
        inst['classification']['stripped'].reverse()
        inst['classification']['auto_accepted'].reverse()
    assert classification_fingerprint(scrambled) == classification_fingerprint(inputs)
    assert len(classification_fingerprint(inputs)) == 64


# --- materialize ------------------------------------------------------------

def test_materialize_copies_verified_bytes(env):
    host = _host(env, [dict(scripts={'bad.py': b'\xff\x00raw', 'branding.py': 'import minqlx\n'},
                            files={'server.cfg': 'set x 1\n', 'user-hooks/a.so': b'\x7fELF..'})])
    _write(env.operator_pool / 'minqlxtended' / 'extra.py', 'pool\n')
    inputs = capture_upgrade_inputs(host)
    dest = env.tmp / 'op' / 'inputs'
    materialize_upgrade_inputs(host, inputs, str(dest))
    inst_dir = dest / 'instances' / '1'
    assert (inst_dir / 'scripts' / 'bad.py').read_bytes() == b'\xff\x00raw'
    assert (inst_dir / 'server.cfg').read_text() == 'set x 1\n'
    assert (inst_dir / 'user-hooks' / 'a.so').read_bytes() == b'\x7fELF..'
    target_scripts = dest / 'target_default_preset_scripts'
    shipped = os.path.join(REAL_BUILTIN_PRESETS, 'default-minqlxtended', 'scripts', 'branding.py')
    with open(shipped, 'rb') as handle:
        assert (target_scripts / 'branding.py').read_bytes() == handle.read()
    assert (dest / 'target_operator_pool' / 'extra.py').read_text() == 'pool\n'
    assert (dest / 'target_builtin_pool' / 'requirements.txt').is_file()


def test_materialize_fails_when_a_file_changed(env):
    host = _host(env, [dict(files={'server.cfg': 'one'})])
    inputs = capture_upgrade_inputs(host)
    _write(env.configs / 'h1' / '1' / 'server.cfg', 'two')
    with pytest.raises(UpgradeInputsChanged):
        materialize_upgrade_inputs(host, inputs, str(env.tmp / 'dest'))


def test_materialize_fails_when_a_file_was_added(env):
    host = _host(env, [dict()])
    inputs = capture_upgrade_inputs(host)
    _write(env.operator_pool / 'minqlxtended' / 'late.py', 'x')
    with pytest.raises(UpgradeInputsChanged):
        materialize_upgrade_inputs(host, inputs, str(env.tmp / 'dest'))


def test_materialize_fails_when_a_file_was_removed(env):
    host = _host(env, [dict(files={'server.cfg': 'one'})])
    inputs = capture_upgrade_inputs(host)
    os.remove(env.configs / 'h1' / '1' / 'server.cfg')
    with pytest.raises(UpgradeInputsChanged):
        materialize_upgrade_inputs(host, inputs, str(env.tmp / 'dest'))


def test_materialize_refuses_a_non_empty_destination(env):
    host = _host(env, [dict()])
    inputs = capture_upgrade_inputs(host)
    dest = env.tmp / 'dest'
    _write(dest / 'leftover', 'x')
    with pytest.raises(ValueError):
        materialize_upgrade_inputs(host, inputs, str(dest))


# --- plugins enabled from the shared pool (no copy in scripts/) ---------------

COMPATIBLE_ANYWHERE = 'import minqlx\n\nclass poolmine(minqlx.Plugin):\n    pass\n'


def _rows(result):
    return {row['path']: row for row in result['stripped']}


def test_operator_pool_plugin_without_target_version_is_unavailable(env):
    _write(env.operator_pool / 'minqlx' / 'poolmine.py', COMPATIBLE_ANYWHERE)
    host = _host(env, [dict(qlx_plugins='poolmine')])
    result = classify_instance(host.instances[0])
    row = _rows(result)['poolmine.py']
    assert row['kind'] == 'unavailable' and row['replacement'] is None
    assert row['originally_checked'] is True and row['from_catalog'] is False
    assert result['checked_plugins'] == []
    assert 'poolmine.py' not in result['auto_accepted']


def test_builtin_pool_plugin_without_target_version_is_unavailable(env):
    host = _host(env, [dict(qlx_plugins='autokick')])
    result = classify_instance(host.instances[0])
    row = _rows(result)['autokick.py']
    assert row['kind'] == 'unavailable' and row['from_catalog'] is True
    assert result['checked_plugins'] == []


def test_stock_builtin_pool_plugin_the_target_ships_is_auto_accepted(env):
    # reset_acc.py is in the minqlx built-in pool (and manifest) but not in the
    # minqlx default preset; minqlxtended's default preset ships it.
    host = _host(env, [dict(qlx_plugins='reset_acc')])
    result = classify_instance(host.instances[0])
    assert result['stripped'] == []
    assert result['auto_accepted'] == ['reset_acc.py']
    assert result['checked_plugins'] == ['reset_acc.py']


def test_edited_operator_pool_copy_of_a_target_plugin_is_replaceable(env):
    _write(env.operator_pool / 'minqlx' / 'motd.py', _stock('motd.py') + '\n# pool edit\n')
    host = _host(env, [dict(qlx_plugins='motd')])
    result = classify_instance(host.instances[0])
    row = _rows(result)['motd.py']
    assert row['kind'] == 'replaceable' and row['replacement'] == 'motd.py'
    assert row['from_catalog'] is True and row['originally_checked'] is True
    assert 'motd.py' in result['replacements']
    assert result['checked_plugins'] == []


def test_operator_pool_plugin_identical_in_the_target_pool_is_auto_accepted(env):
    _write(env.operator_pool / 'minqlx' / 'poolmine.py', COMPATIBLE_ANYWHERE)
    _write(env.operator_pool / 'minqlxtended' / 'poolmine.py', COMPATIBLE_ANYWHERE)
    host = _host(env, [dict(qlx_plugins='poolmine')])
    result = classify_instance(host.instances[0])
    assert result['stripped'] == []
    assert result['auto_accepted'] == ['poolmine.py']
    assert result['checked_plugins'] == ['poolmine.py']


def test_different_target_pool_version_is_replaceable_with_its_text(env):
    _write(env.operator_pool / 'minqlx' / 'poolmine.py', COMPATIBLE_ANYWHERE)
    _write(env.operator_pool / 'minqlxtended' / 'poolmine.py', COMPATIBLE_ANYWHERE + '# xt\n')
    host = _host(env, [dict(qlx_plugins='poolmine')])
    result = classify_instance(host.instances[0])
    assert _rows(result)['poolmine.py']['kind'] == 'replaceable'
    assert result['replacements']['poolmine.py'] == COMPATIBLE_ANYWHERE + '# xt\n'


def test_local_scripts_copy_wins_over_the_pool(env):
    _write(env.operator_pool / 'minqlx' / 'balance.py', 'import minqlx\n# pool\n')
    host = _host(env, [dict(scripts={'balance.py': _stock('balance.py')}, qlx_plugins='balance')])
    result = classify_instance(host.instances[0])
    assert result['stripped'] == [] and result['auto_accepted'] == ['balance.py']


def test_unchecked_pool_plugins_are_not_reported(env):
    _write(env.operator_pool / 'minqlx' / 'poolmine.py', COMPATIBLE_ANYWHERE)
    host = _host(env, [dict(qlx_plugins='')])
    result = classify_instance(host.instances[0])
    assert result['stripped'] == [] and result['auto_accepted'] == []


def test_capture_records_source_pool_digests(env):
    _write(env.operator_pool / 'minqlx' / 'poolmine.py', COMPATIBLE_ANYWHERE)
    host = _host(env, [dict(qlx_plugins='poolmine, autokick')])
    captured = capture_upgrade_inputs(host)['instances'][0]
    pool = captured['source_pool_plugins']
    assert set(pool) == {'poolmine.py', 'autokick.py'}
    assert pool['poolmine.py']['tier'] == 'operator' and pool['autokick.py']['tier'] == 'builtin'
    assert len(pool['poolmine.py']['sha256']) == 64
    assert COMPATIBLE_ANYWHERE not in json.dumps(captured)


def test_fingerprint_changes_when_an_enabled_source_pool_plugin_changes(env):
    _write(env.operator_pool / 'minqlx' / 'poolmine.py', COMPATIBLE_ANYWHERE)
    host = _host(env, [dict(qlx_plugins='poolmine')])
    before = _fp(host)
    _write(env.operator_pool / 'minqlx' / 'poolmine.py', COMPATIBLE_ANYWHERE + '# v2\n')
    assert _fp(host) != before


def test_fingerprint_ignores_source_pool_plugins_nobody_enabled(env):
    host = _host(env, [dict(qlx_plugins='balance', scripts={'balance.py': _stock('balance.py')})])
    before = _fp(host)
    _write(env.operator_pool / 'minqlx' / 'unrelated.py', COMPATIBLE_ANYWHERE)
    assert _fp(host) == before
