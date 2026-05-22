import pytest
from unittest.mock import MagicMock, patch
from ui import create_app
from ui.models import Host, QLInstance
from ui.task_logic.ansible_instance_mgmt import REDIS_UNIX_SOCKET_PATH


@pytest.fixture(scope='module')
def test_app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with app.app_context():
        yield app


def _make_instance(provider='vultr', redis_unix_socket=False):
    host = MagicMock(spec=Host)
    host.provider = provider
    host.redis_unix_socket = redis_unix_socket
    instance = MagicMock(spec=QLInstance)
    instance.host = host
    return instance


# --- Cloud / Standalone: TCP (flag False) ---

def test_cloud_tcp_injects_nothing(test_app):
    """Cloud host with TCP flag: no redis args (minqlx default works)."""
    from ui.task_logic.ansible_instance_mgmt import _redis_args
    instance = _make_instance(provider='vultr', redis_unix_socket=False)
    assert _redis_args(instance) == []


def test_standalone_tcp_injects_nothing(test_app):
    """Standalone host with TCP flag: no redis args."""
    from ui.task_logic.ansible_instance_mgmt import _redis_args
    instance = _make_instance(provider='standalone', redis_unix_socket=False)
    assert _redis_args(instance) == []


# --- Cloud / Standalone: Socket (flag True) ---

def test_cloud_socket_injects_socket_args(test_app):
    """Cloud host with socket flag: socket path + unix socket flag, no password."""
    from ui.task_logic.ansible_instance_mgmt import _redis_args
    instance = _make_instance(provider='vultr', redis_unix_socket=True)
    args = _redis_args(instance)
    assert f'+set qlx_redisAddress "{REDIS_UNIX_SOCKET_PATH}"' in args
    assert '+set qlx_redisUnixSocket 1' in args
    assert not any('redisPassword' in a for a in args)


def test_standalone_socket_injects_socket_args(test_app):
    """Standalone host with socket flag: socket path + unix socket flag, no password."""
    from ui.task_logic.ansible_instance_mgmt import _redis_args
    instance = _make_instance(provider='standalone', redis_unix_socket=True)
    args = _redis_args(instance)
    assert f'+set qlx_redisAddress "{REDIS_UNIX_SOCKET_PATH}"' in args
    assert '+set qlx_redisUnixSocket 1' in args
    assert not any('redisPassword' in a for a in args)


# --- Self-host: always TCP + password ---

@patch.dict('os.environ', {'REDIS_PASSWORD': 'secretpass'})
def test_self_host_tcp_injects_address_and_password(test_app):
    """Self-host always injects TCP address + password regardless of flag."""
    from ui.task_logic.ansible_instance_mgmt import _redis_args
    instance = _make_instance(provider='self', redis_unix_socket=False)
    args = _redis_args(instance)
    assert '+set qlx_redisAddress "127.0.0.1:6379"' in args
    assert '+set qlx_redisPassword "secretpass"' in args


@patch.dict('os.environ', {'REDIS_PASSWORD': 'secretpass'})
def test_self_host_socket_flag_true_still_uses_tcp(test_app):
    """Self-host with socket flag True: still uses TCP (Docker Redis, no socket possible)."""
    from ui.task_logic.ansible_instance_mgmt import _redis_args
    instance = _make_instance(provider='self', redis_unix_socket=True)
    args = _redis_args(instance)
    assert '+set qlx_redisAddress "127.0.0.1:6379"' in args
    assert '+set qlx_redisPassword "secretpass"' in args
    assert not any('UnixSocket' in a for a in args)


@patch.dict('os.environ', {}, clear=True)
def test_self_host_missing_password_raises(test_app):
    """Self-host with no REDIS_PASSWORD raises ValueError."""
    from ui.task_logic.ansible_instance_mgmt import _redis_args
    instance = _make_instance(provider='self', redis_unix_socket=False)
    with pytest.raises(ValueError, match="Redis password"):
        _redis_args(instance)
