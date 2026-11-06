"""Pre-upgrade snapshot publication, fallback presets and per-instance restore.

Everything lives under tmp_path: instance configs, the operator plugin pool,
user presets and the snapshot root. The shipped builtin presets and ql-assets
are read in place; nothing under the real configs/ or data/ is touched.
"""
import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from ui import db, plugin_pool, preset_compat, runtime_upgrade
from ui import runtime_upgrade_presets as snap_presets
from ui import runtime_upgrade_snapshot as snap
from ui.models import ConfigPreset, Host, HostStatus, InstanceStatus, QLInstance
from ui.models_runtime_upgrade import HostRuntimeUpgradeOperation
from ui.routes import preset_api_routes
from ui.runtime_upgrade import UpgradeInputsChanged, capture_upgrade_inputs, classification_fingerprint
from ui.runtime_upgrade_snapshot import (
    PRESET_PREFIX,
    prepare_upgrade_snapshot,
    restore_instance,

)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REAL_BUILTIN_PRESETS = os.path.join(REPO_ROOT, 'configs', 'presets', '_builtin')
ELF = b'\x7fELF\x02\x01\x01\x00' + bytes(range(256)) * 4


class Crash(BaseException):
    """Simulated worker death: not an Exception, so nothing catches it."""


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    configs = tmp_path / 'configs'
    presets = tmp_path / 'presets'
    upgrades = tmp_path / 'runtime-upgrades'
    operator_pool = tmp_path / 'shared-plugins'
    for path in (configs, presets, operator_pool):
        path.mkdir()
    monkeypatch.setattr(runtime_upgrade, 'CONFIGS_BASE', str(configs))
    monkeypatch.setattr(plugin_pool, 'OPERATOR_POOL_BASE', str(operator_pool))
    monkeypatch.setattr(preset_compat, 'BUILTIN_PRESETS_DIR', REAL_BUILTIN_PRESETS)
    monkeypatch.setattr(preset_api_routes, 'PRESETS_DIR', str(presets))
    app.config['RUNTIME_UPGRADES_DIR'] = str(upgrades)
    with app.app_context():
        yield SimpleNamespace(tmp=tmp_path, configs=configs, presets=presets, upgrades=upgrades)


def _write(path, content, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding='utf-8')
    if mode is not None:
        os.chmod(path, mode)


INSTANCE_FILES = {
    'server.cfg': 'set sv_hostname "x"\n',
    'mappool.txt': 'campgrounds|ffa\n',
    'access.txt': '76561198000000001|5\n76561198000000002|admin\n',
    'workshop.txt': '',
    'cfgs/nested/extra.cfg': 'set g_x 1\n',
    'factories/my.factories': '[{"id": "ffa"}]\n',
    'scripts/custom.py': 'import minqlx\n',
    'scripts/sub/helper.py': 'X = 1\n',
    'scripts/custom.pyc': b'\x00\x01junk',
    'scripts/blob.bin': b'\xff\xfe\x00not utf8',
}


def _make_host(env, name='h1', instances=2):
    host = Host(name=name, provider='vultr', status=HostStatus.ACTIVE, runtime='minqlx',
                os_type='ubuntu', os_version='24.04')
    db.session.add(host)
    db.session.commit()
    for index in range(instances):
        inst = QLInstance(
            host_id=host.id, name=f'{name[:40]}-inst{index}', port=27960 + index,
            hostname=f'Server {index}', lan_rate_enabled=bool(index),
            config='{"server.cfg": "x"}',
            qlx_plugins=None if index == 0 else 'custom',
            ld_preload_hooks='force_rate.so' if index else None,
            zmq_rcon_port=28888 + index, zmq_rcon_password='rcon-secret',
            zmq_stats_port=29999 + index, zmq_stats_password='stats-secret',
            status=InstanceStatus.RUNNING if index == 0 else InstanceStatus.STOPPED,
        )
        db.session.add(inst)
        db.session.commit()
        root = env.configs / host.name / str(inst.id)
        for rel, content in INSTANCE_FILES.items():
            _write(root / rel, content)
        _write(root / 'user-hooks' / 'force_rate.so', ELF, mode=0o755)
        os.chmod(root / 'server.cfg', 0o640)
        (root / 'empty-folder').mkdir()
        os.utime(root / 'scripts' / 'custom.py', ns=(1_700_000_000_000_000_000,) * 2)
    db.session.refresh(host)
    return host


