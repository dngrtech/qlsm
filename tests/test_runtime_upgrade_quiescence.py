"""STOPPED verification for the runtime upgrade: systemd inactive and no
server process for the instance's port."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from ui.task_logic import service_runtime
from ui.task_logic.host_runtime_upgrade_deps import UpgradeDeps
from ui.task_logic.service_runtime import (
    PROCESS_SCAN_SOURCE,
    RuntimeObservation,
    build_runtime_probe_command,
    parse_runtime_probe_output,
    quiescence_state,
)


def _scan():
    namespace = {}
    exec(PROCESS_SCAN_SOURCE, namespace)  # the exact code the probe runs on the host
    return namespace['count_qlds_processes']


def _proc(root, pid, argv, cgroup=''):
    entry = root / str(pid)
    entry.mkdir(parents=True)
    (entry / 'cmdline').write_bytes(b'\0'.join(arg.encode() for arg in argv) + b'\0')
    (entry / 'cgroup').write_text(cgroup)


def test_process_scan_counts_unit_members_and_flagged_engines(tmp_path):
    proc = tmp_path / 'proc'
    _proc(proc, 10, ['/bin/bash', './run_server_x64_minqlx.sh'],
          '0::/system.slice/system-qlds.slice/qlds@27960.service\n')
    _proc(proc, 11, ['./qzeroded.x64', '+set', 'net_port', '27961', '+set', 'fs_homepath', 'x'])
    _proc(proc, 12, ['./qzeroded.x64', '+set', 'net_port', '27999'])  # another port
    _proc(proc, 13, ['python3', '-c', 'net_port 27962'])  # not an engine
    (proc / 'self').mkdir()  # non-numeric entries are ignored
    counts = _scan()([27960, 27961, 27962], proc_root=str(proc))
    assert counts == {27960: 1, 27961: 1, 27962: 0}


def test_process_scan_reports_unknown_without_proc(tmp_path):
    assert _scan()([27960], proc_root=str(tmp_path / 'missing')) is None


def test_quiescence_state():
    assert quiescence_state(RuntimeObservation(None, None, True, 1, processes=1)) == 'active'
    assert quiescence_state(RuntimeObservation(None, None, False, None, processes=0)) == 'inactive'
    assert quiescence_state(RuntimeObservation(None, None, False, None, processes=2)) == 'stray_process'
    assert quiescence_state(RuntimeObservation(None, None, False, None)) == 'unknown'
    assert quiescence_state(None) == 'unknown'


def test_probe_carries_process_counts_only_when_asked():
    host = SimpleNamespace(provider='vultr', ip_address='203.0.113.1', ssh_key_path='/k',
                           ssh_port=22, ssh_user='root')
    instance = SimpleNamespace(port=27960, redis_db=None)
    with_scan = build_runtime_probe_command(host, [instance], with_processes=True)[-1]
    without = build_runtime_probe_command(host, [instance])[-1]
    assert 'def count_qlds_processes' in with_scan
    assert 'def count_qlds_processes' not in without
    compile(service_runtime._remote_probe_script([(27960, 1)], None, with_processes=True), 'p', 'exec')

    parsed = parse_runtime_probe_output(json.dumps({'27960': {
        'status': None, 'active_state': 'inactive', 'invocation_id': None,
        'service_started_at': None, 'processes': 1}}))
    assert parsed['27960'].processes == 1
    legacy = parse_runtime_probe_output(json.dumps({'27960': {'active_state': 'inactive'}}))
    assert legacy['27960'].processes is None


def test_upgrade_service_state_uses_the_process_aware_probe():
    instance = SimpleNamespace(id=1, port=27960, host=SimpleNamespace(provider='vultr'))
    observation = RuntimeObservation(None, None, False, None, processes=1)
    with patch('ui.task_logic.service_runtime.probe_host_runtime',
               return_value={'27960': observation}) as probe:
        assert UpgradeDeps().service_state(instance) == 'stray_process'
    assert probe.call_args.kwargs['with_processes'] is True
    with patch('ui.task_logic.service_runtime.probe_host_runtime', return_value=None):
        assert UpgradeDeps().service_state(instance) == 'unknown'
