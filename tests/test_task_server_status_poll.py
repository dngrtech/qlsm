import json

import pytest
from unittest.mock import MagicMock, patch

from ui.database import create_host, create_instance, get_host
from ui.models import HostStatus, InstanceStatus
from ui.task_logic.service_runtime import RuntimeObservation


POLL_MODULE = "ui.task_logic.server_status_poll"


@pytest.fixture(autouse=True)
def _no_runtime_upgrade_reservations():
    """Most tests here mock Host on a bare Flask app with no database, so the
    upgrade-reservation lookup is stubbed; the real lookup is exercised in
    tests/test_host_runtime_upgrade.py."""
    with patch(f"{POLL_MODULE}.reserved_host_ids", return_value=set()):
        yield


def _make_host(id=1, ip="10.0.0.1", ssh_user="ql", ssh_key="/key.pem", ssh_port=22):
    host = MagicMock()
    host.id = id
    host.name = "poll-host"
    host.provider = "standalone"
    host.ip_address = ip
    host.ssh_user = ssh_user
    host.ssh_key_path = ssh_key
    host.ssh_port = ssh_port
    return host


def _make_instance(id=1, port=27960, host_id=1):
    instance = MagicMock()
    instance.id = id
    instance.port = port
    instance.host_id = host_id
    return instance


def test_write_status_to_redis():
    from ui.task_logic.server_status_poll import _write_status_to_redis

    redis_client = MagicMock()
    data = {"map": "campgrounds", "players": []}

    _write_status_to_redis(redis_client, host_id=1, instance_id=5, data=data)

    redis_client.setex.assert_called_once()
    key, ttl, value = redis_client.setex.call_args.args
    assert key == "server:status:1:5"
    assert ttl == 30
    assert json.loads(value) == data


def test_write_status_to_redis_none_deletes_key():
    from ui.task_logic.server_status_poll import _write_status_to_redis

    redis_client = MagicMock()

    _write_status_to_redis(redis_client, host_id=1, instance_id=5, data=None)

    redis_client.delete.assert_called_once_with("server:status:1:5")
    redis_client.setex.assert_not_called()


@patch(f"{POLL_MODULE}.probe_host_runtime")
def test_fetch_and_cache_host_returns_runtime_result_and_preserves_status_value(mock_probe):
    """The cache must receive the status object unchanged, not freshness-filtered data."""
    from ui.task_logic.server_status_poll import _fetch_and_cache_host

    payload = {"map": "campgrounds", "updated": 1}
    observation = RuntimeObservation(payload, "a" * 32, True, 2)
    mock_probe.return_value = {"27960": observation}
    redis_client = MagicMock()
    host = _make_host()
    instances = [_make_instance()]

    result = _fetch_and_cache_host(host, instances, redis_client)

    assert result.active_count == 1
    assert result.observations == {"27960": observation}
    key, _, stored_value = redis_client.setex.call_args.args
    assert key == "server:status:1:1"
    assert json.loads(stored_value) == payload


@patch(f"{POLL_MODULE}.probe_host_runtime", return_value=None)
def test_fetch_and_cache_host_does_not_touch_cache_after_host_probe_failure(mock_probe):
    """A host-level failure is distinct from an empty status and preserves cache state."""
    from ui.task_logic.server_status_poll import _fetch_and_cache_host

    redis_client = MagicMock()

    assert _fetch_and_cache_host(_make_host(), [_make_instance()], redis_client) is None
    redis_client.setex.assert_not_called()
    redis_client.delete.assert_not_called()


@patch(f"{POLL_MODULE}.probe_host_runtime", return_value={})
def test_fetch_and_cache_host_deletes_cache_for_missing_observation(mock_probe):
    """A completed host probe with no port entry preserves the old None/delete behavior."""
    from ui.task_logic.server_status_poll import _fetch_and_cache_host

    redis_client = MagicMock()
    result = _fetch_and_cache_host(_make_host(), [_make_instance()], redis_client)

    assert result.active_count == 0
    redis_client.delete.assert_called_once_with("server:status:1:1")


