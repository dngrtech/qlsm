import pytest
from unittest.mock import patch, MagicMock

from ui import create_app, db


@pytest.fixture(scope='module')
def test_app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RCON_ENABLED': False,
    })
    with app.app_context():
        yield app


@pytest.fixture(autouse=True)
def use_test_app_context(test_app):
    with patch('ui.task_context.create_app', return_value=test_app):
        yield


@patch('ui.task_lock.release_lock')
@patch('ui.tasks.restart_instance_logic')
def test_restart_instance_releases_lock_on_success(mock_logic, mock_release, test_app):
    """Task must release lock in finally block on success."""
    mock_logic.return_value = "ok"
    from ui.tasks import restart_instance
    with test_app.app_context():
        restart_instance(1, lock_token='tok-123')
    mock_release.assert_called_once_with('instance', 1, 'tok-123')


@patch('ui.task_lock.release_lock')
@patch('ui.tasks.restart_instance_logic', side_effect=RuntimeError("boom"))
def test_restart_instance_releases_lock_on_failure(mock_logic, mock_release, test_app):
    """Task must release lock in finally block even on failure."""
    from ui.tasks import restart_instance
    with test_app.app_context():
        with pytest.raises(RuntimeError):
            restart_instance(1, lock_token='tok-456')
    mock_release.assert_called_once_with('instance', 1, 'tok-456')


@patch('ui.task_lock.release_lock')
@patch('ui.tasks.restart_instance_logic')
def test_no_release_when_no_lock_token(mock_logic, mock_release, test_app):
    """Task must not call release_lock when lock_token is None."""
    mock_logic.return_value = "ok"
    from ui.tasks import restart_instance
    with test_app.app_context():
        restart_instance(1)
    mock_release.assert_not_called()


def test_rerun_task_timeout_constants_match_rq_job_timeouts():
    from ui import tasks

    assert tasks.RERUN_CLOUD_SETUP_TIMEOUT == 3600
    assert tasks.RERUN_STANDALONE_SETUP_TIMEOUT == 1200
    assert tasks.RERUN_SETUP_LOCK_RELEASE_BUFFER == 60
    assert tasks.rerun_host_setup_ansible.helper.timeout == 3600
    assert tasks.rerun_standalone_host_setup.helper.timeout == 1200


@pytest.mark.parametrize(
    ("task_name", "logic_name"),
    [
        ("rerun_host_setup_ansible", "setup_host_ansible_logic"),
        ("rerun_standalone_host_setup", "setup_standalone_host_logic"),
    ],
)
@pytest.mark.parametrize("raises", [False, True], ids=["success", "exception"])
def test_rerun_tasks_release_instance_locks_before_host_lock(
    task_name, logic_name, raises, test_app
):
    from ui import tasks

    events = []

    def run_logic(*args, **kwargs):
        if raises:
            raise RuntimeError("setup exploded")
        return "ok"

    with patch.object(tasks, logic_name, side_effect=run_logic), \
         patch(
             'ui.task_lock.release_locks',
             side_effect=lambda entity_type, ids, token: events.append(
                 ("instances", entity_type, ids, token)
             ),
         ), \
         patch(
             'ui.task_lock.release_lock',
             side_effect=lambda entity_type, entity_id, token: events.append(
                 ("host", entity_type, entity_id, token)
             ),
         ):
        task = getattr(tasks, task_name)
        with test_app.app_context():
            if raises:
                with pytest.raises(RuntimeError, match="setup exploded"):
                    task(
                        7,
                        lock_token="rerun-token",
                        locked_instance_ids=[3, 1],
                    )
            else:
                assert task(
                    7,
                    lock_token="rerun-token",
                    locked_instance_ids=[3, 1],
                ) == "ok"

    assert events == [
        ("instances", "instance", [3, 1], "rerun-token"),
        ("host", "host", 7, "rerun-token"),
    ]


@patch('ui.task_logic.terraform_provision.rq')
@patch('ui.task_logic.terraform_provision.db')
@patch('ui.task_logic.terraform_provision.run_terraform_with_retry')
@patch('ui.task_logic.terraform_provision._run_terraform_command')
@patch('ui.task_logic.terraform_provision.append_log')
@patch('ui.task_logic.terraform_provision.get_current_job')
@patch('ui.task_logic.terraform_provision.shutil.which', return_value='/usr/bin/terraform')
def test_provision_passes_lock_token_to_setup(
    mock_which, mock_job, mock_append_log, mock_tf_cmd, mock_tf_retry, mock_db, mock_rq, test_app
):
    """provision_host_logic must forward lock_token to setup_host_ansible enqueue."""
    from ui.task_logic.terraform_provision import provision_host_logic
    from ui.models import Host, HostStatus

    mock_job.return_value = MagicMock(id='job-1')
    mock_host = MagicMock(spec=Host)
    mock_host.id = 1
    mock_host.name = 'test'
    mock_host.provider = 'vultr'
    mock_host.status = HostStatus.PENDING
    mock_db.session.get.return_value = mock_host

    # Simulate successful terraform workflow
    mock_tf_cmd.return_value = ('ok', None)
    mock_tf_retry.return_value = ({'main_ip': {'value': '1.2.3.4'}, 'private_key_path': {'value': '/key'}}, None)

    mock_queue = MagicMock()
    mock_rq.get_queue.return_value = mock_queue

    with test_app.app_context():
        provision_host_logic(1, lock_token='tok-workflow')

    # Verify setup_host_ansible was enqueued with lock_token
    mock_queue.enqueue.assert_called_once()
    call_kwargs = mock_queue.enqueue.call_args
    assert call_kwargs.kwargs.get('kwargs', {}).get('lock_token') == 'tok-workflow'
