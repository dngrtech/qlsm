import pytest
import subprocess
from unittest.mock import MagicMock, patch, call, ANY

from ui import create_app, db
from ui.models import Host, HostStatus
from ui.tasks import destroy_host

TASK_LOGIC_MODULE = 'ui.task_logic.terraform_destroy'

@pytest.fixture(scope='module')
def test_app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SERVER_NAME': 'localhost.test'
    })
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


mock_destroy_host_data = {
    'id': 2,
    'name': 'Host To Destroy',
    'provider': 'vultr',
    'region': 'ewr',
    'machine_size': 'vc2-1c-1gb',
    'status': HostStatus.ACTIVE,
    'workspace_name': 'host-2-host-to-destroy',
    'ssh_key_path': '/path/to/ssh-keys/Host-To-Destroy_id_rsa',
    'logs': None
}


@patch(f'{TASK_LOGIC_MODULE}._run_terraform_command')
@patch(f'{TASK_LOGIC_MODULE}.os.path.isdir', return_value=True)
@patch(f'{TASK_LOGIC_MODULE}.os.path.exists', return_value=True)
@patch(f'{TASK_LOGIC_MODULE}.os.remove')
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value='/usr/bin/terraform')
@patch(f'{TASK_LOGIC_MODULE}.shutil.rmtree')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_destroy_host_success(
    mock_get_job, mock_append_log, mock_session, mock_rmtree, mock_which,
    mock_os_remove, mock_os_exists, mock_isdir, mock_run_tf, test_app
):
    """Test successful destroy using Terraform."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id-destroy'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_destroy_host_data)
    mock_session.get.return_value = mock_host
    mock_run_tf.return_value = ('stdout', None)

    result = destroy_host(mock_host.id)

    mock_session.get.assert_called_once_with(Host, mock_host.id)
    mock_which.assert_called_once_with("terraform")
    assert mock_isdir.called

    assert mock_run_tf.call_count == 5  # init, select workspace, destroy, select default, delete workspace

    tf_calls = mock_run_tf.call_args_list
    assert call(mock_host, ['init', '-input=false', '-no-color'], ANY) in tf_calls
    assert call(mock_host, ['workspace', 'select', mock_host.workspace_name], ANY) in tf_calls
    assert call(mock_host, ['workspace', 'select', 'default'], ANY) in tf_calls
    assert call(mock_host, ['workspace', 'delete', mock_host.workspace_name], ANY) in tf_calls

    destroy_call = [c for c in tf_calls if len(c.args) > 1 and c.args[1][0] == 'destroy']
    assert len(destroy_call) == 1

    mock_os_exists.assert_called()
    mock_os_remove.assert_called()
    mock_session.delete.assert_called_once_with(mock_host)
    assert mock_session.commit.call_count >= 3

    assert f"Host {mock_host.id} ({mock_host.name}) destruction complete and record deleted." in result


@patch(f'{TASK_LOGIC_MODULE}._run_terraform_command')
@patch(f'{TASK_LOGIC_MODULE}.os.path.isdir', return_value=True)
@patch(f'{TASK_LOGIC_MODULE}.os.path.exists')
@patch(f'{TASK_LOGIC_MODULE}.os.remove')
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value='/usr/bin/terraform')
@patch(f'{TASK_LOGIC_MODULE}.shutil.rmtree')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_destroy_host_destroy_fails(
    mock_get_job, mock_append_log, mock_session, mock_rmtree, mock_which,
    mock_os_remove, mock_os_exists, mock_isdir, mock_run_tf, test_app
):
    """Test destroy_host when terraform destroy command fails."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id-destroy-fail'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_destroy_host_data)
    mock_session.get.return_value = mock_host

    destroy_failure_error = "Terraform command failed (RC: 1): Destroy command failed!"
    mock_run_tf.side_effect = [
        ('stdout', None),               # init
        ('stdout', None),               # workspace select
        (None, destroy_failure_error),  # destroy fails
    ]

    result = destroy_host(mock_host.id)

    assert mock_host.status == HostStatus.ERROR
    mock_os_remove.assert_not_called()
    mock_session.delete.assert_not_called()
    assert mock_session.commit.call_count == 2
    assert 'Error during terraform destroy' in result


@patch(f'{TASK_LOGIC_MODULE}._run_terraform_command')
@patch(f'{TASK_LOGIC_MODULE}.os.path.isdir', return_value=True)
@patch(f'{TASK_LOGIC_MODULE}.os.path.exists', return_value=True)
@patch(f'{TASK_LOGIC_MODULE}.os.remove')
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value='/usr/bin/terraform')
@patch(f'{TASK_LOGIC_MODULE}.shutil.rmtree')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_destroy_host_workspace_not_found(
    mock_get_job, mock_append_log, mock_session, mock_rmtree, mock_which,
    mock_os_remove, mock_os_exists, mock_isdir, mock_run_tf, test_app
):
    """Test destroy_host when workspace is not found (assumed already destroyed)."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id-ws-gone'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_destroy_host_data)
    mock_session.get.return_value = mock_host

    select_failure = "Terraform command failed (RC: 1): Workspace not found"
    mock_run_tf.side_effect = [
        ('stdout', None),        # init
        (None, select_failure),  # workspace select fails → skip destroy
    ]

    result = destroy_host(mock_host.id)

    mock_os_remove.assert_called()
    mock_session.delete.assert_called_once_with(mock_host)
    assert mock_session.commit.call_count >= 3

    log_calls = mock_append_log.call_args_list
    assert call(mock_host, f"Warning: Workspace '{mock_host.workspace_name}' not found. Proceeding with cleanup.") in log_calls
    assert call(mock_host, "Terraform destroy/cleanup successful. Removing associated files and DB record...") in log_calls

    assert f"Host {mock_host.id} ({mock_host.name}) destruction complete and record deleted." in result


@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value=None)
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
def test_destroy_host_terraform_not_found(mock_append_log, mock_session, mock_which, mock_get_job, test_app):
    """Test destroy_host when terraform executable is not found."""
    mock_job = MagicMock(); mock_job.id = 'test-job-tf-not-found'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_destroy_host_data)
    mock_session.get.return_value = mock_host

    result = destroy_host(mock_host.id)

    mock_which.assert_called_once_with("terraform")
    assert "Error: Terraform executable not found" in result
    assert mock_host.status == HostStatus.ERROR
    mock_append_log.assert_called_once_with(mock_host, "Task failed: Terraform executable not found in PATH.")
    mock_session.commit.assert_called_once()
