"""One physical ZMQ stats endpoint must only ever have one subscriber.

Recreating an instance mints a new instance_id but keeps the game port, so the
derived ZMQ stats port is unchanged. Without endpoint-level bookkeeping the
leftover record for the old id keeps its own stats socket open and retries the
PLAIN handshake with the password it was created with, which QLDS logs as a
denial next to the accepted handshake from the current instance.
"""

import asyncio

import pytest

from rcon_service.connection_manager import ConnectionManager
from rcon_service.stats_connection import password_fingerprint

HOST_ID = 1
IP = '194.93.2.143'
STATS_PORT = 30000


class FakeInstanceConnection:
    """Records stats subscribe/unsubscribe traffic without touching ZMQ."""

    def __init__(self):
        self.subscriptions = []
        self.unsubscribe_calls = 0
        self.disconnect_calls = 0
        self.subscribed = False

    async def subscribe_stats(self, ip, stats_port, stats_password):
        self.subscriptions.append((ip, stats_port, stats_password))
        self.subscribed = True

    async def unsubscribe_stats(self):
        self.unsubscribe_calls += 1
        self.subscribed = False

    async def disconnect(self):
        self.disconnect_calls += 1
        self.subscribed = False


@pytest.fixture
def manager():
    mgr = ConnectionManager()
    yield mgr
    if mgr._zmq_context is not None:
        mgr._zmq_context.term()


def _register(mgr, instance_id):
    conn = FakeInstanceConnection()
    mgr._connections[(HOST_ID, instance_id)] = conn
    return conn


def test_new_instance_evicts_old_subscriber_on_the_same_endpoint(manager):
    old = _register(manager, 10)
    new = _register(manager, 11)

    async def scenario():
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'old-password')
        await manager.subscribe_stats(HOST_ID, 11, IP, STATS_PORT, 'new-password')

    asyncio.run(scenario())

    assert old.unsubscribe_calls == 1
    assert not old.subscribed
    assert new.subscriptions == [(IP, STATS_PORT, 'new-password')]
    assert new.subscribed
    assert manager._stats_targets == {(IP, STATS_PORT): (HOST_ID, 11)}


def test_repeat_subscribe_from_the_same_instance_is_not_an_eviction(manager):
    conn = _register(manager, 10)

    async def scenario():
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'password')
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'password')

    asyncio.run(scenario())

    assert conn.unsubscribe_calls == 0
    assert manager._stats_targets == {(IP, STATS_PORT): (HOST_ID, 10)}


def test_instances_on_different_endpoints_coexist(manager):
    first = _register(manager, 10)
    second = _register(manager, 11)

    async def scenario():
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'password-a')
        await manager.subscribe_stats(HOST_ID, 11, IP, STATS_PORT + 2, 'password-b')

    asyncio.run(scenario())

    assert first.unsubscribe_calls == 0
    assert first.subscribed
    assert second.subscribed
    assert manager._stats_targets == {
        (IP, STATS_PORT): (HOST_ID, 10),
        (IP, STATS_PORT + 2): (HOST_ID, 11),
    }


def test_moving_an_instance_to_another_endpoint_releases_the_old_one(manager):
    conn = _register(manager, 10)

    async def scenario():
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'password')
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT + 2, 'password')

    asyncio.run(scenario())

    assert manager._stats_targets == {(IP, STATS_PORT + 2): (HOST_ID, 10)}
    assert conn.unsubscribe_calls == 0


def test_unsubscribe_frees_the_endpoint_for_another_instance(manager):
    old = _register(manager, 10)
    new = _register(manager, 11)

    async def scenario():
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'old-password')
        await manager.unsubscribe_stats(HOST_ID, 10)
        await manager.subscribe_stats(HOST_ID, 11, IP, STATS_PORT, 'new-password')

    asyncio.run(scenario())

    # The endpoint was already free, so taking it must not re-poke the old
    # connection -- one unsubscribe from the explicit call, and no more.
    assert old.unsubscribe_calls == 1
    assert manager._stats_targets == {(IP, STATS_PORT): (HOST_ID, 11)}


def test_disconnect_frees_the_endpoint(manager):
    old = _register(manager, 10)
    new = _register(manager, 11)

    async def scenario():
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'old-password')
        await manager.disconnect(HOST_ID, 10)
        await manager.subscribe_stats(HOST_ID, 11, IP, STATS_PORT, 'new-password')

    asyncio.run(scenario())

    assert old.disconnect_calls == 1
    assert old.unsubscribe_calls == 0
    assert new.subscriptions == [(IP, STATS_PORT, 'new-password')]
    assert manager._stats_targets == {(IP, STATS_PORT): (HOST_ID, 11)}


def test_disconnect_host_frees_every_endpoint_it_owned(manager):
    _register(manager, 10)
    _register(manager, 11)

    async def scenario():
        await manager.subscribe_stats(HOST_ID, 10, IP, STATS_PORT, 'password-a')
        await manager.subscribe_stats(HOST_ID, 11, IP, STATS_PORT + 2, 'password-b')
        await manager.disconnect_host(HOST_ID)

    asyncio.run(scenario())

    assert manager._stats_targets == {}


def test_subscribe_without_a_connection_claims_nothing(manager):
    asyncio.run(manager.subscribe_stats(HOST_ID, 99, IP, STATS_PORT, 'password'))

    assert manager._stats_targets == {}


def test_password_fingerprint_identifies_without_disclosing():
    secret = 'stats638-not-a-real-secret'

    fingerprint = password_fingerprint(secret)

    assert fingerprint == password_fingerprint(secret)
    assert fingerprint != password_fingerprint(secret + 'x')
    assert secret not in fingerprint
    assert len(fingerprint) == 8
    assert password_fingerprint(None) == 'none'
    assert password_fingerprint('') == 'none'
