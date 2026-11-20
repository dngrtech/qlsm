import os
import shlex
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from ui.task_logic.ssh_command import build_host_ssh_command, run_host_ssh_command


def _host(**over):
    values = dict(name='h1', ip_address='203.0.113.5', ssh_key_path='keys/h1', ssh_user='ansible',
                  ssh_port=2222, provider='vultr')
    values.update(over)
    return SimpleNamespace(**values)


def test_build_runs_the_command_as_root_with_a_shared_connection():
    argv = build_host_ssh_command(_host(), "find /x \\( -name '*.py' \\) -exec sha256sum {} +")

    assert argv[0] == 'ssh'
    assert argv[argv.index('-i') + 1] == os.path.abspath('keys/h1')
    assert argv[argv.index('-p') + 1] == '2222'
    assert argv[argv.index('-l') + 1] == 'ansible'
    assert 'BatchMode=yes' in argv
    assert 'ControlMaster=auto' in argv
    assert any(a.startswith('ControlPath=') and a.endswith('/%C') for a in argv)
    assert argv[-2] == '203.0.113.5'
    # The remote shell gets exactly the command back, run through sudo -n.
    remote = shlex.split(argv[-1])
    assert remote[:4] == ['sudo', '-n', 'sh', '-c']
    assert remote[4] == "find /x \\( -name '*.py' \\) -exec sha256sum {} +"


def test_build_without_become_and_for_the_self_host():
    with patch('ui.task_logic.access_permission_sync.resolve_self_host_management_target',
               return_value='172.17.0.1'):
        argv = build_host_ssh_command(_host(provider='self'), 'true', become=False)
    assert argv[-2:] == ['172.17.0.1', 'true']


@patch('ui.task_logic.ssh_command.subprocess.run')
def test_run_returns_stdout_on_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess([], 0, stdout='abc  /x/a.py\n', stderr='')
    assert run_host_ssh_command(_host(), 'true') == (True, 'abc  /x/a.py\n', '')
    assert mock_run.call_args.kwargs['timeout'] == 30


@patch('ui.task_logic.ssh_command.subprocess.run')
def test_run_reports_a_failure_with_its_stderr(mock_run):
    mock_run.return_value = subprocess.CompletedProcess([], 255, stdout='', stderr='Connection refused\n')
    assert run_host_ssh_command(_host(), 'true') == (False, '', 'Connection refused')

    mock_run.return_value = subprocess.CompletedProcess([], 1, stdout='', stderr='')
    assert run_host_ssh_command(_host(), 'true') == (False, '', 'Command failed with exit code 1')


@patch('ui.task_logic.ssh_command.subprocess.run', side_effect=subprocess.TimeoutExpired('ssh', 30))
def test_run_reports_a_timeout(_mock_run):
    assert run_host_ssh_command(_host(), 'true', timeout=30) == (False, '', 'Timed out after 30s')


def test_run_refuses_a_host_without_connection_details():
    ok, _out, err = run_host_ssh_command(_host(ip_address=None), 'true')
    assert not ok and 'Host details missing' in err
