import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ui import create_app, db
from ui.models import Host, QLInstance, HostStatus, InstanceStatus
from ui.tasks import deploy_instance
from ui.task_logic.ansible_runner import SimpleAnsibleResult

TASK_LOGIC_MODULE = 'ui.task_logic.ansible_instance_mgmt'

@pytest.fixture(scope='module')
def test_app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        yield app


def _make_mock_instance(instance_id=10, status=InstanceStatus.IDLE):
    mock_host = MagicMock(spec=Host)
    mock_host.name = 'test-host'
    mock_host.ip_address = '1.2.3.4'
    mock_host.ssh_user = 'testuser'
    mock_host.ssh_key_path = '/fake/key.pem'

    mock_instance = MagicMock(spec=QLInstance)
    mock_instance.id = instance_id
    mock_instance.port = 27960
    mock_instance.hostname = 'Test Server'
    mock_instance.status = status
    mock_instance.host = mock_host
    return mock_instance


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_success(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test successful deployment via Ansible."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance

    mock_run_playbook.return_value = (SimpleAnsibleResult(0, 'Ansible stdout', ''), None)

    result = deploy_instance(10)

    mock_session.get.assert_called_once_with(QLInstance, 10)
    mock_prep_zmq.assert_called_once_with(mock_instance)
    mock_run_playbook.assert_called_once()
    assert mock_instance.status == InstanceStatus.RUNNING
    assert mock_session.commit.call_count == 2
    assert mock_append_log.called, "append_log should be called during deploy"
    assert 'deployment successful. Status: RUNNING' in result


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_ansible_failure(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test deploy when Ansible returns non-zero RC."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance

    mock_run_playbook.return_value = (SimpleAnsibleResult(1, 'failure output', 'stderr'), None)

    result = deploy_instance(10)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 2
    assert 'stderr' in result


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_surfaces_ansible_fail_message(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    mock_job = MagicMock(); mock_job.id = 'job'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance
    stdout = (
        'fatal: [test-host]: FAILED! => {"changed": false, "msg": '
        '"QLDS instance directory /home/ql/qlds-27960 already exists."}'
    )
    mock_run_playbook.return_value = (SimpleAnsibleResult(2, stdout, ''), None)

    result = deploy_instance(10)

    assert mock_instance.status == InstanceStatus.ERROR
    assert "QLDS instance directory /home/ql/qlds-27960 already exists." in result


@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_not_found(mock_get_job, mock_session, mock_append_log, test_app):
    """Test deploy when instance is not in DB."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job
    mock_session.get.return_value = None

    result = deploy_instance(99)

    mock_session.get.assert_called_once_with(QLInstance, 99)
    mock_session.commit.assert_not_called()
    assert 'Error: Instance 99 not found' in result


@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_missing_host(mock_get_job, mock_session, mock_append_log, test_app):
    """Test deploy when instance has no associated host."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = MagicMock(spec=QLInstance)
    mock_instance.id = 11
    mock_instance.host = None
    mock_session.get.return_value = mock_instance

    result = deploy_instance(11)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 1
    assert 'Error during instance 11 deployment: Host not found' in result


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._build_qlds_args_string', return_value='mock_qlds_args')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_instance_exception(
    mock_get_job, mock_session, mock_append_log, mock_prep_zmq,
    mock_build_args, mock_run_playbook, test_app
):
    """Test deploy when an exception is raised during playbook execution."""
    mock_job = MagicMock(); mock_job.id = 'test-job-id'
    mock_get_job.return_value = mock_job

    mock_instance = _make_mock_instance()
    mock_session.get.return_value = mock_instance
    mock_run_playbook.side_effect = Exception('Playbook init error')

    result = deploy_instance(10)

    assert mock_instance.status == InstanceStatus.ERROR
    assert mock_session.commit.call_count == 2
    assert 'Playbook init error' in result


# ── _build_qlds_args_string / SYSTEM_PLUGINS tests ──────────────────────────

from ui.task_logic.ansible_instance_mgmt import _build_qlds_args_string


def _make_instance_for_args(**kwargs):
    inst = MagicMock(spec=QLInstance)
    inst.port = kwargs.get('port', 27960)
    inst.hostname = kwargs.get('hostname', 'Test Server')
    inst.zmq_rcon_port = kwargs.get('zmq_rcon_port', 28960)
    inst.zmq_rcon_password = kwargs.get('zmq_rcon_password', 'rconpass')
    inst.zmq_stats_port = kwargs.get('zmq_stats_port', 29960)
    inst.zmq_stats_password = kwargs.get('zmq_stats_password', 'statspass')
    inst.lan_rate_enabled = kwargs.get('lan_rate_enabled', False)
    inst.qlx_plugins = kwargs.get('qlx_plugins', None)
    inst.host = kwargs.get('host', SimpleNamespace(provider='standalone'))
    return inst


def test_build_qlds_args_serverchecker_always_present_when_no_user_plugins(test_app):
    """serverchecker must be in qlx_plugins even when qlx_plugins is None."""
    with test_app.app_context():
        inst = _make_instance_for_args(qlx_plugins=None)
        result = _build_qlds_args_string(inst)
        assert '+set qlx_plugins "serverchecker"' in result


def test_build_qlds_args_serverchecker_prepended_to_user_plugins(test_app):
    """serverchecker must appear first, followed by user-specified plugins."""
    with test_app.app_context():
        inst = _make_instance_for_args(qlx_plugins='balance, ban')
        result = _build_qlds_args_string(inst)
        assert '+set qlx_plugins "serverchecker, balance, ban"' in result


def test_build_qlds_args_serverchecker_not_duplicated(test_app):
    """If user already lists serverchecker, it must not appear twice."""
    with test_app.app_context():
        inst = _make_instance_for_args(qlx_plugins='serverchecker, balance')
        result = _build_qlds_args_string(inst)
        assert result.count('serverchecker') == 1
        assert '+set qlx_plugins "serverchecker, balance"' in result


def test_build_qlds_args_self_host_includes_shared_redis_runtime(test_app, monkeypatch):
    with test_app.app_context():
        monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
        inst = _make_instance_for_args()
        inst.host = SimpleNamespace(provider="self")

        result = _build_qlds_args_string(inst)

        assert '+set qlx_redisAddress "127.0.0.1:6379"' in result
        assert '+set qlx_redisPassword "shared-secret"' in result
        assert '+set qlx_redisDatabase 1' in result


def test_build_qlds_args_non_self_host_does_not_include_shared_redis_runtime(
    test_app, monkeypatch
):
    with test_app.app_context():
        monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
        inst = _make_instance_for_args()
        inst.host = SimpleNamespace(provider="standalone")

        result = _build_qlds_args_string(inst)

        assert "qlx_redisAddress" not in result
        assert "qlx_redisPassword" not in result


def test_build_qlds_args_self_host_requires_redis_password(test_app, monkeypatch):
    with test_app.app_context():
        monkeypatch.delenv("REDIS_PASSWORD", raising=False)
        inst = _make_instance_for_args()
        inst.host = SimpleNamespace(provider="self")

        with pytest.raises(
            ValueError,
            match="Self-host instance Redis password is not configured.",
        ):
            _build_qlds_args_string(inst)
