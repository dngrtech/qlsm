from types import SimpleNamespace
import threading
import time
from unittest.mock import patch

from flask import request
from flask_jwt_extended import create_access_token


def _make_host(provider, ip='203.0.113.10'):
    return SimpleNamespace(provider=provider, ip_address=ip)


@patch(
    'ui.socketio_events.resolve_self_host_management_target',
    return_value='host.docker.internal',
)
def test_rcon_target_for_self_host_uses_management_target(mock_target):
    from ui.socketio_events import _rcon_target_for_host

    target = _rcon_target_for_host(_make_host('self'))

    assert target == 'host.docker.internal'
    mock_target.assert_called_once_with()


@patch('ui.socketio_events.resolve_self_host_management_target')
def test_rcon_target_for_standalone_host_uses_ip_address(mock_target):
    from ui.socketio_events import _rcon_target_for_host

    target = _rcon_target_for_host(_make_host('standalone', ip='10.0.0.1'))

    assert target == '10.0.0.1'
    mock_target.assert_not_called()


@patch('ui.socketio_events.resolve_self_host_management_target')
def test_rcon_target_for_cloud_host_uses_ip_address(mock_target):
    from ui.socketio_events import _rcon_target_for_host

    target = _rcon_target_for_host(_make_host('vultr', ip='45.76.1.100'))

    assert target == '45.76.1.100'
    mock_target.assert_not_called()


def _invoke(app, handler, data, sid='sid-a'):
    with app.app_context():
        token = create_access_token(identity='socketio-unit-user')
    with app.test_request_context(
        '/', headers={'Cookie': f'access_token_cookie={token}'},
    ):
        request.sid = sid
        return handler(data)


def _invoke_disconnect(app, handler, sid):
    with app.test_request_context('/'):
        request.sid = sid
        return handler()


def _wait_for_target_tickets(gate, key, count):
    deadline = time.monotonic() + 2
    while gate.operation_bookkeeping().get(key, 0) < count:
        assert time.monotonic() < deadline


def _target():
    from ui.rcon_transport import ResolvedRconTarget

    return ResolvedRconTarget(1, 2, '203.0.113.10', 28888, 'secret', False)


def test_individual_join_first_owner_joins_and_connects(app):
    from ui import rcon_ownership, rcon_target_gate, socketio_events
    from ui.rcon_transport import PublishResult

    rcon_ownership.cleanup_sid('sid-a')
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, 'join_room') as join,
        patch.object(socketio_events, 'publish_json', return_value=PublishResult(True, 1)) as publish,
        patch.object(socketio_events, 'emit') as emit,
    ):
        _invoke(app, socketio_events.handle_rcon_join, {'host_id': 1, 'instance_id': 2})

    join.assert_called_once_with('rcon:1:2')
    assert publish.call_count == 1
    assert publish.call_args.args[0] == 'rcon:cmd:1:2'
    assert publish.call_args.args[1]['rcon_password'] == 'secret'
    emit.assert_called_with('rcon:joined', {'room': 'rcon:1:2', 'host_id': 1, 'instance_id': 2})
    assert rcon_ownership.owns('sid-a', 1, 2, 'individual')
    rcon_ownership.cleanup_sid('sid-a')


def test_individual_join_retries_when_existing_owner_is_not_established(app):
    from ui import rcon_ownership, rcon_target_gate, socketio_events
    from ui.rcon_transport import PublishResult

    rcon_ownership.cleanup_sid('sid-a')
    rcon_ownership.acquire_owner('sid-a', 1, 2, 'fleet')
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, 'join_room') as join,
        patch.object(socketio_events, 'publish_json', return_value=PublishResult(True, 1)) as publish,
        patch.object(socketio_events, 'emit'),
    ):
        _invoke(app, socketio_events.handle_rcon_join, {'host_id': 1, 'instance_id': 2})

    join.assert_not_called()
    publish.assert_called_once()
    assert rcon_ownership.owns('sid-a', 1, 2, 'individual')
    rcon_ownership.cleanup_sid('sid-a')


def test_individual_join_is_idempotent_without_duplicate_connect(app):
    from ui import rcon_ownership, rcon_target_gate, socketio_events
    from ui.rcon_transport import PublishResult

    rcon_ownership.cleanup_sid('sid-a')
    acquisition = rcon_ownership.acquire_owner('sid-a', 1, 2, 'individual')
    attempt = rcon_ownership.begin_connect(acquisition)
    rcon_ownership.complete_connect(attempt, succeeded=True)
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, 'join_room') as join,
        patch.object(socketio_events, 'publish_json', return_value=PublishResult(True, 1)) as publish,
        patch.object(socketio_events, 'emit'),
    ):
        _invoke(app, socketio_events.handle_rcon_join, {'host_id': 1, 'instance_id': 2})

    join.assert_not_called()
    publish.assert_not_called()
    rcon_ownership.cleanup_sid('sid-a')


