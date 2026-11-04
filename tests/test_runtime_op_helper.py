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
    qlds = tmp_path / 'qlds-27960'
    _tree(str(qlds), {
        'baseq3/server.cfg': 'old cfg\n',
        'baseq3/maps/sentinel.bsp': 'map data\n',
        'minqlx-plugins/balance.py': 'old plugin\n',
        'minqlx.x64.so': 'old engine\n',
        'minqlxtended-plugins/plugin_data.json': '{"owned": "by plugin"}\n',
    })
    stage = tmp_path / 'stage'
    _tree(str(stage / 'tree'), {
        'baseq3/server.cfg': 'new cfg\n',
        'minqlxtended-plugins/balance.py': 'new plugin\n',
    })
    shared = tmp_path / 'minqlxtended-shared'
    _tree(str(shared), {'minqlxtended.x64.so': 'new engine\n', 'minqlxtended.zip': 'zip\n',
                        'run_server_x64_minqlxtended.sh': '#!/bin/sh\n'})
    common = tmp_path / 'common'
    _tree(str(common), {'serverchecker.py': 'pool\n', 'balance.py': 'pool balance\n'})
    unit_dir = tmp_path / 'systemd'
    _tree(str(unit_dir), {'qlds@27960.service': 'old unit\n'})
    _tree(str(stage), {'qlds@27960.service': 'new unit\n'})
    plan = {
        'operation_id': OP_A, 'instance_id': 7,
        'qlds_dir': str(qlds), 'ops_dir': str(tmp_path / 'ops' / OP_A / '7'),
        'record': True,
        'extra_destinations': [str(unit_dir / 'qlds@27960.service')],
        'sources': [
            {'kind': 'tree', 'from': str(stage / 'tree'), 'into': str(qlds)},
            {'kind': 'names', 'from': str(shared), 'into': str(qlds),
             'names': ['minqlxtended.x64.so', 'minqlxtended.zip', 'run_server_x64_minqlxtended.sh']},
            {'kind': 'missing_only', 'from': str(common), 'into': str(qlds / 'minqlxtended-plugins')},
            {'kind': 'file', 'from': str(stage / 'qlds@27960.service'),
             'to': str(unit_dir / 'qlds@27960.service'), 'mode': '0644', 'owner': 'root'},
        ],
    }
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    return {'qlds': qlds, 'plan': str(plan_path), 'ops': plan['ops_dir'],
            'unit': unit_dir / 'qlds@27960.service', 'plan_data': plan}


def test_apply_records_then_installs_and_restore_reverses_it(helper, instance, capsys):
    qlds = instance['qlds']
    rc, out = _run(helper, capsys, 'apply', '--plan', instance['plan'])
    assert rc == 0, out
    assert _read(qlds / 'baseq3/server.cfg') == 'new cfg\n'
    assert _read(qlds / 'minqlxtended.x64.so') == 'new engine\n'
    assert _read(qlds / 'minqlxtended-plugins/balance.py') == 'new plugin\n'  # stage wins over pool
    assert _read(qlds / 'minqlxtended-plugins/serverchecker.py') == 'pool\n'  # backfilled
    assert _read(instance['unit']) == 'new unit\n'
    # Untouched: old runtime files, baseq3 data, plugin-owned data.
    assert _read(qlds / 'minqlx.x64.so') == 'old engine\n'
    assert _read(qlds / 'minqlx-plugins/balance.py') == 'old plugin\n'
    assert _read(qlds / 'baseq3/maps/sentinel.bsp') == 'map data\n'

    manifest = json.loads(_read(os.path.join(instance['ops'], 'manifest.json')))
    cfg = manifest['entries'][str(qlds / 'baseq3/server.cfg')]
    assert cfg['existed'] and cfg['mode'] and len(cfg['sha256']) == 64
    assert manifest['entries'][str(qlds / 'minqlxtended.x64.so')]['existed'] is False

    rc, out = _run(helper, capsys, 'restore', '--ops-dir', instance['ops'])
    assert rc == 0, out
    assert _read(qlds / 'baseq3/server.cfg') == 'old cfg\n'
    assert _read(instance['unit']) == 'old unit\n'
    assert not (qlds / 'minqlxtended.x64.so').exists()
    assert not (qlds / 'minqlxtended-plugins/serverchecker.py').exists()
    assert _read(qlds / 'minqlxtended-plugins/plugin_data.json') == '{"owned": "by plugin"}\n'
    assert _read(qlds / 'baseq3/maps/sentinel.bsp') == 'map data\n'


def test_replayed_apply_never_overwrites_the_recorded_originals(helper, instance, capsys):
    _run(helper, capsys, 'apply', '--plan', instance['plan'])
    _run(helper, capsys, 'apply', '--plan', instance['plan'])  # retry after a failure
    _run(helper, capsys, 'restore', '--ops-dir', instance['ops'])
    assert _read(instance['qlds'] / 'baseq3/server.cfg') == 'old cfg\n'
    assert _read(instance['unit']) == 'old unit\n'


def test_restore_keeps_a_created_file_that_changed_since(helper, instance, capsys):
    _run(helper, capsys, 'apply', '--plan', instance['plan'])
    changed = instance['qlds'] / 'minqlxtended-plugins/serverchecker.py'
    changed.write_text('edited by someone else\n')
    rc, out = _run(helper, capsys, 'restore', '--ops-dir', instance['ops'])
    assert rc == 0 and str(changed) in out['kept']
    assert changed.exists()


def test_unrecorded_apply_writes_no_inventory(helper, instance, capsys, tmp_path):
    plan = dict(instance['plan_data'], record=False, ops_dir=str(tmp_path / 'other-ops'))
    path = tmp_path / 'plan2.json'
    path.write_text(json.dumps(plan))
    rc, _out = _run(helper, capsys, 'apply', '--plan', str(path))
    assert rc == 0
    assert not os.path.exists(tmp_path / 'other-ops' / 'manifest.json')


def test_apply_refuses_destinations_outside_the_instance(helper, instance, capsys, tmp_path):
    plan = dict(instance['plan_data'], extra_destinations=[])
    path = tmp_path / 'plan3.json'
    path.write_text(json.dumps(plan))
    rc, out = _run(helper, capsys, 'apply', '--plan', str(path))
    assert rc == 3 and 'outside the instance directory' in out['refused']
    assert _read(instance['qlds'] / 'baseq3/server.cfg') == 'old cfg\n'  # nothing written


def test_restore_without_inventory_is_a_no_op(helper, tmp_path, capsys):
    rc, out = _run(helper, capsys, 'restore', '--ops-dir', str(tmp_path / 'none'))
    assert rc == 0 and out['restored'] == 0