def _operation(host, inputs):
    op = HostRuntimeUpgradeOperation(
        host_id=host.id, state='preparing', fingerprint=classification_fingerprint(inputs),
        inputs_json=json.dumps(inputs), original_runtime='minqlx',
        original_host_status='active')
    db.session.add(op)
    db.session.commit()
    return op


def _prepared(env, **kwargs):
    host = _make_host(env, **kwargs)
    inputs = capture_upgrade_inputs(host)
    op = _operation(host, inputs)
    path = prepare_upgrade_snapshot(host, op.id, inputs)
    return host, op, path


def _inventory(root):
    """rel -> (bytes, mode) for files; rel -> mode for directories."""
    files, dirs = {}, {}
    for current, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(current, root).replace(os.sep, '/')
        dirs[rel_dir] = stat.S_IMODE(os.stat(current).st_mode)
        for filename in filenames:
            full = os.path.join(current, filename)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            with open(full, 'rb') as handle:
                files[rel] = (handle.read(), stat.S_IMODE(os.stat(full).st_mode))
    return files, dirs


def _live(env, host, inst):
    return env.configs / host.name / str(inst.id)


def _siblings(env, host):
    return sorted(name for name in os.listdir(env.configs / host.name) if name.startswith('.'))


def _mutate(root):
    (root / 'server.cfg').write_text('converted\n')
    os.chmod(root / 'server.cfg', 0o600)
    (root / 'scripts' / 'sub' / 'helper.py').unlink()
    _write(root / 'scripts' / 'new_target.py', 'import minqlxtended\n')
    (root / 'empty-folder').rmdir()


# --- prepare -----------------------------------------------------------------

def test_prepare_publishes_complete_verified_snapshot(env):
    host, op, path = _prepared(env)
    assert path == os.path.join(str(env.upgrades), str(host.id), op.id)
    assert not os.path.exists(path + '.staging')

    db.session.refresh(op)
    assert op.snapshot_complete is True
    assert op.snapshot_path == path

    with open(os.path.join(path, 'manifest.json')) as handle:
        manifest = json.load(handle)
    assert manifest['complete'] is True
    assert manifest['operation_id'] == op.id
    assert manifest['host_id'] == host.id
    assert manifest['original_runtime'] == 'minqlx'
    assert len(manifest['presets']) == 2

    for inst in host.instances:
        live_files, live_dirs = _inventory(_live(env, host, inst))
        snap_files, snap_dirs = _inventory(os.path.join(path, 'inputs', 'instances', str(inst.id)))
        assert snap_files == live_files  # bytes and modes, including force_rate.so
        assert snap_dirs == live_dirs    # empty folders survive
        assert snap_files['user-hooks/force_rate.so'] == (ELF, 0o755)
        assert snap_files['server.cfg'][1] == 0o640
        copied = os.path.join(path, 'inputs', 'instances', str(inst.id), 'scripts', 'custom.py')
        assert os.stat(copied).st_mtime_ns == 1_700_000_000_000_000_000


def test_snapshot_directories_are_private(env, monkeypatch):
    """instance.json holds plaintext ZMQ passwords: the staging and published
    operation directories are 0700 whatever the process umask."""
    old_umask = os.umask(0o022)
    try:
        host = _make_host(env)
        inputs = capture_upgrade_inputs(host)
        op = _operation(host, inputs)
        seen = {}
        real_rename = snap._rename

        def rename(src, dst):
            seen['staging'] = stat.S_IMODE(os.stat(src).st_mode)
            return real_rename(src, dst)

        monkeypatch.setattr(snap, '_rename', rename)
        path = prepare_upgrade_snapshot(host, op.id, inputs)
    finally:
        os.umask(old_umask)
    assert seen['staging'] == 0o700
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o700