def test_failed_first_connect_rolls_back_and_leaves_room(app):
    from ui import rcon_ownership, rcon_target_gate, socketio_events
    from ui.rcon_transport import PublishResult

    rcon_ownership.cleanup_sid('sid-a')
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, 'join_room'),
        patch.object(socketio_events, 'leave_room') as leave,
        patch.object(
            socketio_events, 'publish_json',
            return_value=PublishResult(False, 0, 'RCON service unavailable'),
        ),
        patch.object(socketio_events, 'emit') as emit,
    ):
        _invoke(app, socketio_events.handle_rcon_join, {'host_id': 1, 'instance_id': 2})

    leave.assert_called_once_with('rcon:1:2')
    assert not rcon_ownership.owns('sid-a', 1, 2, 'individual')
    emit.assert_called_once_with('rcon:error', {
        'error': 'RCON service unavailable',
        'host_id': 1,
        'instance_id': 2,
    })


def test_individual_leave_preserves_fleet_owner_and_room(app):
    from ui import rcon_ownership, socketio_events

    rcon_ownership.cleanup_sid('sid-a')
    rcon_ownership.acquire_owner('sid-a', 1, 2, 'individual')
    rcon_ownership.acquire_owner('sid-a', 1, 2, 'fleet')
    with (
        patch.object(socketio_events, 'rooms', return_value=['rcon:1:2']),
        patch.object(socketio_events, 'leave_room') as leave,
        patch.object(socketio_events, 'publish_json') as publish,
        patch.object(socketio_events, 'emit') as emit,
    ):
        _invoke(app, socketio_events.handle_rcon_leave, {'host_id': 1, 'instance_id': 2})

    leave.assert_not_called()
    publish.assert_not_called()
    assert rcon_ownership.owns('sid-a', 1, 2, 'fleet')
    emit.assert_called_once_with('rcon:left', {'room': 'rcon:1:2'})
    rcon_ownership.cleanup_sid('sid-a')


def test_individual_command_requires_individual_owner_and_room(app):
    from ui import rcon_ownership, socketio_events

    rcon_ownership.cleanup_sid('sid-a')
    rcon_ownership.acquire_owner('sid-a', 1, 2, 'fleet')
    with (
        patch.object(socketio_events, 'rooms', return_value=['rcon:1:2']),
        patch.object(socketio_events, 'publish_json') as publish,
        patch.object(socketio_events, 'emit') as emit,
    ):
        _invoke(
            app, socketio_events.handle_rcon_command,
            {'host_id': 1, 'instance_id': 2, 'cmd': 'status'},
        )

    publish.assert_not_called()
    emit.assert_called_once_with('rcon:error', {
        'error': 'Not authorized for this instance',
        'host_id': 1,
        'instance_id': 2,
    })
    rcon_ownership.cleanup_sid('sid-a')


def test_individual_command_missing_fields_preserves_parsed_target_in_error(app):
    from ui import socketio_events

    with patch.object(socketio_events, 'emit') as emit:
        _invoke(
            app, socketio_events.handle_rcon_command,
            {'host_id': 1, 'instance_id': 2},
        )

    emit.assert_called_once_with('rcon:error', {
        'error': 'Missing required fields',
        'host_id': 1,
        'instance_id': 2,
    })


def test_individual_join_resolution_error_is_targeted(app):
    from ui import socketio_events
    from ui.rcon_transport import RconTargetError

    with (
        patch.object(
            socketio_events, 'resolve_fleet_target',
            side_effect=RconTargetError('Instance not found on host'),
        ),
        patch.object(socketio_events, 'emit') as emit,
    ):
        _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2},
        )

    emit.assert_called_once_with('rcon:error', {
        'error': 'Instance not found on host',
        'host_id': 1,
        'instance_id': 2,
    })


def test_individual_join_missing_target_uses_unroutable_none_ids(app):
    from ui import socketio_events

    with patch.object(socketio_events, 'emit') as emit:
        _invoke(app, socketio_events.handle_rcon_join, {})

    emit.assert_called_once_with('rcon:error', {
        'error': 'Missing required fields (host_id, instance_id)',
        'host_id': None,
        'instance_id': None,
    })


