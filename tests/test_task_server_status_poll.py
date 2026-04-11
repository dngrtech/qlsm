import json
import pytest
from unittest.mock import MagicMock, patch

POLL_MODULE = 'ui.task_logic.server_status_poll'


def _make_host(id=1, ip='10.0.0.1', ssh_user='ql', ssh_key='/key.pem', ssh_port=22):
    h = MagicMock()
    h.id = id
    h.ip_address = ip
    h.ssh_user = ssh_user
    h.ssh_key_path = ssh_key
    h.ssh_port = ssh_port
    return h


def _make_instance(id=1, port=27960, host_id=1):
    i = MagicMock()
    i.id = id
    i.port = port
    i.host_id = host_id
    return i


def test_build_ssh_command_single_instance():
    from ui.task_logic.server_status_poll import _build_ssh_command
    host = _make_host()
    instances = [_make_instance(port=27960)]
    cmd = _build_ssh_command(host, instances)
    assert cmd[0] == 'ssh'
    assert '-i' in cmd
    assert '/key.pem' in cmd
    assert 'StrictHostKeyChecking=no' in cmd
    assert 'BatchMode=yes' in cmd
    assert 'ConnectTimeout=5' in cmd
    assert '10.0.0.1' in cmd
    full_cmd = ' '.join(cmd)
    assert '27960' in full_cmd
    assert 'redis' in full_cmd.lower()


def test_build_ssh_command_multiple_instances():
    from ui.task_logic.server_status_poll import _build_ssh_command
    host = _make_host()
    instances = [_make_instance(port=27960), _make_instance(port=27961)]
    cmd = _build_ssh_command(host, instances)
    full_cmd = ' '.join(cmd)
    assert '27960' in full_cmd
    assert '27961' in full_cmd
    assert str(27960 - 27959) in full_cmd  # db=1
    assert str(27961 - 27959) in full_cmd  # db=2


def test_build_ssh_command_self_host_uses_management_target(monkeypatch):
    from ui.task_logic.server_status_poll import _build_ssh_command

    host = _make_host(ip='203.0.113.10')
    host.provider = 'self'
    monkeypatch.setattr(
        'ui.task_logic.server_status_poll.resolve_self_host_management_target',
        lambda: 'host.docker.internal',
    )

    cmd = _build_ssh_command(host, [_make_instance(port=27960)])

    assert 'host.docker.internal' in cmd
    assert '203.0.113.10' not in cmd


def test_build_ssh_command_standalone_uses_connect_address():
    from ui.task_logic.server_status_poll import _build_ssh_command

    host = _make_host(ip='10.0.0.1')
    host.provider = 'standalone'
    cmd = _build_ssh_command(host, [_make_instance(port=27960)])

    assert '10.0.0.1' in cmd


def test_parse_ssh_output_valid():
    from ui.task_logic.server_status_poll import _parse_ssh_output
    payload = {'map': 'campgrounds', 'players': [], 'maxplayers': 16, 'state': 'warmup'}
    output = json.dumps({'27960': payload})
    result = _parse_ssh_output(output)
    assert result == {'27960': payload}


def test_parse_ssh_output_null_instance():
    from ui.task_logic.server_status_poll import _parse_ssh_output
    output = json.dumps({'27960': None, '27961': {'map': 'dm6'}})
    result = _parse_ssh_output(output)
    assert result['27960'] is None
    assert result['27961']['map'] == 'dm6'


def test_parse_ssh_output_invalid_json():
    from ui.task_logic.server_status_poll import _parse_ssh_output
    result = _parse_ssh_output('not json at all')
    assert result == {}


def test_parse_ssh_output_empty():
    from ui.task_logic.server_status_poll import _parse_ssh_output
    result = _parse_ssh_output('')
    assert result == {}


def test_write_status_to_redis():
    from ui.task_logic.server_status_poll import _write_status_to_redis
    mock_redis = MagicMock()
    data = {'map': 'campgrounds', 'players': []}
    _write_status_to_redis(mock_redis, host_id=1, instance_id=5, data=data)
    mock_redis.setex.assert_called_once()
    args = mock_redis.setex.call_args
    key = args[0][0]
    assert key == 'server:status:1:5'
    ttl = args[0][1]
    assert ttl == 30
    stored = json.loads(args[0][2])
    assert stored['map'] == 'campgrounds'