def test_instance_metadata_records_original_db_fields(env):
    host, _op, path = _prepared(env)
    first, second = sorted(host.instances, key=lambda inst: inst.id)
    with open(os.path.join(path, 'instances', str(first.id), 'instance.json')) as handle:
        meta = json.load(handle)
    assert meta['original_runtime'] == 'minqlx'
    assert meta['original_status'] == 'running'
    assert meta['qlx_plugins'] is None
    assert meta['ld_preload_hooks'] is None
    assert meta['lan_rate_enabled'] is False
    assert meta['renderer']['zmq_rcon_password'] == 'rcon-secret'
    assert meta['renderer']['port'] == first.port
    with open(os.path.join(path, 'instances', str(second.id), 'instance.json')) as handle:
        meta2 = json.load(handle)
    assert meta2['qlx_plugins'] == 'custom'
    assert meta2['ld_preload_hooks'] == 'force_rate.so'
    assert meta2['lan_rate_enabled'] is True
    assert meta2['original_status'] == 'stopped'


def test_prepare_rejects_bad_operation_id_and_missing_row(env):
    host = _make_host(env, instances=1)
    inputs = capture_upgrade_inputs(host)
    with pytest.raises(ValueError):
        prepare_upgrade_snapshot(host, '../escape', inputs)
    with pytest.raises(LookupError):
        prepare_upgrade_snapshot(host, uuid.uuid4().hex, inputs)
    assert not env.upgrades.exists() or not any(env.upgrades.rglob('*.json'))


def test_prepare_discards_orphan_publication_from_crashed_attempt(env):
    host = _make_host(env, instances=1)
    inputs = capture_upgrade_inputs(host)
    op = _operation(host, inputs)
    orphan = env.upgrades / str(host.id) / op.id
    _write(orphan / 'manifest.json', '{"complete": true}')
    _write(env.upgrades / str(host.id) / f'{op.id}.staging' / 'junk', 'x')
    path = prepare_upgrade_snapshot(host, op.id, inputs)
    with open(os.path.join(path, 'manifest.json')) as handle:
        assert json.load(handle)['operation_id'] == op.id
    assert not os.path.exists(path + '.staging')


def test_completed_snapshot_is_never_discarded_by_a_repeat_prepare(env):
    host, op, path = _prepared(env, instances=1)
    inputs = json.loads(op.inputs_json)
    assert prepare_upgrade_snapshot(host, op.id, inputs) == path  # idempotent

    shutil.rmtree(path)
    with pytest.raises(snap.SnapshotInvalid):
        prepare_upgrade_snapshot(host, op.id, inputs)
    names = [row.name for row in ConfigPreset.query.all()]
    assert len(names) == 1
    assert (env.presets / names[0]).is_dir()


# --- fallback presets ----------------------------------------------------------

