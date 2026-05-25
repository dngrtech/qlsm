"""When initial host setup succeeds, Host.lan_rate_uses_hook is set to True
so new hosts start on the LD_PRELOAD hook mechanism. Follows the precedent
of test_host_setup_sets_socket_flag.py — monkeypatches subprocess.Popen."""
from unittest.mock import MagicMock, patch
from ui.models import Host, HostStatus, QLFilterStatus

CLOUD_MODULE = 'ui.task_logic.ansible_host_setup'


@patch(f'{CLOUD_MODULE}.db.session')
@patch(f'{CLOUD_MODULE}.get_current_job')
@patch(f'{CLOUD_MODULE}.append_log')
@patch('ui.task_logic.ansible_runner._stream_output', return_value=('stdout ok', ''))
@patch(f'{CLOUD_MODULE}.subprocess.Popen')
@patch(f'{CLOUD_MODULE}.subprocess.run')
@patch(f'{CLOUD_MODULE}.os.path.exists', return_value=True)
def test_successful_initial_setup_sets_lan_rate_uses_hook_true(
    mock_exists, mock_run, mock_popen, mock_stream, mock_append_log, mock_job, mock_session
):
    mock_job.return_value = MagicMock(id='job-1')
    host = MagicMock(spec=Host)
    host.id = 1
    host.name = 'newly-provisioned'
    host.ip_address = '1.2.3.4'
    host.ssh_key_path = '/key'
    host.ssh_user = 'ansible'
    host.provider = 'vultr'
    host.status = HostStatus.PROVISIONED_PENDING_SETUP
    host.timezone = None
    host.lan_rate_uses_hook = False
    mock_session.get.return_value = host

    proc = MagicMock()
    proc.returncode = 0
    mock_popen.return_value = proc
    mock_run.return_value = MagicMock(stdout='ok', stderr='', returncode=0)

    from ui.task_logic.ansible_host_setup import setup_host_ansible_logic
    setup_host_ansible_logic(1)

    assert host.lan_rate_uses_hook is True
    assert host.status == HostStatus.ACTIVE


@patch(f'{CLOUD_MODULE}.db.session')
@patch(f'{CLOUD_MODULE}.get_current_job')
@patch(f'{CLOUD_MODULE}.append_log')
@patch('ui.task_logic.ansible_runner._stream_output', return_value=('stdout fail', 'error output'))
@patch(f'{CLOUD_MODULE}.subprocess.Popen')
@patch(f'{CLOUD_MODULE}.subprocess.run')
@patch(f'{CLOUD_MODULE}.os.path.exists', return_value=True)
def test_failed_initial_setup_leaves_flag_false(
    mock_exists, mock_run, mock_popen, mock_stream, mock_append_log, mock_job, mock_session
):
    mock_job.return_value = MagicMock(id='job-2')
    host = MagicMock(spec=Host)
    host.id = 2
    host.name = 'newly-provisioned-fail'
    host.ip_address = '1.2.3.5'
    host.ssh_key_path = '/key'
    host.ssh_user = 'ansible'
    host.provider = 'vultr'
    host.status = HostStatus.PROVISIONED_PENDING_SETUP
    host.timezone = None
    host.lan_rate_uses_hook = False
    mock_session.get.return_value = host

    proc = MagicMock()
    proc.returncode = 1
    mock_popen.return_value = proc
    mock_run.return_value = MagicMock(stdout='ok', stderr='', returncode=0)

    from ui.task_logic.ansible_host_setup import setup_host_ansible_logic
    setup_host_ansible_logic(2)

    assert host.lan_rate_uses_hook is False
    assert host.status == HostStatus.ERROR