@patch(f"{POLL_MODULE}._fetch_and_cache_host")
@patch(f"{POLL_MODULE}.Host")
def test_poll_all_hosts_skips_no_running_instances(mock_host_class, mock_fetch):
    """Hosts with no RUNNING/UPDATED instances are skipped."""
    from flask import Flask
    from ui.task_logic.server_status_poll import poll_all_hosts

    app = Flask(__name__)
    instance = _make_instance()
    instance.status = InstanceStatus.IDLE
    host = _make_host()
    host.instances = [instance]
    mock_host_class.query.filter.return_value.all.return_value = [host]
    app.extensions["redis"] = MagicMock()

    with app.app_context():
        poll_all_hosts()

    mock_fetch.assert_not_called()


@patch(f"{POLL_MODULE}.reconcile_runtime_observations")
@patch(f"{POLL_MODULE}._fetch_and_cache_host")
@patch(f"{POLL_MODULE}.Host")
def test_poll_all_hosts_reconciles_completed_host_observations(
    mock_host_class, mock_fetch, mock_reconcile
):
    """Reconciliation runs only after a successful host probe/cache cycle."""
    from flask import Flask
    from ui.task_logic.server_status_poll import HostPollResult, poll_all_hosts

    instance = _make_instance()
    instance.status = InstanceStatus.UPDATED
    host = _make_host()
    host.status = HostStatus.ACTIVE
    host.instances = [instance]
    observations = {"27960": RuntimeObservation({"updated": 2}, "a" * 32, True, 1)}
    mock_host_class.query.filter.return_value.all.return_value = [host]
    mock_fetch.return_value = HostPollResult(active_count=1, observations=observations)
    app = Flask(__name__)
    app.extensions["redis"] = MagicMock()

    with app.app_context():
        poll_all_hosts()

    mock_reconcile.assert_called_once_with([instance], observations)


@patch(f"{POLL_MODULE}._fetch_and_cache_host")
@patch(f"{POLL_MODULE}.Host")
def test_poll_all_hosts_no_redis(mock_host_class, mock_fetch):
    """poll_all_hosts returns early if management Redis is unavailable."""
    from flask import Flask
    from ui.task_logic.server_status_poll import poll_all_hosts

    app = Flask(__name__)

    with app.app_context():
        poll_all_hosts()

    mock_fetch.assert_not_called()
    mock_host_class.query.filter.assert_not_called()


@patch(f"{POLL_MODULE}.probe_host_runtime")
def test_poll_all_hosts_recovers_error_host_when_runtime_probe_succeeds(mock_probe, app):
    """A stale ERROR host with live status should self-heal to ACTIVE."""
    from ui.task_logic.server_status_poll import poll_all_hosts

    payload = {"map": "campgrounds", "updated": 1}
    mock_probe.return_value = {
        "27960": RuntimeObservation(payload, "a" * 32, True, 2),
    }
    redis_client = MagicMock()
    app.extensions["redis"] = redis_client

    with app.app_context():
        host = create_host(
            name="stale-error-host",
            provider="standalone",
            status=HostStatus.ERROR,
            is_standalone=True,
            ssh_user="debian",
            ssh_key_path="/tmp/test-key",
            ssh_port=22,
            ip_address="203.0.113.20",
        )
        instance = create_instance(
            name="live-instance",
            host_id=host.id,
            port=27960,
            hostname="live.example",
        )
        instance.status = InstanceStatus.RUNNING

        poll_all_hosts()

        refreshed = get_host(host.id)
        assert refreshed.status == HostStatus.ACTIVE
        assert "Recovered automatically" in refreshed.logs

    redis_client.setex.assert_called_once()


def test_status_poller_cli_command_exists(app):
    """The status poller CLI command remains registered."""
    with app.app_context():
        assert app.cli.commands.get("run-status-poller") is not None