def test_write_status_to_redis_none_deletes_key():
    from ui.task_logic.server_status_poll import _write_status_to_redis
    mock_redis = MagicMock()
    _write_status_to_redis(mock_redis, host_id=1, instance_id=5, data=None)
    mock_redis.delete.assert_called_once_with('server:status:1:5')
    mock_redis.setex.assert_not_called()


@patch(f'{POLL_MODULE}.subprocess.run')
def test_fetch_and_cache_host_success(mock_run):
    from ui.task_logic.server_status_poll import _fetch_and_cache_host
    payload = {'map': 'campgrounds', 'players': [], 'maxplayers': 16}
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({'27960': payload}), stderr='')
    mock_redis = MagicMock()
    host = _make_host()
    instances = [_make_instance(port=27960)]
    _fetch_and_cache_host(host, instances, mock_redis)
    mock_redis.setex.assert_called_once()
    key = mock_redis.setex.call_args[0][0]
    assert key == 'server:status:1:1'


@patch(f'{POLL_MODULE}.subprocess.run')
def test_fetch_and_cache_host_ssh_failure(mock_run):
    from ui.task_logic.server_status_poll import _fetch_and_cache_host
    mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='Connection refused')
    mock_redis = MagicMock()
    host = _make_host()
    instances = [_make_instance(port=27960)]
    _fetch_and_cache_host(host, instances, mock_redis)
    # On SSH failure, nothing written to Redis
    mock_redis.setex.assert_not_called()
    mock_redis.delete.assert_not_called()


@patch(f'{POLL_MODULE}.subprocess.run')
def test_fetch_and_cache_host_timeout(mock_run):
    import subprocess
    from ui.task_logic.server_status_poll import _fetch_and_cache_host
    mock_run.side_effect = subprocess.TimeoutExpired(cmd='ssh', timeout=10)
    mock_redis = MagicMock()
    host = _make_host()
    instances = [_make_instance(port=27960)]
    # Should not raise — timeout is handled gracefully
    _fetch_and_cache_host(host, instances, mock_redis)
    mock_redis.setex.assert_not_called()


@patch(f'{POLL_MODULE}.subprocess.run')
def test_fetch_and_cache_host_missing_port_in_response(mock_run):
    """Instance port not in SSH response — status should be deleted (None data)."""
    from ui.task_logic.server_status_poll import _fetch_and_cache_host
    # SSH returns data for 27961 but not 27960
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({'27961': {'map': 'dm6'}}), stderr='')
    mock_redis = MagicMock()
    host = _make_host()
    instances = [_make_instance(id=1, port=27960)]
    _fetch_and_cache_host(host, instances, mock_redis)
    # 27960 not in response → data=None → delete
    mock_redis.delete.assert_called_once_with('server:status:1:1')


@patch(f'{POLL_MODULE}._fetch_and_cache_host')
@patch(f'{POLL_MODULE}.Host')
def test_poll_all_hosts_skips_no_running_instances(mock_host_class, mock_fetch):
    """Hosts with no RUNNING/UPDATED instances are skipped."""
    from ui.task_logic.server_status_poll import poll_all_hosts
    from flask import Flask
    app = Flask(__name__)
    mock_instance = _make_instance()
    mock_instance.status = 'idle'  # Not running

    mock_host = _make_host()
    mock_host.instances = [mock_instance]
    mock_host_class.query.filter_by.return_value.all.return_value = [mock_host]

    mock_redis = MagicMock()
    app.extensions['redis'] = mock_redis

    with app.app_context():
        poll_all_hosts()

    mock_fetch.assert_not_called()


@patch(f'{POLL_MODULE}._fetch_and_cache_host')
@patch(f'{POLL_MODULE}.Host')
def test_poll_all_hosts_no_redis(mock_host_class, mock_fetch):
    """poll_all_hosts returns early if Redis unavailable."""
    from ui.task_logic.server_status_poll import poll_all_hosts
    from flask import Flask
    app = Flask(__name__)
    # No redis in extensions

    with app.app_context():
        poll_all_hosts()

    mock_fetch.assert_not_called()
    mock_host_class.query.filter_by.assert_not_called()


def test_status_poller_cli_command_exists(app):
    """The 'run-status-poller' CLI command must be registered."""
    with app.app_context():
        cmd = app.cli.commands.get('run-status-poller')
        assert cmd is not None, "CLI command 'run-status-poller' not registered"
