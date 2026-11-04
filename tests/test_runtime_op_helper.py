"""ansible/files/qlsm_runtime_op.py: the remote helper behind the runtime
upgrade playbooks. Exercised here on local temp directories only."""
import importlib.util
import json
import os
import signal
import time

import pytest

HELPER = os.path.join(os.path.dirname(__file__), '..', 'ansible', 'files', 'qlsm_runtime_op.py')
OP_A = 'a' * 32
OP_B = 'b' * 32


@pytest.fixture(scope='module')
def helper():
    spec = importlib.util.spec_from_file_location('qlsm_runtime_op', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- fencing rules ----------------------------------------------------------

def test_first_operation_may_proceed(helper):
    assert helper.token_decision(None, OP_A, 1, set()) is None


def test_same_operation_rejects_a_lower_token(helper):
    record = {'operation_id': OP_A, 'fencing_token': 5, 'state': 'active'}
    assert 'stale fencing token 4' in helper.token_decision(record, OP_A, 4, set())
    assert helper.token_decision(record, OP_A, 5, set()) is None
    assert helper.token_decision(record, OP_A, 6, set()) is None


def test_other_nonterminal_operation_blocks(helper):
    record = {'operation_id': OP_A, 'fencing_token': 1, 'state': 'active'}
    assert OP_A in helper.token_decision(record, OP_B, 1, set())


def test_terminal_or_finalized_operation_can_be_taken_over(helper):
    record = {'operation_id': OP_A, 'fencing_token': 9, 'state': 'active'}
    assert helper.token_decision(record, OP_B, 1, {OP_A}) is None
    assert helper.token_decision(dict(record, state='finalized'), OP_B, 1, set()) is None


def test_finalized_operation_cannot_run_again(helper):
    record = {'operation_id': OP_A, 'fencing_token': 1, 'state': 'finalized'}
    assert 'finalized' in helper.token_decision(record, OP_A, 2, set())


def _run(helper, capsys, *argv):
    rc = helper.main(list(argv))
    return rc, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_acquire_holds_the_lock_until_release(helper, tmp_path, capsys):
    base = str(tmp_path)
    rc, out = _run(helper, capsys, 'acquire', '--base', base, '--operation-id', OP_A,
                   '--fencing-token', '3', '--ttl', '60')
    assert rc == 0 and out['acquired']
    holder = out['holder_pid']
    try:
        # A second play (even of the same operation) cannot run concurrently.
        rc, out = _run(helper, capsys, 'acquire', '--base', base, '--operation-id', OP_A,
                       '--fencing-token', '4')
        assert rc == 3 and 'still running' in out['refused']
    finally:
        rc, out = _run(helper, capsys, 'release', '--base', base, '--operation-id', OP_A,
                       '--fencing-token', '3')
    assert out['released']
    for _ in range(50):
        try:
            os.kill(holder, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    # Stale token now rejected; current token accepted.
    rc, out = _run(helper, capsys, 'acquire', '--base', base, '--operation-id', OP_A,
                   '--fencing-token', '2')
    assert rc == 3 and 'stale fencing token' in out['refused']
    rc, out = _run(helper, capsys, 'acquire', '--base', base, '--operation-id', OP_A,
                   '--fencing-token', '3', '--ttl', '60')
    assert rc == 0
    os.kill(out['holder_pid'], signal.SIGTERM)


def test_finalize_lets_the_next_operation_in(helper, tmp_path, capsys):
    base = str(tmp_path)
    token = os.path.join(base, helper.TOKEN_NAME)
    os.makedirs(base, exist_ok=True)
    with open(token, 'w') as handle:
        json.dump({'operation_id': OP_A, 'fencing_token': 2, 'state': 'active'}, handle)
    rc, out = _run(helper, capsys, 'acquire', '--base', base, '--operation-id', OP_B,
                   '--fencing-token', '1')
    assert rc == 3
    rc, out = _run(helper, capsys, 'finalize', '--base', base, '--operation-id', OP_A,
                   '--fencing-token', '2')
    assert rc == 0 and out['finalized']
    rc, out = _run(helper, capsys, 'acquire', '--base', base, '--operation-id', OP_B,
                   '--fencing-token', '1', '--ttl', '60')
    assert rc == 0
    os.kill(out['holder_pid'], signal.SIGTERM)


# --- apt guard ----------------------------------------------------------------

APT_ADDITIVE = """Reading package lists...
The following NEW packages will be installed:
  python3-venv python3.12-venv
0 upgraded, 2 newly installed, 0 to remove and 3 not upgraded.
Inst python3.12-venv (3.12.3-1ubuntu0.8 Ubuntu:24.04/noble-updates [amd64])
Inst python3-venv (3.12.3-0ubuntu2 Ubuntu:24.04/noble [amd64])
Conf python3.12-venv (3.12.3-1ubuntu0.8 Ubuntu:24.04/noble-updates [amd64])
"""

APT_UPGRADE = """0 upgraded, 1 newly installed, 0 to remove and 3 not upgraded.
Inst libpython3.12-stdlib [3.12.3-1ubuntu0.7] (3.12.3-1ubuntu0.8 Ubuntu:24.04/noble-updates [amd64])
Inst python3-dev (3.12.3-0ubuntu2 Ubuntu:24.04/noble [amd64])
"""

APT_REMOVE = """The following packages will be REMOVED:
  systemd-timesyncd
Remv systemd-timesyncd [255.4-1ubuntu8.18]
Inst chrony (4.5-1ubuntu4.2 Ubuntu:24.04/noble-updates [arm64])
"""


def test_apt_parser_accepts_purely_additive_installs(helper):
    installs, violations = helper.parse_apt_simulation(APT_ADDITIVE)
    assert installs == ['python3.12-venv', 'python3-venv']
    assert violations == []


def test_apt_parser_rejects_upgrading_an_installed_package(helper):
    _installs, violations = helper.parse_apt_simulation(APT_UPGRADE)
    assert violations == ['would change installed libpython3.12-stdlib (3.12.3-1ubuntu0.7)']


def test_apt_parser_rejects_removals(helper):
    _installs, violations = helper.parse_apt_simulation(APT_REMOVE)
    assert violations == ['would remove systemd-timesyncd']


# --- managed files --------------------------------------------------------------

def _tree(root, files):
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(content)


def _read(path):
    with open(path) as handle:
        return handle.read()


@pytest.fixture
def instance(tmp_path):
    tmp_path = tmp_path.resolve()  # macOS: /var is a symlink, and symlinks are refused
    base = tmp_path / 'runtime-ops'
    qlds = tmp_path / 'qlds-27960'
    _tree(str(qlds), {
        'baseq3/server.cfg': 'old cfg\n',
        'baseq3/maps/sentinel.bsp': 'map data\n',
        'minqlx-plugins/balance.py': 'old plugin\n',
        'minqlx.x64.so': 'old engine\n',
        'minqlxtended-plugins/plugin_data.json': '{"owned": "by plugin"}\n',
    })
    ops = base / 'ops' / OP_A / '7'
    stage = ops / 'stage'
    _tree(str(stage / 'tree'), {
        'baseq3/server.cfg': 'new cfg\n',
        'minqlxtended-plugins/balance.py': 'new plugin\n',
    })
    _tree(str(stage), {'qlds@27960.service': 'new unit\n'})
    for root, dirs, _files in os.walk(base):
        os.chmod(root, 0o700)
        for name in dirs:
            os.chmod(os.path.join(root, name), 0o700)
    shared = tmp_path / 'minqlxtended-shared'
    _tree(str(shared), {'minqlxtended.x64.so': 'new engine\n', 'minqlxtended.zip': 'zip\n',
                        'run_server_x64_minqlxtended.sh': '#!/bin/sh\n'})
    common = tmp_path / 'common'
    _tree(str(common), {'serverchecker.py': 'pool\n', 'balance.py': 'pool balance\n'})
    unit_dir = tmp_path / 'systemd'
    _tree(str(unit_dir), {'qlds@27960.service': 'old unit\n'})
    unit = str(unit_dir / 'qlds@27960.service')
    plan = {
        'operation_id': OP_A, 'instance_id': 7,
        'qlds_dir': str(qlds), 'ops_dir': str(ops),
        'record': True,
        'extra_destinations': [unit],
        'sources': [
            {'kind': 'tree', 'from': str(stage / 'tree'), 'into': str(qlds)},
            {'kind': 'names', 'from': str(shared), 'into': str(qlds),
             'names': ['minqlxtended.x64.so', 'minqlxtended.zip', 'run_server_x64_minqlxtended.sh']},
            {'kind': 'missing_only', 'from': str(common), 'into': str(qlds / 'minqlxtended-plugins')},
            {'kind': 'file', 'from': str(stage / 'qlds@27960.service'), 'to': unit},
        ],
    }
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    return {'qlds': qlds, 'ops': str(ops), 'base': str(base), 'tmp': tmp_path,
            'unit': unit_dir / 'qlds@27960.service', 'plan_data': plan,
            'apply': ['apply', '--base', str(base), '--plan', str(plan_path)],
            'restore': ['restore', '--base', str(base), '--ops-dir', str(ops),
                        '--qlds-dir', str(qlds), '--unit-path', unit]}


def test_apply_records_then_installs_and_restore_reverses_it(helper, instance, capsys):
    qlds = instance['qlds']
    rc, out = _run(helper, capsys, *instance['apply'])
    assert rc == 0, out
    assert _read(qlds / 'baseq3/server.cfg') == 'new cfg\n'
    assert _read(qlds / 'minqlxtended.x64.so') == 'new engine\n'
    assert _read(qlds / 'minqlxtended-plugins/balance.py') == 'new plugin\n'  # stage wins over pool
    assert _read(qlds / 'minqlxtended-plugins/serverchecker.py') == 'pool\n'  # backfilled
    assert _read(instance['unit']) == 'new unit\n'
    assert os.stat(instance['unit']).st_mode & 0o777 == 0o644
    # Untouched: old runtime files, baseq3 data, plugin-owned data.
    assert _read(qlds / 'minqlx.x64.so') == 'old engine\n'
    assert _read(qlds / 'minqlx-plugins/balance.py') == 'old plugin\n'
    assert _read(qlds / 'baseq3/maps/sentinel.bsp') == 'map data\n'

    manifest = json.loads(_read(os.path.join(instance['ops'], 'manifest.json')))
    cfg = manifest['entries'][str(qlds / 'baseq3/server.cfg')]
    assert cfg['existed'] and cfg['mode'] and len(cfg['sha256']) == 64
    assert cfg['backup'].startswith(os.path.join(instance['ops'], 'files') + '/')
    assert manifest['entries'][str(qlds / 'minqlxtended.x64.so')]['existed'] is False

    rc, out = _run(helper, capsys, *instance['restore'])
    assert rc == 0, out
    assert _read(qlds / 'baseq3/server.cfg') == 'old cfg\n'
    assert _read(instance['unit']) == 'old unit\n'
    assert not (qlds / 'minqlxtended.x64.so').exists()
    assert not (qlds / 'minqlxtended-plugins/serverchecker.py').exists()
    assert _read(qlds / 'minqlxtended-plugins/plugin_data.json') == '{"owned": "by plugin"}\n'
    assert _read(qlds / 'baseq3/maps/sentinel.bsp') == 'map data\n'


def test_replayed_apply_never_overwrites_the_recorded_originals(helper, instance, capsys):
    _run(helper, capsys, *instance['apply'])
    _run(helper, capsys, *instance['apply'])  # retry after a failure
    _run(helper, capsys, *instance['restore'])
    assert _read(instance['qlds'] / 'baseq3/server.cfg') == 'old cfg\n'
    assert _read(instance['unit']) == 'old unit\n'


def test_restore_keeps_a_created_file_that_changed_since(helper, instance, capsys):
    _run(helper, capsys, *instance['apply'])
    changed = instance['qlds'] / 'minqlxtended-plugins/serverchecker.py'
    changed.write_text('edited by someone else\n')
    rc, out = _run(helper, capsys, *instance['restore'])
    assert rc == 0 and str(changed) in out['kept']
    assert changed.exists()


def _replan(instance, name, **changes):
    path = instance['tmp'] / name
    path.write_text(json.dumps(dict(instance['plan_data'], **changes)))
    return ['apply', '--base', instance['base'], '--plan', str(path)]


def test_unrecorded_apply_writes_no_inventory(helper, instance, capsys):
    rc, _out = _run(helper, capsys, *_replan(instance, 'p2.json', record=False))
    assert rc == 0
    assert not os.path.exists(os.path.join(instance['ops'], 'manifest.json'))


def test_apply_refuses_destinations_outside_the_instance(helper, instance, capsys):
    rc, out = _run(helper, capsys, *_replan(instance, 'p3.json', extra_destinations=[]))
    assert rc == 3 and 'not an allowed extra destination' in out['refused']
    assert _read(instance['qlds'] / 'baseq3/server.cfg') == 'old cfg\n'  # nothing written


def test_apply_refuses_an_ops_dir_outside_the_root_owned_base(helper, instance, capsys):
    rc, out = _run(helper, capsys, *_replan(
        instance, 'p4.json', ops_dir=str(instance['tmp'] / 'ops' / OP_A / '7')))
    assert rc == 3 and 'not under' in out['refused']


def test_apply_refuses_a_symlinked_path_component(helper, instance, capsys):
    """The ql user controls /home/ql/qlds-<port>: a planted symlink must never
    redirect a root write elsewhere."""
    victim = instance['tmp'] / 'victim'
    victim.mkdir()
    plugins = instance['qlds'] / 'minqlxtended-plugins'
    for child in plugins.iterdir():
        child.unlink()
    plugins.rmdir()
    plugins.symlink_to(victim, target_is_directory=True)
    rc, out = _run(helper, capsys, *instance['apply'])
    assert rc == 3 and 'symlink' in out['refused']
    assert list(victim.iterdir()) == []


def test_apply_refuses_a_symlinked_destination_file(helper, instance, capsys):
    victim = instance['tmp'] / 'victim.txt'
    victim.write_text('do not touch\n')
    cfg = instance['qlds'] / 'baseq3/server.cfg'
    cfg.unlink()
    cfg.symlink_to(victim)
    rc, out = _run(helper, capsys, *instance['apply'])
    assert rc == 3
    assert _read(victim) == 'do not touch\n'


def test_apply_refuses_a_symlinked_source(helper, instance, capsys):
    secret = instance['tmp'] / 'secret'
    secret.write_text('root only\n')
    (instance['tmp'] / 'common' / 'leak.py').symlink_to(secret)
    rc, out = _run(helper, capsys, *instance['apply'])
    assert rc == 3 and 'symlink' in out['refused']
    assert not (instance['qlds'] / 'minqlxtended-plugins/leak.py').exists()


def _tamper(instance, change):
    path = os.path.join(instance['ops'], 'manifest.json')
    manifest = json.loads(_read(path))
    change(manifest)
    with open(path, 'w') as handle:
        json.dump(manifest, handle)


def test_restore_refuses_a_manifest_destination_outside_the_allowed_roots(helper, instance, capsys):
    _run(helper, capsys, *instance['apply'])
    outside = str(instance['tmp'] / 'elsewhere.txt')
    _tamper(instance, lambda m: m['entries'].update({outside: {'existed': False, 'written_sha256': 'x'}}))
    rc, out = _run(helper, capsys, *instance['restore'])
    assert rc == 3 and 'outside the allowed roots' in out['refused']
    assert _read(instance['qlds'] / 'baseq3/server.cfg') == 'new cfg\n'  # nothing restored


def test_restore_refuses_a_backup_outside_the_operation_files_dir(helper, instance, capsys):
    _run(helper, capsys, *instance['apply'])
    cfg = str(instance['qlds'] / 'baseq3/server.cfg')
    _tamper(instance, lambda m: m['entries'][cfg].update({'backup': '/etc/shadow'}))
    rc, out = _run(helper, capsys, *instance['restore'])
    assert rc == 3 and 'outside' in out['refused']
    assert _read(instance['qlds'] / 'baseq3/server.cfg') == 'new cfg\n'


def test_restore_refuses_a_qlds_dir_mismatch(helper, instance, capsys):
    _run(helper, capsys, *instance['apply'])
    args = list(instance['restore'])
    args[args.index('--qlds-dir') + 1] = str(instance['tmp'] / 'qlds-27961')
    rc, out = _run(helper, capsys, *args)
    assert rc == 3 and 'another instance directory' in out['refused']


def test_restore_without_inventory_is_a_no_op(helper, instance, capsys):
    args = list(instance['restore'])
    args[args.index('--ops-dir') + 1] = os.path.join(instance['base'], 'ops', OP_B, '7')
    rc, out = _run(helper, capsys, *args)
    assert rc == 0 and out['restored'] == 0


def test_lock_base_must_not_be_a_symlink(helper, tmp_path, capsys):
    real = tmp_path.resolve() / 'real'
    real.mkdir(mode=0o700)
    link = tmp_path.resolve() / 'link'
    link.symlink_to(real, target_is_directory=True)
    rc, out = _run(helper, capsys, 'acquire', '--base', str(link), '--operation-id', OP_A,
                   '--fencing-token', '1')
    assert rc == 3 and 'symlink' in out['refused']


def test_apply_refuses_a_hard_linked_source(helper, instance, capsys):
    secret = instance['tmp'] / 'secret'
    secret.write_text('root only\n')
    os.link(secret, instance['tmp'] / 'common' / 'leak.py')
    rc, out = _run(helper, capsys, *instance['apply'])
    assert rc == 3 and 'hard links' in out['refused']
    assert not (instance['qlds'] / 'minqlxtended-plugins/leak.py').exists()


def test_apply_refuses_a_fifo_source_without_blocking(helper, instance, capsys):
    os.mkfifo(instance['tmp'] / 'common' / 'pipe.py')
    rc, out = _run(helper, capsys, *instance['apply'])
    assert rc == 3 and 'not a regular file' in out['refused']


def test_apply_refuses_backing_up_a_hard_linked_destination(helper, instance, capsys):
    """A ql-planted hard link at a managed path must not be copied (as root)
    into the backup, nor overwritten in place."""
    victim = instance['tmp'] / 'victim.txt'
    victim.write_text('do not copy\n')
    cfg = instance['qlds'] / 'baseq3/server.cfg'
    cfg.unlink()
    os.link(victim, cfg)
    rc, out = _run(helper, capsys, *instance['apply'])
    assert rc == 3 and 'hard links' in out['refused']
    assert not os.path.exists(os.path.join(instance['ops'], 'files', '000000'))
    assert _read(victim) == 'do not copy\n'


def test_a_writable_non_sticky_ancestor_is_refused(helper, tmp_path, capsys):
    """Only a root-owned sticky ancestor (like /tmp) may be writable by others."""
    shared = tmp_path.resolve() / 'shared'
    shared.mkdir()
    os.chmod(shared, 0o777)
    rc, out = _run(helper, capsys, 'acquire', '--base', str(shared / 'runtime-ops'),
                   '--operation-id', OP_A, '--fencing-token', '1')
    assert rc == 3 and 'non-writable-by-others' in out['refused'] and str(shared) in out['refused']


def test_the_base_itself_may_never_be_writable_by_others(helper, tmp_path, capsys):
    base = tmp_path.resolve() / 'runtime-ops'
    base.mkdir()
    os.chmod(base, 0o1777)
    rc, out = _run(helper, capsys, 'acquire', '--base', str(base),
                   '--operation-id', OP_A, '--fencing-token', '1')
    assert rc == 3 and 'non-writable-by-others' in out['refused']
