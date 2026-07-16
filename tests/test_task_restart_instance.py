import pytest
from unittest.mock import MagicMock, patch, call

from ui import create_app, db
from ui.models import Host, QLInstance, HostStatus, InstanceStatus
from ui.tasks import restart_instance
from ui.task_logic.ansible_runner import SimpleAnsibleResult

TASK_LOGIC_MODULE = 'ui.task_logic.ansible_instance_mgmt'

@pytest.fixture(scope='module')
def test_app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        yield app


def _make_mock_instance(instance_id=11, status=InstanceStatus.RUNNING):
    mock_host = MagicMock(spec=Host)
    mock_host.name = 'test-host'
    mock_host.ip_address = '1.2.3.4'
    mock_host.ssh_user = 'testuser'
    mock_host.ssh_key_path = '/fake/key.pem'

    mock_instance = MagicMock(spec=QLInstance)
    mock_instance.id = instance_id
    mock_instance.status = status
    mock_instance.host = mock_host
    mock_instance.port = 27960
    return mock_instance


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_restart_instance_success(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test successful restart via Ansible."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance

    mock_run_playbook.return_value = (SimpleAnsibleResult(0, 'Ansible stdout', ''), None)

    result = restart_instance(11)

    mock_session.get.assert_called_once_with(QLInstance, 11)
    mock_prep_zmq.assert_called_once_with(mock_instance)
    mock_run_playbook.assert_called_once()
    assert mock_instance.status == InstanceStatus.RUNNING
    assert mock_session.commit.call_count == 2
    assert mock_append_log.called, "append_log should be called during restart"
    assert result == 'Instance 11 restart successful. Status: RUNNING'


@patch(f'{TASK_LOGIC_MODULE}.ensure_instance_cpu_affinity', return_value=1)
@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_restart_instance_passes_cpu_affinity(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, mock_ensure_affinity, test_app
):
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance
    mock_run_playbook.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    restart_instance(11)

    mock_ensure_affinity.assert_called_once_with(mock_instance)
    extravars = mock_run_playbook.call_args.kwargs['extravars']
    assert extravars['cpu_affinity'] == 1


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_restart_instance_ansible_failure(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test restart when Ansible returns non-zero RC."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance

    mock_run_playbook.return_value = (SimpleAnsibleResult(2, 'Ansible failure output', 'stderr'), None)

    result = restart_instance(11)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 2
    assert result == 'Error: Instance 11 restart failed. RC: 2'


@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_restart_instance_not_found(mock_get_job, mock_session, mock_append_log, test_app):
    """Test restart when instance is not in DB."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job
    mock_session.get.return_value = None

    result = restart_instance(99)

    mock_session.get.assert_called_once_with(QLInstance, 99)
    mock_session.commit.assert_not_called()
    assert 'Error: Instance 99 not found' in result


@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_restart_instance_no_host(mock_get_job, mock_session, mock_append_log, test_app):
    """Test restart when instance has no associated host."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = MagicMock(spec=QLInstance)
    mock_instance.id = 11
    mock_instance.host = None
    mock_session.get.return_value = mock_instance

    result = restart_instance(11)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 1
    assert 'Error during instance 11 restart: Host not found' in result


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_restart_instance_exception(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test restart when _run_ansible_playbook raises an exception."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance
    mock_run_playbook.side_effect = Exception('Ansible internal error')

    result = restart_instance(11)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 2
    assert 'Ansible internal error' in result


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_restart_instance_pip_warning_logged(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Pip install warnings emitted by Ansible are logged during restart."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance(status=InstanceStatus.RUNNING)
    mock_session.get.return_value = mock_instance

    stdout = 'task output\nQLSM_PIP_WARN: pip install failed: No module named requests\nmore output'
    mock_run_playbook.return_value = (SimpleAnsibleResult(0, stdout, ''), None)

    result = restart_instance(mock_instance.id)

    assert mock_instance.status == InstanceStatus.RUNNING
    logged_messages = [str(call) for call in mock_append_log.call_args_list]
    assert any('pip install failed' in msg for msg in logged_messages)
