import asyncio
from unittest.mock import patch

import zmq

from rcon_service.instance_connection import InstanceConnection
from rcon_service.service import RconService


class _FakeSocket:
    def __init__(self):
        self.options = {}
        self.plain_username = None
        self.plain_password = None
        self.zap_domain = None
        self.identity = None
        self.endpoint = None
        self.sent = []

    def setsockopt(self, option, value):
        self.options[option] = value

    def connect(self, endpoint):
        self.endpoint = endpoint

    async def send_string(self, value):
        self.sent.append(value)

    def close(self):
        pass


class _FakeContext:
    def __init__(self):
        self.created = []

    def socket(self, socket_type):
        assert socket_type == zmq.DEALER
        sock = _FakeSocket()
        self.created.append(sock)
        return sock


class _DummyTask:
    def done(self):
        return True

    def cancel(self):
        pass


def _discard_task(coro):
    coro.close()
    return _DummyTask()


def test_service_passes_self_host_flag_to_manager():
    service = RconService(redis_url='redis://example.invalid:6379/0')

    class _Manager:
        def __init__(self):
            self.calls = []

        async def connect(self, *args):
            self.calls.append(args)

    manager = _Manager()
    service._manager = manager

    asyncio.run(service._process_command(1, 2, {
        'action': 'connect',
        'ip': 'host.docker.internal',
        'rcon_port': 28888,
        'rcon_password': 'secret',
        'self_host': True,
    }))

    assert manager.calls == [
        (1, 2, 'host.docker.internal', 28888, 'secret', True),
    ]


def test_instance_connection_uses_non_immediate_mode_for_self_host():
    context = _FakeContext()
    conn = InstanceConnection(1, 2, zmq_context=context)

    with patch('rcon_service.instance_connection.asyncio.create_task', side_effect=_discard_task):
        assert asyncio.run(conn.connect('host.docker.internal', 28888, 'secret', self_host=True)) is True

    sock = context.created[0]
    assert sock.options[zmq.IMMEDIATE] == 0
    assert sock.endpoint == 'tcp://host.docker.internal:28888'
    assert sock.sent == ['register']


def test_instance_connection_keeps_immediate_mode_for_remote_hosts():
    context = _FakeContext()
    conn = InstanceConnection(1, 2, zmq_context=context)

    with patch('rcon_service.instance_connection.asyncio.create_task', side_effect=_discard_task):
        assert asyncio.run(conn.connect('45.76.21.225', 28888, 'secret', self_host=False)) is True

    sock = context.created[0]
    assert sock.options[zmq.IMMEDIATE] == 1
    assert sock.endpoint == 'tcp://45.76.21.225:28888'
