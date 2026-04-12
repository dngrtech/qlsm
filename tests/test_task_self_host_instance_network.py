import pytest
from unittest.mock import MagicMock, patch

from ui import create_app
from ui.models import Host, QLInstance, InstanceStatus
from ui.task_logic.ansible_runner import SimpleAnsibleResult
from ui.tasks import (
    apply_instance_config,
    delete_instance,
    deploy_instance,
    reconfigure_instance_lan_rate,
    start_instance,
)

TASK_LOGIC_MODULE = 'ui.task_logic.ansible_instance_mgmt'


@pytest.fixture(scope='module')
def test_app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        yield app


def _self_host(instances):
    host = MagicMock(spec=Host)
    host.provider = 'self'
    host.name = 'self-host'
    host.ip_address = '172.17.0.1'
    host.ssh_user = 'rage'
    host.ssh_key_path = '/tmp/self-key'
    host.instances = instances
    return host


def _instance(instance_id=1, port=27960, lan_rate_enabled=True):
    inst = MagicMock(spec=QLInstance)
    inst.id = instance_id
    inst.port = port
    inst.hostname = 'Self Host Server'
    inst.status = InstanceStatus.IDLE
    inst.zmq_rcon_port = 28888
    inst.zmq_rcon_password = 'rcon'
    inst.zmq_stats_port = 29999
    inst.zmq_stats_password = 'stats'
    inst.qlx_plugins = None
    inst.lan_rate_enabled = lan_rate_enabled
    return inst


def _wire_host(instances):
    host = _self_host(instances)
    for inst in instances:
        inst.host = host
    return host


def _assert_helper_extravars(mock_run, expected_lan_ports):
    extravars = mock_run.call_args.kwargs['extravars']
    assert extravars['firewall_mode'] == 'helper'
    assert extravars['qlsm_network_rules']['lan_rate']['udp_ports'] == expected_lan_ports


def _assert_self_host_redis_qlds_args(mock_run):
    qlds_args = mock_run.call_args.kwargs['extravars']['qlds_args']
    assert '+set qlx_redisAddress "127.0.0.1:6379"' in qlds_args
    assert '+set qlx_redisPassword "shared-secret"' in qlds_args


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_deploy_self_host_passes_helper_network_state(
    mock_job, mock_session, mock_log, mock_zmq, mock_run, test_app, monkeypatch
):
    monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
    inst = _instance()
    _wire_host([inst])
    mock_job.return_value.id = 'job'
    mock_session.get.return_value = inst
    mock_run.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    deploy_instance(inst.id)

    _assert_helper_extravars(mock_run, [27960])
    _assert_self_host_redis_qlds_args(mock_run)


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_start_self_host_passes_helper_network_state(mock_job, mock_session, mock_log, mock_run, test_app):
    inst = _instance()
    _wire_host([inst])
    mock_job.return_value.id = 'job'
    mock_session.get.return_value = inst
    mock_run.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    start_instance(inst.id)

    _assert_helper_extravars(mock_run, [27960])


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_apply_config_self_host_passes_helper_network_state(
    mock_job, mock_session, mock_log, mock_zmq, mock_run, test_app, monkeypatch
):
    monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
    inst = _instance()
    _wire_host([inst])
    mock_job.return_value.id = 'job'
    mock_session.get.return_value = inst
    mock_run.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    apply_instance_config(inst.id)

    _assert_helper_extravars(mock_run, [27960])
    _assert_self_host_redis_qlds_args(mock_run)


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}._prepare_instance_zmq')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_reconfigure_self_host_passes_helper_network_state(
    mock_job, mock_session, mock_log, mock_zmq, mock_run, test_app, monkeypatch
):
    monkeypatch.setenv("REDIS_PASSWORD", "shared-secret")
    inst = _instance()
    _wire_host([inst])
    mock_job.return_value.id = 'job'
    mock_session.get.return_value = inst
    mock_run.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    reconfigure_instance_lan_rate(inst.id)

    _assert_helper_extravars(mock_run, [27960])
    _assert_self_host_redis_qlds_args(mock_run)


@patch(f'{TASK_LOGIC_MODULE}._run_ansible_playbook')
@patch(f'{TASK_LOGIC_MODULE}.append_log')
@patch(f'{TASK_LOGIC_MODULE}.db.session')
@patch(f'{TASK_LOGIC_MODULE}.get_current_job')
def test_delete_self_host_excludes_deleted_instance_from_network_state(mock_job, mock_session, mock_log, mock_run, test_app):
    deleting = _instance(1, 27960, True)
    kept = _instance(2, 27961, True)
    _wire_host([deleting, kept])
    mock_job.return_value.id = 'job'
    mock_session.get.return_value = deleting
    mock_run.return_value = (SimpleAnsibleResult(0, 'ok', ''), None)

    delete_instance(deleting.id)

    _assert_helper_extravars(mock_run, [27961])