def test_snapshot_presets_hold_instance_contents(env):
    host, op, _path = _prepared(env)
    first, second = sorted(host.instances, key=lambda inst: inst.id)
    rows = {row.name: row for row in ConfigPreset.query.all()}
    assert len(rows) == 2
    name1 = f'{PRESET_PREFIX}{host.name}-{first.id}-{op.id}'
    name2 = f'{PRESET_PREFIX}{host.name}-{second.id}-{op.id}'
    assert set(rows) == {name1, name2}
    assert all(row.runtime == 'minqlx' and not row.is_builtin for row in rows.values())

    p1 = env.presets / name1
    assert rows[name1].path == str(p1)
    assert (p1 / 'server.cfg').read_text() == INSTANCE_FILES['server.cfg']
    assert (p1 / 'cfgs' / 'nested' / 'extra.cfg').read_text() == INSTANCE_FILES['cfgs/nested/extra.cfg']
    assert (p1 / 'empty-folder').is_dir()
    # The existing preset writer strips numeric admin lines from access.txt.
    assert (p1 / 'access.txt').read_text() == '76561198000000002|admin\n'
    assert (p1 / 'factories' / 'my.factories').read_text() == INSTANCE_FILES['factories/my.factories']
    assert json.loads((p1 / 'checked_factories.json').read_text()) == ['my.factories']
    assert (p1 / 'scripts' / 'sub' / 'helper.py').read_text() == 'X = 1\n'
    assert (p1 / 'scripts' / 'blob.bin').read_bytes() == INSTANCE_FILES['scripts/blob.bin']
    assert not (p1 / 'scripts' / 'custom.pyc').exists()  # generated cruft skipped
    assert (p1 / 'user-hooks' / 'force_rate.so').read_bytes() == ELF
    assert json.loads((p1 / 'lan_rate_enabled.json').read_text()) is False
    # NULL plugin/hook selections are "never recorded", not an empty list.
    assert not (p1 / 'checked_plugins.json').exists()
    assert not (p1 / 'enabled_hooks.json').exists()

    p2 = env.presets / name2
    assert json.loads((p2 / 'checked_plugins.json').read_text()) == ['custom.py']
    assert json.loads((p2 / 'enabled_hooks.json').read_text()) == ['force_rate.so']
    assert json.loads((p2 / 'lan_rate_enabled.json').read_text()) is True


def test_preset_names_fit_with_max_length_host_and_repeat_attempts(env):
    host = _make_host(env, name='h' + 'x' * 99, instances=2)
    inputs = capture_upgrade_inputs(host)
    names = []
    for _attempt in range(2):
        op = _operation(host, inputs)
        path = prepare_upgrade_snapshot(host, op.id, inputs)
        with open(os.path.join(path, 'manifest.json')) as handle:
            names += json.load(handle)['presets']
        op.state = 'failed_preparation'
        db.session.commit()
    assert len(names) == 4 and len(set(names)) == 4
    for name in names:
        assert len(name) <= 100
        assert name.startswith(PRESET_PREFIX)
        assert re.fullmatch(r'[A-Za-z0-9_-]+', name)
        assert re.search(r'-\d+-[0-9a-f]{32}$', name)
    assert {row.name for row in ConfigPreset.query.all()} == set(names)


def test_preset_host_fragment_is_the_only_part_truncated(env):
    name = snap.snapshot_preset_name('h' * 100, 123456, 'a' * 32)
    assert len(name) == 100
    assert name.endswith('-123456-' + 'a' * 32)
    assert name.startswith(PRESET_PREFIX + 'h')


# --- preparation failures are preparation-only ------------------------------------

def _assert_untouched(env, host, before, op):
    for inst in host.instances:
        assert _inventory(_live(env, host, inst)) == before[inst.id]
    assert _siblings(env, host) == []
    host_root = env.upgrades / str(host.id)
    assert not host_root.exists() or os.listdir(host_root) == []
    assert ConfigPreset.query.count() == 0
    assert os.listdir(env.presets) == []
    db.session.refresh(op)
    assert op.snapshot_complete is False
    assert op.snapshot_path is None


