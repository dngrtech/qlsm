import pytest
from unittest.mock import MagicMock, patch
from ui.models import Host, HostStatus, QLFilterStatus

CLOUD_MODULE = 'ui.task_logic.ansible_host_setup'
STANDALONE_MODULE = 'ui.task_logic.standalone_host_setup'


@patch(f'{CLOUD_MODULE}.db.session')
@patch(f'{CLOUD_MODULE}.get_current_job')
@patch(f'{CLOUD_MODULE}.append_log')
@patch('ui.task_logic.ansible_runner._stream_output', return_value=('stdout ok', ''))
@patch(f'{CLOUD_MODULE}.subprocess.Popen')
@patch(f'{CLOUD_MODULE}.subprocess.run')
@patch(f'{CLOUD_MODULE}.os.path.exists', return_value=True)
def test_cloud_setup_sets_redis_unix_socket(
    mock_exists, mock_run, mock_popen, mock_stream, mock_append_log, mock_job, mock_session
):
    mock_job.return_value = MagicMock(id='job-1')
    host = MagicMock(spec=Host)
    host.id = 1
    host.name = 'testhost'
    host.ip_address = '1.2.3.4'
    host.ssh_key_path = '/key'
    host.ssh_user = 'ansible'
    host.provider = 'vultr'
    host.status = HostStatus.PROVISIONED_PENDING_SETUP
    host.timezone = None
    mock_session.get.return_value = host

    proc = MagicMock()
    proc.returncode = 0
    mock_popen.return_value = proc
    mock_run.return_value = MagicMock(stdout='ok', stderr='', returncode=0)

    from ui.task_logic.ansible_host_setup import setup_host_ansible_logic
    setup_host_ansible_logic(1)

    assert host.redis_unix_socket is True
    assert host.status == HostStatus.ACTIVE


@patch(f'{STANDALONE_MODULE}.db.session')
@patch(f'{STANDALONE_MODULE}.get_current_job')
@patch(f'{STANDALONE_MODULE}.append_log')
@patch(f'{STANDALONE_MODULE}._generate_standalone_inventory')
@patch(f'{STANDALONE_MODULE}._wait_for_ssh', return_value=True)
@patch(f'{STANDALONE_MODULE}._run_setup_playbook', return_value=True)
def test_standalone_setup_sets_redis_unix_socket(
    mock_playbook, mock_ssh, mock_inventory, mock_append_log, mock_job, mock_session
):
    mock_job.return_value = MagicMock(id='job-2')
    host = MagicMock(spec=Host)
    host.id = 2
    host.ip_address = '5.6.7.8'
    host.ssh_key_path = '/key'
    host.ssh_user = 'ansible'
    host.provider = 'vultr'
    host.status = HostStatus.PROVISIONED_PENDING_SETUP
    mock_session.get.return_value = host
    mock_inventory.return_value = ('/tmp/inv.yml', '5.6.7.8')

    from ui.task_logic.standalone_host_setup import setup_standalone_host_logic
    setup_standalone_host_logic(2)

    assert host.redis_unix_socket is True
    assert host.status == HostStatus.ACTIVE


@patch(f'{STANDALONE_MODULE}.db.session')
@patch(f'{STANDALONE_MODULE}.get_current_job')
@patch(f'{STANDALONE_MODULE}.append_log')
@patch(f'{STANDALONE_MODULE}._generate_standalone_inventory')
@patch(f'{STANDALONE_MODULE}._wait_for_ssh', return_value=True)
@patch(f'{STANDALONE_MODULE}._run_setup_playbook', return_value=True)
def test_self_host_setup_does_not_set_redis_unix_socket(
    mock_playbook, mock_ssh, mock_inventory, mock_append_log, mock_job, mock_session
):
    """Self-host provider must NOT flip the flag — Docker Redis has no socket."""
    mock_job.return_value = MagicMock(id='job-3')
    host = MagicMock(spec=Host)
    host.id = 3
    host.ip_address = '127.0.0.1'
    host.ssh_key_path = '/key'
    host.ssh_user = 'ansible'
    host.provider = 'self'
    host.status = HostStatus.PROVISIONED_PENDING_SETUP
    host.redis_unix_socket = False
    mock_session.get.return_value = host
    mock_inventory.return_value = ('/tmp/inv.yml', 'host.docker.internal')

    from ui.task_logic.standalone_host_setup import setup_standalone_host_logic
    setup_standalone_host_logic(3)

    assert host.redis_unix_socket is False
