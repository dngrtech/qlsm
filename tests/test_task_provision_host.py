import os
import pytest
import json
from unittest.mock import MagicMock, patch, call, ANY

from ui import create_app, db
from ui.models import Host, HostStatus
from ui.tasks import provision_host, setup_host_ansible
from ui import rq

TASK_LOGIC_MODULE = 'ui.task_logic.terraform_provision'

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


@pytest.fixture(autouse=True)
def use_test_app_context(test_app):
    with patch('ui.task_context.create_app', return_value=test_app):
        yield


mock_host_data = {
    'id': 1,
    'name': 'Test Host One',
    'provider': 'vultr',
    'region': 'ewr',
    'machine_size': 'vc2-1c-1gb',
    'status': HostStatus.PENDING,
    'workspace_name': None,
    'ip_address': None,
    'ssh_key_path': None,
    'logs': None
}

mock_tf_output = {
    "main_ip": {"sensitive": False, "type": "string", "value": "192.0.2.10"},
    "private_key_path": {"sensitive": False, "type": "string", "value": "/path/to/ssh-keys/Test-Host-One_id_rsa"}
}


@patch(f'{TASK_LOGIC_MODULE}._run_terraform_command')
@patch(f'{TASK_LOGIC_MODULE}.run_terraform_with_retry')
@patch(f'{TASK_LOGIC_MODULE}.os.path.isdir', return_value=True)
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value='/usr/bin/terraform')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
@patch(f'{TASK_LOGIC_MODULE}.rq')
def test_provision_host_success(
    mock_rq, mock_get_job, mock_append_log, mock_session, mock_which,
    mock_isdir, mock_run_tf_retry, mock_run_tf, test_app
):
    """Test successful host provisioning with Terraform."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_host_data)
    mock_session.get.return_value = mock_host

    mock_queue = MagicMock()
    mock_rq.get_queue.return_value = mock_queue

    # _run_terraform_command: init, workspace select (fails), workspace new, workspace select
    mock_run_tf.side_effect = [
        ('Init success', None),                   # init
        (None, 'Workspace not found'),             # select fails
        ('Created workspace', None),               # new
        ('Selected workspace', None),              # select again
    ]
    # run_terraform_with_retry: apply, output
    mock_run_tf_retry.side_effect = [
        ('Apply complete!', None),                 # apply
        (mock_tf_output, None),                    # output -json
    ]

    result = provision_host(mock_host.id)

    mock_session.get.assert_called_once_with(Host, mock_host.id)
    mock_which.assert_called_once_with("terraform")
    assert mock_isdir.called

    assert mock_host.ip_address == mock_tf_output['main_ip']['value']
    # SSH key path is stored as a relative path (portable across deployments).
    # Verify it resolves back to the original absolute path when joined with app root.
    assert not os.path.isabs(mock_host.ssh_key_path), "ssh_key_path should be relative"
    app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    resolved = os.path.normpath(os.path.join(app_root, mock_host.ssh_key_path))
    assert resolved == mock_tf_output['private_key_path']['value']
    assert mock_host.status == HostStatus.PROVISIONED_PENDING_SETUP
    assert mock_host.workspace_name is not None
    assert mock_host.workspace_name.startswith('host-1-')

    mock_rq.get_queue.assert_called_once()
    mock_queue.enqueue.assert_called_once_with(
        setup_host_ansible,
        args=[mock_host.id],
        kwargs={'lock_token': None},
        job_timeout=1200,
        delay=60
    )

    assert f"Host {mock_host.id} Terraform provisioning complete" in result


@patch(f'{TASK_LOGIC_MODULE}._run_terraform_command')
@patch(f'{TASK_LOGIC_MODULE}.run_terraform_with_retry')
@patch(f'{TASK_LOGIC_MODULE}.os.path.isdir', return_value=True)
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value='/usr/bin/terraform')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
@patch(f'{TASK_LOGIC_MODULE}.rq')
def test_provision_host_apply_fails(
    mock_rq, mock_get_job, mock_append_log, mock_session, mock_which,
    mock_isdir, mock_run_tf_retry, mock_run_tf, test_app
):
    """Test provision_host when terraform apply fails."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_host_data)
    mock_session.get.return_value = mock_host

    mock_run_tf.side_effect = [
        ('Init success', None),           # init
        (None, 'Workspace not found'),    # select fails
        ('Created', None),                # new
        ('Selected', None),               # select again
    ]
    mock_run_tf_retry.side_effect = [
        (None, 'Terraform command failed (RC: 1)'),  # apply fails
    ]

    result = provision_host(mock_host.id)

    assert mock_host.status == HostStatus.ERROR
    mock_rq.get_queue.assert_not_called()
    assert 'Error during terraform apply' in result


@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value=None)
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
def test_provision_host_terraform_not_found(mock_append_log, mock_session, mock_which, mock_get_job, test_app):
    """Test provision_host when terraform executable is not found."""
    mock_job = MagicMock(); mock_job.id = 'test-job-tf-not-found'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_host_data)
    mock_session.get.return_value = mock_host

    result = provision_host(mock_host.id)

    mock_which.assert_called_once_with("terraform")
    assert "Error: Terraform executable not found" in result
    assert mock_host.status == HostStatus.ERROR
    mock_append_log.assert_called_once_with(mock_host, "Task failed: Terraform executable not found in PATH.")
    mock_session.commit.assert_called_once()


@patch(f'{TASK_LOGIC_MODULE}.os.path.isdir', side_effect=lambda p: 'terraform' not in str(p))
@patch(f'{TASK_LOGIC_MODULE}.shutil.which', return_value='/usr/bin/terraform')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_provision_host_tf_dir_not_found(
    mock_get_job, mock_append_log, mock_session, mock_which, mock_isdir, test_app
):
    """Test provision_host when Terraform root directory is not found."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_host = Host(**mock_host_data)
    mock_session.get.return_value = mock_host

    result = provision_host(mock_host.id)

    assert mock_isdir.called
    assert mock_host.status == HostStatus.ERROR
    assert f"Error during host {mock_host.id} provisioning" in result
    assert "Terraform root directory not found" in result


@patch('ui.task_lock.release_lock')
@patch('ui.tasks.provision_host_logic', return_value='terraform failed')
def test_provision_host_releases_lock_on_error_return(mock_logic, mock_release, test_app):
    """provision_host must release the host lock even when logic returns an error string."""
    result = provision_host(1, lock_token='tok-123')

    assert result == 'terraform failed'
    mock_release.assert_called_once_with('host', 1, 'tok-123')


@patch('ui.task_lock.release_lock')
@patch('ui.tasks.provision_host_logic', return_value='ok')
def test_provision_host_preserves_lock_for_delayed_setup(
    mock_logic, mock_release, test_app
):
    """provision_host must keep the host lock when setup is still pending."""
    with test_app.app_context():
        host = Host(
            id=2,
            name='Pending Setup Host',
            provider='vultr',
            status=HostStatus.PROVISIONED_PENDING_SETUP,
        )
        db.session.add(host)
        db.session.commit()

    result = provision_host(2, lock_token='tok-setup')

    assert result == 'ok'
    mock_release.assert_not_called()