def _fail_metadata(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(snap, '_write_instance_metadata', boom)


def _fail_preset_row(monkeypatch):
    calls = []
    real = snap_presets._create_preset_row

    def second_fails(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError('db locked')
        return real(**kwargs)
    monkeypatch.setattr(snap_presets, '_create_preset_row', second_fails)


def _swallowed_writer_failure(monkeypatch):
    # The real writers log and swallow errors; validation must still notice.
    monkeypatch.setattr(preset_api_routes, '_write_preset_lan_rate_enabled',
                        lambda *_args, **_kwargs: None)


def _fail_publish_rename(monkeypatch):
    real = snap._rename

    def boom(src, dst):
        if src.endswith('.staging'):
            raise OSError('rename failed')
        return real(src, dst)
    monkeypatch.setattr(snap, '_rename', boom)


def _fail_published_verification(monkeypatch):
    real = snap._verify_published

    def tamper(path, *args, **kwargs):
        _write(Path(path) / 'inputs' / 'instances' /
               os.listdir(os.path.join(path, 'inputs', 'instances'))[0] / 'server.cfg', 'evil')
        return real(path, *args, **kwargs)
    monkeypatch.setattr(snap, '_verify_published', tamper)


@pytest.mark.parametrize('inject, raised, message', [
    (_fail_metadata, OSError, 'disk full'),
    (_fail_preset_row, RuntimeError, 'db locked'),
    (_swallowed_writer_failure, snap_presets.SnapshotPresetError, 'lan_rate_enabled differs'),
    (_fail_publish_rename, OSError, 'rename failed'),
    (_fail_published_verification, snap.SnapshotInvalid, 'server.cfg changed'),
])
def test_preparation_failure_cleans_only_operation_owned_artifacts(
        env, monkeypatch, inject, raised, message):
    host = _make_host(env)
    inputs = capture_upgrade_inputs(host)
    op = _operation(host, inputs)
    before = {inst.id: _inventory(_live(env, host, inst)) for inst in host.instances}
    inject(monkeypatch)
    with pytest.raises(raised, match=message):
        prepare_upgrade_snapshot(host, op.id, inputs)
    _assert_untouched(env, host, before, op)


def test_copy_failure_on_drift_cleans_up(env):
    host = _make_host(env)
    inputs = capture_upgrade_inputs(host)
    op = _operation(host, inputs)
    inst = host.instances[0]
    (_live(env, host, inst) / 'mappool.txt').write_text('edited after confirm\n')
    before = {i.id: _inventory(_live(env, host, i)) for i in host.instances}
    with pytest.raises(UpgradeInputsChanged):
        prepare_upgrade_snapshot(host, op.id, inputs)
    _assert_untouched(env, host, before, op)


def test_unrelated_presets_survive_preparation_failure(env, monkeypatch):
    host = _make_host(env, instances=1)
    inputs = capture_upgrade_inputs(host)
    op = _operation(host, inputs)
    other = env.presets / 'mine'
    other.mkdir()
    db.session.add(ConfigPreset(name='mine', path=str(other), runtime='minqlx'))
    db.session.commit()
    _fail_publish_rename(monkeypatch)
    with pytest.raises(OSError):
        prepare_upgrade_snapshot(host, op.id, inputs)
    assert [row.name for row in ConfigPreset.query.all()] == ['mine']
    assert other.is_dir()


# --- restore -----------------------------------------------------------------

def _restore_fields(inst):
    return (inst.qlx_plugins, inst.ld_preload_hooks, inst.lan_rate_enabled, inst.hostname,
            inst.config, inst.zmq_rcon_password, inst.cpu_affinity, inst.redis_db)


def test_restore_round_trips_bytes_metadata_and_db_fields(env):
    host, _op, path = _prepared(env)
    originals = {}
    for inst in host.instances:
        originals[inst.id] = (_inventory(_live(env, host, inst)), _restore_fields(inst), inst.status)
        _mutate(_live(env, host, inst))
        inst.qlx_plugins = ''
        inst.ld_preload_hooks = 'other.so'
        inst.lan_rate_enabled = not inst.lan_rate_enabled
        inst.hostname = 'changed'
        inst.config = '{}'
        inst.zmq_rcon_password = 'new'
        inst.status = InstanceStatus.CONFIGURING
    db.session.commit()

    for inst in host.instances:
        result = restore_instance(inst, path)
        assert result['ok'] is True, result
        assert result['error'] is None
        assert result['instance_id'] == inst.id

    for inst in host.instances:
        db.session.refresh(inst)
        tree, fields, _status = originals[inst.id]
        assert _inventory(_live(env, host, inst)) == tree
        assert _restore_fields(inst) == fields
        # Readiness is never claimed from metadata.
        assert inst.status == InstanceStatus.CONFIGURING
    assert _siblings(env, host) == []
    assert os.path.isfile(os.path.join(path, 'manifest.json'))


def test_restore_status_comes_from_verified_service_state(env):
    host, _op, path = _prepared(env, instances=1)
    inst = host.instances[0]
    inst.status = InstanceStatus.CONFIGURING
    db.session.commit()
    result = restore_instance(inst, path, service_state=lambda _inst: InstanceStatus.STOPPED)
    assert result['ok'] is True
    db.session.refresh(inst)
    assert inst.status == InstanceStatus.STOPPED  # original was RUNNING; verifier wins


def test_restore_rejects_incomplete_or_tampered_snapshot(env):
    host, _op, path = _prepared(env, instances=1)
    inst = host.instances[0]
    _mutate(_live(env, host, inst))
    mutated = _inventory(_live(env, host, inst))

    _write(Path(path) / 'inputs' / 'instances' / str(inst.id) / 'server.cfg',
           'tampered')
    result = restore_instance(inst, path)
    assert result['ok'] is False
    assert result['phase'] == 'stage'
    assert 'server.cfg' in result['error']
    assert _inventory(_live(env, host, inst)) == mutated

    manifest_path = os.path.join(path, 'manifest.json')
    with open(manifest_path) as handle:
        manifest = json.load(handle)
    manifest['complete'] = False
    with open(manifest_path, 'w') as handle:
        json.dump(manifest, handle)
    result = restore_instance(inst, path)
    assert result == {'instance_id': inst.id, 'ok': False, 'phase': 'validate',
                      'error': result['error'], 'status_verified': False}
    assert _inventory(_live(env, host, inst)) == mutated


def test_restore_copy_failure_isolated_to_one_instance(env):
    host, _op, path = _prepared(env)
    first, second = sorted(host.instances, key=lambda inst: inst.id)
    for inst in (first, second):
        _mutate(_live(env, host, inst))
    mutated_first = _inventory(_live(env, host, first))
    expected_second = _inventory(os.path.join(path, 'inputs', 'instances', str(second.id)))
    (Path(path) / 'inputs' / 'instances' / str(first.id) /
     'scripts' / 'custom.py').unlink()

    results = [restore_instance(inst, path) for inst in (first, second)]
    assert results[0]['ok'] is False and results[0]['phase'] == 'stage'
    assert results[1]['ok'] is True
    assert _inventory(_live(env, host, first)) == mutated_first
    assert _inventory(_live(env, host, second)) == expected_second


def test_restore_swap_failure_keeps_live_data_and_later_instances_restore(env, monkeypatch):
    host, _op, path = _prepared(env)
    first, second = sorted(host.instances, key=lambda inst: inst.id)
    for inst in (first, second):
        _mutate(_live(env, host, inst))
    mutated_first = _inventory(_live(env, host, first))
    live_first = str(_live(env, host, first))
    real = snap._rename

    def staged_into_place_fails(src, dst):
        if dst == live_first and '.upgrade-restore-' in src:
            raise OSError('EIO')
        return real(src, dst)
    monkeypatch.setattr(snap, '_rename', staged_into_place_fails)

    results = [restore_instance(inst, path) for inst in (first, second)]
    assert results[0]['ok'] is False and results[0]['phase'] == 'swap'
    assert 'EIO' in results[0]['error']
    assert results[1]['ok'] is True
    assert _inventory(live_first) == mutated_first  # undone: live data back in place
    assert _inventory(_live(env, host, second)) == _inventory(
        os.path.join(path, 'inputs', 'instances', str(second.id)))
    assert os.path.isfile(os.path.join(path, 'manifest.json'))

    monkeypatch.setattr(snap, '_rename', real)
    assert restore_instance(first, path)['ok'] is True


def _crash_on_rename(monkeypatch, nth):
    real = snap._rename
    calls = []

    def crash(src, dst):
        calls.append((src, dst))
        if len(calls) == nth:
            raise Crash()
        return real(src, dst)
    monkeypatch.setattr(snap, '_rename', crash)
    return real


@pytest.mark.parametrize('crash_at', ['before_first_rename', 'between_renames', 'after_swap'])
def test_recovery_completes_an_interrupted_swap(env, monkeypatch, crash_at):
    host, _op, path = _prepared(env, instances=1)
    inst = host.instances[0]
    expected = _inventory(os.path.join(path, 'inputs', 'instances', str(inst.id)))
    _mutate(_live(env, host, inst))
    inst.qlx_plugins = 'changed'
    db.session.commit()

    if crash_at == 'before_first_rename':
        real = _crash_on_rename(monkeypatch, 1)
    elif crash_at == 'between_renames':
        real = _crash_on_rename(monkeypatch, 2)
    else:
        real = snap._rename
        real_intent = snap._write_intent

        def crash_after_swap(intent_path, intent):
            if intent.get('state') == 'swapped':
                raise Crash()
            return real_intent(intent_path, intent)
        monkeypatch.setattr(snap, '_write_intent', crash_after_swap)

    with pytest.raises(Crash):
        restore_instance(inst, path)
    if crash_at == 'between_renames':
        assert not _live(env, host, inst).exists()  # the window recovery must close

    monkeypatch.setattr(snap, '_rename', real)
    if crash_at == 'after_swap':
        monkeypatch.setattr(snap, '_write_intent', real_intent)
    db.session.rollback()
    result = restore_instance(inst, path)
    assert result['ok'] is True, result
    assert _inventory(_live(env, host, inst)) == expected
    db.session.refresh(inst)
    assert inst.qlx_plugins is None
    assert _siblings(env, host) == []


def test_recovery_restages_a_damaged_staged_copy(env, monkeypatch):
    host, op, path = _prepared(env, instances=1)
    inst = host.instances[0]
    expected = _inventory(os.path.join(path, 'inputs', 'instances', str(inst.id)))
    _mutate(_live(env, host, inst))
    mutated = _inventory(_live(env, host, inst))

    real = _crash_on_rename(monkeypatch, 1)  # before_first_rename
    with pytest.raises(Crash):
        restore_instance(inst, path)
    monkeypatch.setattr(snap, '_rename', real)
    db.session.rollback()

    staged = env.configs / host.name / f'.upgrade-restore-{inst.id}-{op.id}'
    assert staged.is_dir()
    (staged / 'server.cfg').write_text('corrupted')
    (staged / 'scripts' / 'custom.py').unlink()
    assert _inventory(_live(env, host, inst)) == mutated  # live untouched so far

    result = restore_instance(inst, path)
    assert result['ok'] is True, result
    assert _inventory(_live(env, host, inst)) == expected
    assert _siblings(env, host) == []


# --- Local review #2: a restore under an operation commits through its fence ---------

@pytest.mark.parametrize('verify', [False, True])
def test_restore_db_write_is_fenced_after_a_takeover(env, verify):
    from ui.task_logic.host_runtime_upgrade_state import Execution, StaleExecution, claim_operation

    host, op, path = _prepared(env, instances=1)
    inst = host.instances[0]
    inst.hostname = 'changed'
    inst.status = InstanceStatus.CONFIGURING
    db.session.commit()
    token = claim_operation(op.id, 'job-1')
    stale = Execution(op.id, token, 'job-1', None)
    assert claim_operation(op.id, 'job-2') == token + 1

    calls = []
    commit = stale.commit
    if verify:
        # The DB-field commit is still ours; the takeover lands before the status write.
        def commit():
            calls.append('commit')
            if len(calls) == 2:
                return stale.commit()
            return db.session.commit()
    with pytest.raises(StaleExecution):
        restore_instance(inst, path, commit=commit,
                         service_state=(lambda _inst: InstanceStatus.STOPPED) if verify else None)
    db.session.expire_all()
    inst = db.session.get(type(inst), inst.id)
    assert inst.status == InstanceStatus.CONFIGURING
    if not verify:
        assert inst.hostname == 'changed'
