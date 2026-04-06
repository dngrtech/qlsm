import pytest
from unittest.mock import MagicMock, patch

from ui import create_app, db
from ui.models import Host, QLInstance, HostStatus, InstanceStatus
from ui.tasks import apply_instance_config
from ui.task_logic.ansible_runner import SimpleAnsibleResult

TASK_LOGIC_MODULE = 'ui.task_logic.ansible_instance_mgmt'

@pytest.fixture(scope='module')
def test_app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        yield app


def _make_mock_instance(instance_id=12, status=InstanceStatus.RUNNING):
    mock_host = MagicMock(spec=Host)
    mock_host.name = 'test-host'
    mock_host.ip_address = '7.8.9.0'
    mock_host.ssh_user = 'configuser'
    mock_host.ssh_key_path = '/config/key.pem'

    mock_instance = MagicMock(spec=QLInstance)
    mock_instance.id = instance_id
    mock_instance.port = 27960
    mock_instance.status = status
    mock_instance.host = mock_host
    mock_instance.config = '+set sv_hostname "Test Server"'
    return mock_instance


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_apply_instance_config_success(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test successful config application via Ansible."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance(status=InstanceStatus.RUNNING)
    mock_session.get.return_value = mock_instance

    mock_run_playbook.return_value = (SimpleAnsibleResult(0, 'Ansible success', ''), None)

    result = apply_instance_config(12)

    mock_session.get.assert_called_once_with(QLInstance, 12)
    mock_prep_zmq.assert_called_once_with(mock_instance)
    mock_run_playbook.assert_called_once()
    assert mock_instance.status == InstanceStatus.RUNNING
    assert mock_session.commit.call_count == 2
    assert mock_append_log.called, "append_log should be called during config apply"
    assert 'config application successful' in result


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_apply_instance_config_ansible_failure(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test config application when Ansible returns non-zero RC."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance

    mock_run_playbook.return_value = (SimpleAnsibleResult(1, 'failure output', 'stderr'), None)

    result = apply_instance_config(12)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 2
    assert 'config application failed' in result


@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_apply_instance_config_not_found(mock_get_job, mock_session, mock_append_log, test_app):
    """Test config application when instance is not in DB."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job
    mock_session.get.return_value = None

    result = apply_instance_config(99)

    mock_session.get.assert_called_once_with(QLInstance, 99)
    mock_session.commit.assert_not_called()
    assert 'Error: Instance 99 not found' in result


@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_apply_instance_config_no_host(mock_get_job, mock_session, mock_append_log, test_app):
    """Test config application when instance has no associated host."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = MagicMock(spec=QLInstance)
    mock_instance.id = 12
    mock_instance.host = None
    mock_session.get.return_value = mock_instance

    result = apply_instance_config(12)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 1
    assert 'Error during instance 12 config apply: Host not found' in result


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_apply_instance_config_exception(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test config application when an exception is raised."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance
    mock_run_playbook.side_effect = Exception('Config apply error')

    result = apply_instance_config(12)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 2
    assert 'Error during instance 12 config application: Config apply error' in result