def test_individual_join_not_established_error_is_targeted(app):
    from ui import rcon_ownership, socketio_events

    rcon_ownership.cleanup_sid('sid-a')
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, 'join_room'),
        patch.object(
            socketio_events, 'begin_connect',
            return_value=SimpleNamespace(should_publish=False, established=False),
        ),
        patch.object(socketio_events, 'emit') as emit,
    ):
        _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2},
        )

    emit.assert_called_once_with('rcon:error', {
        'error': 'RCON connection was not established',
        'host_id': 1,
        'instance_id': 2,
    })
    rcon_ownership.cleanup_sid('sid-a')


def test_same_sid_handler_after_disconnect_starts_is_rejected(app):
    from ui import (
        rcon_ownership,
        rcon_sid_lifecycle,
        rcon_target_gate,
        socketio_events,
    )
    from ui.rcon_transport import PublishResult

    actions = []
    first_connect_started = threading.Event()
    allow_first_connect = threading.Event()

    def publish(_channel, payload):
        actions.append(payload['action'])
        if actions == ['connect']:
            first_connect_started.set()
            assert allow_first_connect.wait(timeout=2)
        return PublishResult(True, 1)

    rcon_ownership.cleanup_sid('sid-a')
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, '_participant_count', return_value=0),
        patch.object(socketio_events, 'join_room'),
        patch.object(socketio_events, 'leave_room'),
        patch.object(socketio_events, 'publish_json', side_effect=publish),
        patch.object(socketio_events, 'emit'),
    ):
        old_join = threading.Thread(target=lambda: _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2}, sid='sid-a',
        ))
        cleanup = threading.Thread(target=lambda: _invoke_disconnect(
            app, socketio_events.handle_disconnect, 'sid-a',
        ))
        reacquire = threading.Thread(target=lambda: _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2}, sid='sid-a',
        ))
        old_join.start()
        assert first_connect_started.wait(timeout=2)
        cleanup.start()
        _wait_for_sid_closing(rcon_sid_lifecycle, 'sid-a')
        reacquire.start()
        reacquire.join(timeout=2)
        assert not reacquire.is_alive()
        allow_first_connect.set()
        for thread in (old_join, cleanup):
            thread.join(timeout=2)
            assert not thread.is_alive()

    assert actions == ['connect', 'disconnect']
    assert not rcon_ownership.owns('sid-a', 1, 2)
    assert rcon_target_gate.operation_bookkeeping() == {}
    assert rcon_sid_lifecycle.bookkeeping() == {}


def test_other_sid_join_waits_behind_pending_cleanup(app):
    from ui import rcon_ownership, rcon_target_gate, socketio_events
    from ui.rcon_transport import PublishResult

    actions = []
    first_connect_started = threading.Event()
    allow_first_connect = threading.Event()
    disconnect_started = threading.Event()
    allow_disconnect = threading.Event()

    def publish(_channel, payload):
        actions.append(payload['action'])
        if actions == ['connect']:
            first_connect_started.set()
            assert allow_first_connect.wait(timeout=2)
        elif payload['action'] == 'disconnect':
            disconnect_started.set()
            assert allow_disconnect.wait(timeout=2)
        return PublishResult(True, 1)

    rcon_ownership.cleanup_sid('sid-a')
    rcon_ownership.cleanup_sid('sid-b')
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, '_participant_count', return_value=0),
        patch.object(socketio_events, 'join_room'),
        patch.object(socketio_events, 'leave_room'),
        patch.object(socketio_events, 'publish_json', side_effect=publish),
        patch.object(socketio_events, 'emit'),
    ):
        old_join = threading.Thread(target=lambda: _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2}, sid='sid-a',
        ))
        cleanup = threading.Thread(target=lambda: _invoke_disconnect(
            app, socketio_events.handle_disconnect, 'sid-a',
        ))
        survivor_join = threading.Thread(target=lambda: _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2}, sid='sid-b',
        ))
        old_join.start()
        assert first_connect_started.wait(timeout=2)
        cleanup.start()
        allow_first_connect.set()
        assert disconnect_started.wait(timeout=2)
        survivor_join.start()
        _wait_for_target_tickets(rcon_target_gate, (1, 2), 2)
        allow_disconnect.set()
        for thread in (old_join, cleanup, survivor_join):
            thread.join(timeout=2)
            assert not thread.is_alive()

    assert actions == ['connect', 'disconnect', 'connect']
    assert not rcon_ownership.owns('sid-a', 1, 2)
    assert rcon_ownership.owns('sid-b', 1, 2, 'individual')
    assert rcon_target_gate.operation_bookkeeping() == {}
    rcon_ownership.cleanup_sid('sid-b')


