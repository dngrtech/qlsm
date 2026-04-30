"""Tests for the host resize task logic."""
from unittest.mock import MagicMock, patch

import pytest

from ui import create_app, db
from ui.models import Host, HostStatus

TASK_LOGIC_MODULE = "ui.task_logic.terraform_resize"


@pytest.fixture(scope="module")
def test_app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SERVER_NAME": "localhost.test",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(autouse=True)
def use_test_app_context(test_app):
    with patch("ui.task_context.create_app", return_value=test_app):
        yield


MOCK_HOST_DATA = {
    "id": 100,
    "name": "resize-host",
    "provider": "vultr",
    "region": "ewr",
    "machine_size": "vc2-1c-2gb",
    "status": HostStatus.CONFIGURING,
    "workspace_name": "host-100-resize-host",
    "ip_address": "192.0.2.50",
    "logs": None,
}


def _mock_job(mock_get_job):
    mock_job = MagicMock()
    mock_job.id = "resize-job"
    mock_get_job.return_value = mock_job


@patch(f"{TASK_LOGIC_MODULE}._run_terraform_command")
@patch(f"{TASK_LOGIC_MODULE}.run_terraform_with_retry")
@patch(f"{TASK_LOGIC_MODULE}.os.path.isdir", return_value=True)
@patch(f"{TASK_LOGIC_MODULE}.shutil.which", return_value="/usr/bin/terraform")
@patch(f"{TASK_LOGIC_MODULE}.db.session")
@patch(f"{TASK_LOGIC_MODULE}.append_log")
@patch(f"{TASK_LOGIC_MODULE}.get_current_job")
def test_resize_host_success(
    mock_get_job, mock_append_log, mock_session, mock_which,
    mock_isdir, mock_run_tf_retry, mock_run_tf, test_app
):
    """Successful resize applies Terraform and updates machine_size."""
    from ui.task_logic.terraform_resize import resize_host_logic

    _mock_job(mock_get_job)
    host = Host(**MOCK_HOST_DATA)
    mock_session.get.return_value = host
    mock_run_tf.side_effect = [("Init success", None), ("Selected", None)]
    mock_run_tf_retry.return_value = ("Apply complete!", None)

    result = resize_host_logic(100, "vc2-2c-4gb")

    assert host.machine_size == "vc2-2c-4gb"
    assert host.status == HostStatus.ACTIVE
    assert "resize complete" in result.lower()

    apply_args = mock_run_tf_retry.call_args.args[1]
    assert "-var=vultr_plan=vc2-2c-4gb" in apply_args
    assert "-var=instance_name=resize-host" in apply_args
    assert "-var=vultr_region=ewr" in apply_args


@patch(f"{TASK_LOGIC_MODULE}._run_terraform_command")
@patch(f"{TASK_LOGIC_MODULE}.run_terraform_with_retry")
@patch(f"{TASK_LOGIC_MODULE}.os.path.isdir", return_value=True)
@patch(f"{TASK_LOGIC_MODULE}.shutil.which", return_value="/usr/bin/terraform")
@patch(f"{TASK_LOGIC_MODULE}.db.session")
@patch(f"{TASK_LOGIC_MODULE}.append_log")
@patch(f"{TASK_LOGIC_MODULE}.get_current_job")
def test_resize_host_apply_fails_sets_error(
    mock_get_job, mock_append_log, mock_session, mock_which,
    mock_isdir, mock_run_tf_retry, mock_run_tf, test_app
):
    """Terraform apply failure preserves machine_size and marks ERROR."""
    from ui.task_logic.terraform_resize import resize_host_logic

    _mock_job(mock_get_job)
    host = Host(**MOCK_HOST_DATA)
    mock_session.get.return_value = host
    mock_run_tf.side_effect = [("Init success", None), ("Selected", None)]
    mock_run_tf_retry.return_value = (None, "Terraform command failed (RC: 1): boom")

    result = resize_host_logic(100, "vc2-2c-4gb")

    assert host.status == HostStatus.ERROR
    assert host.machine_size == "vc2-1c-2gb"
    assert "Error during terraform apply" in result


@patch(f"{TASK_LOGIC_MODULE}._run_terraform_command")
@patch(f"{TASK_LOGIC_MODULE}.os.path.isdir", return_value=True)
@patch(f"{TASK_LOGIC_MODULE}.shutil.which", return_value="/usr/bin/terraform")
@patch(f"{TASK_LOGIC_MODULE}.db.session")
@patch(f"{TASK_LOGIC_MODULE}.append_log")
@patch(f"{TASK_LOGIC_MODULE}.get_current_job")
def test_resize_host_workspace_missing(
    mock_get_job, mock_append_log, mock_session, mock_which,
    mock_isdir, mock_run_tf, test_app
):
    """Workspace select failure sets ERROR and does not create a workspace."""
    from ui.task_logic.terraform_resize import resize_host_logic

    _mock_job(mock_get_job)
    host = Host(**MOCK_HOST_DATA)
    mock_session.get.return_value = host
    mock_run_tf.side_effect = [("Init success", None), (None, "Workspace not found")]

    result = resize_host_logic(100, "vc2-2c-4gb")

    assert host.status == HostStatus.ERROR
    assert host.machine_size == "vc2-1c-2gb"
    assert "workspace" in result.lower()


@patch(f"{TASK_LOGIC_MODULE}.shutil.which", return_value=None)
@patch(f"{TASK_LOGIC_MODULE}.db.session")
@patch(f"{TASK_LOGIC_MODULE}.append_log")
@patch(f"{TASK_LOGIC_MODULE}.get_current_job")
def test_resize_host_terraform_not_found(
    mock_get_job, mock_append_log, mock_session, mock_which, test_app
):
    """Missing Terraform binary sets ERROR."""
    from ui.task_logic.terraform_resize import resize_host_logic

    _mock_job(mock_get_job)
    host = Host(**MOCK_HOST_DATA)
    mock_session.get.return_value = host

    result = resize_host_logic(100, "vc2-2c-4gb")

    assert host.status == HostStatus.ERROR
    assert "Terraform executable not found" in result


@patch(f"{TASK_LOGIC_MODULE}.db.session")
@patch(f"{TASK_LOGIC_MODULE}.get_current_job")
def test_resize_host_not_found(mock_get_job, mock_session, test_app):
    """Unknown host returns an error string."""
    from ui.task_logic.terraform_resize import resize_host_logic

    _mock_job(mock_get_job)
    mock_session.get.return_value = None

    result = resize_host_logic(99999, "vc2-2c-4gb")

    assert "not found" in result.lower()


@patch(f"{TASK_LOGIC_MODULE}.db.session")
@patch(f"{TASK_LOGIC_MODULE}.append_log")
@patch(f"{TASK_LOGIC_MODULE}.get_current_job")
def test_resize_host_requires_configuring_status(
    mock_get_job, mock_append_log, mock_session, test_app
):
    """Task bails if the route did not set CONFIGURING first."""
    from ui.task_logic.terraform_resize import resize_host_logic

    _mock_job(mock_get_job)
    host = Host(**{**MOCK_HOST_DATA, "status": HostStatus.ACTIVE})
    mock_session.get.return_value = host

    result = resize_host_logic(100, "vc2-2c-4gb")

    assert host.status == HostStatus.ERROR
    assert host.machine_size == "vc2-1c-2gb"
    assert "configuring" in result.lower()
