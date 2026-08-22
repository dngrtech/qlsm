import asyncio

from rcon_service.instance_connection import InstanceConnection
from rcon_service.stats_connection import password_fingerprint


class FakeStatsConnection:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connect_calls = []
        self.disconnect_calls = 0
        type(self).instances.append(self)

    async def connect(self, ip, stats_port, stats_password):
        self.connect_calls.append((ip, stats_port, stats_password))
        return True

    async def disconnect(self):
        self.disconnect_calls += 1


def test_subscribe_stats_reconnects_when_password_changes(monkeypatch):
    FakeStatsConnection.instances = []
    monkeypatch.setattr(
        'rcon_service.instance_connection.StatsConnection',
        FakeStatsConnection,
    )
    connection = InstanceConnection(host_id=1, instance_id=2)

    asyncio.run(connection.subscribe_stats('194.93.2.143', 30000, 'old-password'))
    asyncio.run(connection.subscribe_stats('194.93.2.143', 30000, 'new-password'))

    first, replacement = FakeStatsConnection.instances
    assert first.disconnect_calls == 1
    assert replacement.connect_calls == [
        ('194.93.2.143', 30000, 'new-password'),
    ]


def test_subscribe_stats_keeps_identical_subscription(monkeypatch):
    FakeStatsConnection.instances = []
    monkeypatch.setattr(
        'rcon_service.instance_connection.StatsConnection',
        FakeStatsConnection,
    )
    connection = InstanceConnection(host_id=1, instance_id=2)

    asyncio.run(connection.subscribe_stats('194.93.2.143', 30000, 'same-password'))
    asyncio.run(connection.subscribe_stats('194.93.2.143', 30000, 'same-password'))

    assert len(FakeStatsConnection.instances) == 1
    assert FakeStatsConnection.instances[0].disconnect_calls == 0


def test_password_fingerprint_identifies_without_disclosing():
    """Credential mismatches are reconciled from logs, so the logs must not
    carry the secret."""
    secret = 'not-a-real-stats-password'

    fingerprint = password_fingerprint(secret)

    assert fingerprint == password_fingerprint(secret)
    assert fingerprint != password_fingerprint(secret + 'x')
    assert secret not in fingerprint
    assert password_fingerprint(None) == 'none'
    assert password_fingerprint('') == 'none'