def test_released_individual_claimant_receives_no_false_joined(app):
    from ui import rcon_ownership, rcon_target_gate, socketio_events
    from ui.rcon_transport import PublishResult

    publish_started = threading.Event()
    allow_publish = threading.Event()
    emitted = []
    actions = []

    def publish(_channel, payload):
        actions.append(payload['action'])
        publish_started.set()
        assert allow_publish.wait(timeout=2)
        return PublishResult(True, 1)

    rcon_ownership.cleanup_sid('sid-a')
    rcon_ownership.acquire_owner('sid-a', 1, 2, 'fleet')
    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, 'join_room'),
        patch.object(socketio_events, 'publish_json', side_effect=publish),
        patch.object(socketio_events, 'emit', side_effect=lambda event, *_args, **_kwargs: emitted.append(event)),
    ):
        join = threading.Thread(target=lambda: _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2}, sid='sid-a',
        ))
        join.start()
        assert publish_started.wait(timeout=2)
        released = rcon_ownership.release_owner('sid-a', 1, 2, 'individual')
        assert released.changed and not released.final_owner
        allow_publish.set()
        join.join(timeout=2)
        assert not join.is_alive()

    assert actions == ['connect']
    assert 'rcon:joined' not in emitted
    assert rcon_ownership.owns('sid-a', 1, 2, 'fleet')
    established = rcon_ownership.begin_connect(
        rcon_ownership.acquire_owner('sid-a', 1, 2, 'fleet'),
    )
    assert established.established and not established.should_publish
    rcon_ownership.cleanup_sid('sid-a')


def test_disconnect_drains_join_queued_before_owner_acquisition(app):
    from ui import rcon_ownership, rcon_sid_lifecycle, rcon_target_gate, socketio_events
    from ui.rcon_transport import PublishResult

    actions = []
    joined_rooms = {'sid-a': set()}
    gate_entered = threading.Event()
    release_gate = threading.Event()

    def hold_gate():
        with rcon_target_gate.operation(1, 2):
            gate_entered.set()
            assert release_gate.wait(timeout=2)

    def join_room(room):
        joined_rooms.setdefault('sid-a', set()).add(room)

    def leave_room(room):
        joined_rooms.get('sid-a', set()).discard(room)
        if not joined_rooms.get('sid-a'):
            joined_rooms.pop('sid-a', None)

    def publish(_channel, payload):
        actions.append(payload['action'])
        return PublishResult(True, 1)

    rcon_ownership.cleanup_sid('sid-a')
    blocker = threading.Thread(target=hold_gate)
    blocker.start()
    assert gate_entered.wait(timeout=2)

    with (
        patch.object(socketio_events, 'resolve_fleet_target', return_value=_target()),
        patch.object(socketio_events, 'join_room', side_effect=join_room),
        patch.object(socketio_events, 'leave_room', side_effect=leave_room),
        patch.object(socketio_events, '_participant_count', return_value=0),
        patch.object(socketio_events, 'publish_json', side_effect=publish),
        patch.object(socketio_events, 'emit'),
    ):
        join = threading.Thread(target=lambda: _invoke(
            app, socketio_events.handle_rcon_join,
            {'host_id': 1, 'instance_id': 2}, sid='sid-a',
        ))
        join.start()
        _wait_for_sid_active(rcon_sid_lifecycle, 'sid-a')
        _wait_for_target_tickets(rcon_target_gate, (1, 2), 2)

        def disconnect_after_socketio_room_cleanup():
            joined_rooms.pop('sid-a', None)
            _invoke_disconnect(app, socketio_events.handle_disconnect, 'sid-a')

        cleanup = threading.Thread(target=disconnect_after_socketio_room_cleanup)
        cleanup.start()
        _wait_for_sid_closing(rcon_sid_lifecycle, 'sid-a')
        release_gate.set()
        for thread in (blocker, join, cleanup):
            thread.join(timeout=2)
            assert not thread.is_alive()

    assert actions == ['connect', 'disconnect']
    assert not rcon_ownership.owns('sid-a', 1, 2)
    assert 'sid-a' not in rcon_ownership._connection_states
    assert 'sid-a' not in joined_rooms
    assert rcon_target_gate.operation_bookkeeping() == {}
    assert rcon_sid_lifecycle.bookkeeping() == {}


def _wait_for_sid_active(lifecycle, sid):
    deadline = time.monotonic() + 2
    while lifecycle.bookkeeping().get(sid, {}).get('active') != 1:
        assert time.monotonic() < deadline


def _wait_for_sid_closing(lifecycle, sid):
    deadline = time.monotonic() + 2
    while not lifecycle.bookkeeping().get(sid, {}).get('closing'):
        assert time.monotonic() < deadline
