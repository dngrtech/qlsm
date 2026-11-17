import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import auth_headers, make_user
from ui import db
from ui.database import create_host, get_host
from ui.models import HostStatus
from ui.task_logic.host_os_version import backfill_host_os_version_logic, detect_self_host_os_version

OS_RELEASE = 'NAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n'


def _host(**overrides):
    fields = dict(
        name='legacy', provider='standalone', ip_address='192.0.2.10',
        ssh_user='root', ssh_key_path='/keys/legacy', ssh_port=22,
        os_type='ubuntu', status=HostStatus.ACTIVE,
    )
    fields.update(overrides)
    return create_host(**fields)


def _ssh_result(stdout='', returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr='boom')


# --- backfill_host_os_version_logic ---

@patch('ui.task_logic.host_os_version.subprocess.run', return_value=_ssh_result(OS_RELEASE))
def test_backfill_stores_version_id(mock_run, app):
    with app.app_context():
        host = _host()
        assert backfill_host_os_version_logic(host.id) == '24.04'
        assert get_host(host.id).os_version == '24.04'
        assert mock_run.call_args[0][0][-1] == 'cat /etc/os-release'


@patch('ui.task_logic.host_os_version.subprocess.run', return_value=_ssh_result('', returncode=255))
def test_backfill_leaves_version_empty_when_ssh_fails(mock_run, app):
    with app.app_context():
        host = _host()
        assert backfill_host_os_version_logic(host.id) is None
        assert get_host(host.id).os_version is None


@patch('ui.task_logic.host_os_version.subprocess.run',
       side_effect=subprocess.TimeoutExpired(cmd='ssh', timeout=20))
def test_backfill_survives_ssh_timeout(mock_run, app):
    with app.app_context():
        host = _host()
        assert backfill_host_os_version_logic(host.id) is None


@patch('ui.task_logic.host_os_version.subprocess.run', return_value=_ssh_result('ID=debian\n'))
def test_backfill_without_version_id_stores_nothing(mock_run, app):
    with app.app_context():
        host = _host()
        assert backfill_host_os_version_logic(host.id) is None
        assert get_host(host.id).os_version is None


@patch('ui.task_logic.host_os_version.subprocess.run')
def test_backfill_skips_host_that_already_has_a_version(mock_run, app):
    with app.app_context():
        host = _host(os_version='22.04')
        backfill_host_os_version_logic(host.id)
        mock_run.assert_not_called()


@patch('ui.task_logic.host_os_version.detect_self_host_os_version', return_value='24.04')
@patch('ui.task_logic.host_os_version.subprocess.run')
def test_backfill_self_host_reads_host_init_file_not_ssh(mock_run, mock_self, app):
    with app.app_context():
        host = _host(provider='self')
        assert backfill_host_os_version_logic(host.id) == '24.04'
        assert get_host(host.id).os_version == '24.04'
        mock_run.assert_not_called()


@pytest.mark.parametrize('content, expected', [
    ('{"os_type":"ubuntu","pretty_name":"Ubuntu 24.04.1 LTS","version_id":"24.04"}', '24.04'),
    ('{"os_type":"ubuntu","pretty_name":"Ubuntu 24.04.1 LTS"}', None),  # written by older host-init
    ('{"os_type":"ubuntu","pretty_name":"x","version_id":""}', None),
    ('not json', None),
    ('[]', None),
])
def test_detect_self_host_os_version(tmp_path, content, expected):
    path = tmp_path / 'host-os-type'
    path.write_text(content)
    assert detect_self_host_os_version(str(path)) == expected


def test_detect_self_host_os_version_missing_file(tmp_path):
    assert detect_self_host_os_version(str(tmp_path / 'absent')) is None


# --- GET /api/hosts/ enqueues the backfill ---

@pytest.fixture
def headers(app):
    make_user(app, 'osadmin', 'osadminp1')
    return auth_headers(app, 'osadmin')


@pytest.fixture
def fake_redis(app):
    seen = set()
    redis = MagicMock()
    redis.get.return_value = None  # JWT blocklist lookup: token not revoked
    redis.set.side_effect = lambda key, *a, **kw: not (key in seen or seen.add(key))
    app.extensions['redis'] = redis
    return redis


@patch('ui.routes.host_routes.enqueue_task')
def test_list_enqueues_only_active_hosts_without_version(mock_enqueue, client, app, headers, fake_redis):
    with app.app_context():
        legacy = _host(name='legacy').id
        _host(name='known', os_version='12')
        _host(name='pending', status=HostStatus.PENDING)
        self_host = _host(name='self-host', provider='self').id

    assert client.get('/api/hosts/', headers=headers).status_code == 200
    assert sorted(c.args[1] for c in mock_enqueue.call_args_list) == sorted([legacy, self_host])


@patch('ui.routes.host_routes.enqueue_task')
def test_list_probes_each_host_at_most_once_per_hour(mock_enqueue, client, app, headers, fake_redis):
    with app.app_context():
        _host()

    client.get('/api/hosts/', headers=headers)
    client.get('/api/hosts/', headers=headers)
    assert mock_enqueue.call_count == 1
    assert fake_redis.set.call_args.kwargs == {'nx': True, 'ex': 3600}


@patch('ui.routes.host_routes.enqueue_task', side_effect=RuntimeError('queue down'))
def test_list_still_returns_hosts_when_enqueue_fails(mock_enqueue, client, app, headers, fake_redis):
    with app.app_context():
        _host()

    response = client.get('/api/hosts/', headers=headers)
    assert response.status_code == 200
    assert [h['name'] for h in response.get_json()['data']] == ['legacy']
