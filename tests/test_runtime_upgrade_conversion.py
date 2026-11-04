"""Converted instance state for a host runtime upgrade, built only from the
operation's immutable materialized inputs."""
import json
import os
from types import SimpleNamespace

import pytest

from ui import db, plugin_pool, preset_compat, runtime_upgrade
from ui.models import Host, HostStatus, InstanceStatus, QLInstance
from ui.runtime_upgrade import capture_upgrade_inputs, materialize_upgrade_inputs
from ui.runtime_upgrade_conversion import (
    AnswersInvalid,
    build_converted_tree,
    build_target_system_hooks,
    conversion_paths,
    converted_ld_preload_hooks,
    discard_conversion_leftovers,
    excluded_hooks,
    install_converted_tree,
    parse_answers,
    same_tree,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REAL_BUILTIN_PRESETS = os.path.join(REPO_ROOT, 'configs', 'presets', '_builtin')
STOCK = os.path.join(REAL_BUILTIN_PRESETS, 'default', 'scripts')
TARGET = os.path.join(REAL_BUILTIN_PRESETS, 'default-minqlxtended', 'scripts')
CUSTOM = 'import minqlx\n\nclass mine(minqlx.Plugin):\n    pass\n'


def _read(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    configs = tmp_path / 'configs'
    pool = tmp_path / 'shared-plugins'
    configs.mkdir()
    pool.mkdir()
    monkeypatch.setattr(runtime_upgrade, 'CONFIGS_BASE', str(configs))
    monkeypatch.setattr(plugin_pool, 'OPERATOR_POOL_BASE', str(pool))
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', REAL_BUILTIN_PRESETS)
    with app.app_context():
        yield SimpleNamespace(tmp=tmp_path, configs=configs)


def _host(env, qlx_plugins='balance, ban, mine', hooks='force_rate.so,my.so'):
    host = Host(name='ch', provider='vultr', status=HostStatus.ACTIVE, runtime='minqlx',
                os_type='ubuntu', os_version='24.04')
    db.session.add(host)
    db.session.commit()
    inst = QLInstance(host_id=host.id, name='ci', port=27960, hostname='x', qlx_plugins=qlx_plugins,
                      ld_preload_hooks=hooks, zmq_rcon_port=28888, zmq_rcon_password='r',
                      zmq_stats_port=29999, zmq_stats_password='s', status=InstanceStatus.RUNNING)
    db.session.add(inst)
    db.session.commit()
    root = env.configs / host.name / str(inst.id)
    (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'balance.py').write_text(_read(os.path.join(STOCK, 'balance.py')))
    (root / 'scripts' / 'ban.py').write_text(_read(os.path.join(STOCK, 'ban.py')) + '\n# mine\n')
    (root / 'scripts' / 'mine.py').write_text(CUSTOM)
    (root / 'server.cfg').write_text('set sv_hostname "x"\n')
    (root / 'user-hooks').mkdir()
    (root / 'user-hooks' / 'my.so').write_bytes(b'\x7fELF')
    db.session.refresh(host)
    return host, inst


def _materialized(env, host):
    inputs = capture_upgrade_inputs(host)
    inputs_dir = str(env.tmp / 'inputs')
    materialize_upgrade_inputs(host, inputs, inputs_dir)
    return json.loads(json.dumps(inputs)), inputs_dir


def test_ticked_replacement_is_converted_and_keeps_its_selection(env):
    host, inst = _host(env)
    inputs, inputs_dir = _materialized(env, host)
    captured = inputs['instances'][0]
    assert captured['classification']['auto_accepted'] == ['balance.py']
    dest = str(env.tmp / 'converted')

    fields = build_converted_tree(inputs_dir, captured, ['ban.py'], excluded_hooks(inputs), dest)

    scripts = os.path.join(dest, 'scripts')
    assert sorted(os.listdir(scripts)) == ['balance.py', 'ban.py']
    assert _read(os.path.join(scripts, 'balance.py')) == _read(os.path.join(TARGET, 'balance.py'))
    assert _read(os.path.join(scripts, 'ban.py')) == _read(os.path.join(TARGET, 'ban.py'))
    assert _read(os.path.join(dest, 'server.cfg')) == 'set sv_hostname "x"\n'
    assert os.path.isfile(os.path.join(dest, 'user-hooks', 'my.so'))
    assert fields == {'qlx_plugins': 'balance, ban', 'ld_preload_hooks': 'my.so'}
    # The live tree is untouched.
    assert sorted(os.listdir(env.configs / host.name / str(inst.id) / 'scripts')) == \
        ['balance.py', 'ban.py', 'mine.py']


def test_unticked_replacement_drops_the_plugin(env):
    host, _inst = _host(env)
    inputs, inputs_dir = _materialized(env, host)
    dest = str(env.tmp / 'converted')
    fields = build_converted_tree(inputs_dir, inputs['instances'][0], [], excluded_hooks(inputs), dest)
    assert sorted(os.listdir(os.path.join(dest, 'scripts'))) == ['balance.py']
    assert fields['qlx_plugins'] == 'balance'


def test_null_selection_is_preserved(env):
    host, _inst = _host(env, qlx_plugins=None, hooks=None)
    inputs, inputs_dir = _materialized(env, host)
    fields = build_converted_tree(inputs_dir, inputs['instances'][0], [], excluded_hooks(inputs),
                                  str(env.tmp / 'converted'))
    assert fields == {'qlx_plugins': None, 'ld_preload_hooks': None}


def test_conversion_reads_materialized_target_not_live_assets(env, monkeypatch, tmp_path):
    host, _inst = _host(env)
    inputs, inputs_dir = _materialized(env, host)
    # Live shipped presets vanish after the capture: the conversion is unaffected.
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', str(tmp_path / 'nowhere'))
    dest = str(env.tmp / 'converted')
    build_converted_tree(inputs_dir, inputs['instances'][0], ['ban.py'], excluded_hooks(inputs), dest)
    assert _read(os.path.join(dest, 'scripts', 'ban.py')) == _read(os.path.join(TARGET, 'ban.py'))


def test_excluded_hooks_are_removed_only_from_converted_fields():
    assert converted_ld_preload_hooks('force_rate.so', {'force_rate.so'}) is None
    assert converted_ld_preload_hooks('a.so, force_rate.so,b.so', {'force_rate.so'}) == 'a.so,b.so'
    assert converted_ld_preload_hooks('a.so', {'force_rate.so'}) == 'a.so'
    assert converted_ld_preload_hooks(None, {'force_rate.so'}) is None


def test_target_system_hooks_skip_excluded(env, tmp_path):
    inputs_dir = tmp_path / 'in'
    (inputs_dir / 'system_hooks').mkdir(parents=True)
    (inputs_dir / 'system_hooks' / 'force_rate.so').write_bytes(b'x')
    (inputs_dir / 'system_hooks' / 'other.so').write_bytes(b'y')
    dest = build_target_system_hooks(str(inputs_dir), {'force_rate.so'}, str(tmp_path / 'out'))
    assert os.listdir(dest) == ['other.so']


def test_answers_are_validated_against_the_capture(env):
    host, inst = _host(env)
    inputs, _ = _materialized(env, host)
    assert parse_answers(inputs, None) == {inst.id: []}
    assert parse_answers(inputs, json.dumps({str(inst.id): ['ban.py', 'ban.py']})) == {inst.id: ['ban.py']}
    with pytest.raises(AnswersInvalid):
        parse_answers(inputs, json.dumps({'999': []}))
    # combineAcceptedPaths sends auto_accepted + ticked: the auto part is dropped.
    assert parse_answers(inputs, json.dumps({str(inst.id): ['balance.py', 'ban.py']})) == {inst.id: ['ban.py']}
    assert parse_answers(inputs, json.dumps({str(inst.id): ['balance.py']})) == {inst.id: []}
    with pytest.raises(AnswersInvalid):
        parse_answers(inputs, json.dumps({str(inst.id): ['motd.py']}))  # neither offered nor auto
    with pytest.raises(AnswersInvalid):
        parse_answers(inputs, json.dumps({str(inst.id): ['mine.py']}))  # no replacement exists
    with pytest.raises(AnswersInvalid):
        parse_answers(inputs, '[1]')


def _tree(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_install_converted_tree_swaps_and_is_idempotent(tmp_path):
    live, converted = tmp_path / 'host' / '5', tmp_path / 'conv'
    _tree(live, {'server.cfg': 'old', 'scripts/a.py': 'a'})
    _tree(converted, {'server.cfg': 'new'})
    install_converted_tree(str(live), str(converted), '5-op')
    assert same_tree(str(live), str(converted))
    staged, original = conversion_paths(str(live), '5-op')
    assert (tmp_path / 'host' / '.upgrade-original-5-op' / 'scripts' / 'a.py').read_text() == 'a'
    install_converted_tree(str(live), str(converted), '5-op')  # replay: no-op
    assert same_tree(str(live), str(converted))
    discard_conversion_leftovers(str(live), '5-op')
    assert not os.path.exists(staged) and not os.path.exists(original)


def test_install_converted_tree_finishes_after_crash_between_renames(tmp_path):
    live, converted = tmp_path / 'host' / '5', tmp_path / 'conv'
    _tree(live, {'server.cfg': 'old'})
    _tree(converted, {'server.cfg': 'new'})
    _staged, original = conversion_paths(str(live), 'x')
    os.rename(live, original)  # died after moving live aside
    install_converted_tree(str(live), str(converted), 'x')
    assert same_tree(str(live), str(converted))
