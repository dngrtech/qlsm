# Global RCON Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a top-level Global RCON page that persistently selects QLSM instances, connects them concurrently, broadcasts one command to every ready target, and presents honest per-target one-line and multiline output.

**Architecture:** Extend the current default-namespace Flask-SocketIO → per-instance Redis Pub/Sub → `rcon_service` → ZMQ path. Flask owns fleet validation, room membership, and per-target fan-out; the existing RCON service keeps owning concurrent per-instance sockets. React owns browser-local target preferences, readiness snapshots, command-run grouping, raw streams, and presentation-only quiet/no-response timers.

**Tech Stack:** Python 3.11, Flask-SocketIO, SQLAlchemy, Redis Pub/Sub, pytest, React 19, Socket.IO Client, CodeMirror 6, Tailwind/CSS variables, Vitest, Testing Library.

---

## Decision Checkpoints

### Approved and closed

- Route: `/global-rcon`; desktop navigation order is Servers → Global RCON → Docs.
- Selected targets and expanded hosts persist per user in browser `localStorage`.
- Inventory-ineligible instances remain visible with disabled checkboxes and reasons.
- Selected inventory-eligible targets connect immediately.
- Send has no confirmation modal.
- A command is sent only to selected targets whose latest status is ready at click time.
- Selected connecting/failed targets are recorded as skipped; there is no delayed retry.
- Global RCON never subscribes to live stats/game events.
- All view groups output by command and target; per-instance filters show raw streams.
- Existing `rcon_service` and per-instance Redis channels remain authoritative; no global Redis command channel is added.
- Output and command runs are browser-memory-only and clear on reload.

### Unresolved forks

None. All implementation tasks may proceed autonomously. Any newly discovered user-visible semantics fork must stop and return to brainstorming before code continues.

## File Structure

### Backend

- Create `ui/rcon_transport.py` — shared target validation, credential resolution, room naming, Redis publication result, connect/command/disconnect payload builders.
- Create `ui/rcon_fleet_events.py` — fleet SID registry and `rcon:fleet_*` SocketIO handlers.
- Modify `ui/socketio_events.py` — consume shared transport helpers, preserve individual events, register fleet handlers, clean fleet state on disconnect.
- Create `tests/test_rcon_transport.py` — pure/backend helper coverage.
- Create `tests/test_rcon_fleet_events.py` — authenticated SocketIO fleet lifecycle and partial fan-out coverage.

### Shared RCON frontend

- Create `frontend-react/src/hooks/rconSocketTransport.js` — one reference-counted Socket.IO transport without target semantics.
- Modify `frontend-react/src/hooks/useRconSocket.js` — preserve individual-console API while using the shared transport and leaving its room immediately on cleanup.
- Create `frontend-react/src/components/rcon/RconRawOutputViewer.jsx` — extracted CodeMirror output setup, append, search, colors, and 1,000-line truncation.
- Create `frontend-react/src/components/rcon/RconCommandInput.jsx` — shared input, history navigation, focus, and recipient-aware send button.
- Modify `frontend-react/src/components/RconConsoleModal.jsx` — compose extracted primitives and retain individual stats behavior.
- Create `frontend-react/src/hooks/__tests__/rconSocketTransport.test.js`.
- Extend `frontend-react/src/components/__tests__/RconConsoleModal.test.jsx`.

### Fleet state and UI

- Create `frontend-react/src/utils/rconTargets.js` — target keys, eligibility, host tree construction, tri-state calculations.
- Create `frontend-react/src/hooks/useGlobalRconPreferences.js` — per-user selection/expansion persistence and reconciliation.
- Create `frontend-react/src/components/rcon/RconTargetTree.jsx` — host/instance tree, Select All/None, disabled reasons, connection indicators.
- Create `frontend-react/src/utils/__tests__/rconTargets.test.js`.
- Create `frontend-react/src/hooks/__tests__/useGlobalRconPreferences.test.jsx`.
- Create `frontend-react/src/components/rcon/__tests__/RconTargetTree.test.jsx`.
- Create `frontend-react/src/hooks/useFleetRconSession.js` — fleet joins, desired-target sync, status/message routing, fleet send acknowledgements, leave.
- Create `frontend-react/src/hooks/__tests__/useFleetRconSession.test.jsx`.
- Create `frontend-react/src/hooks/useRconCommandRuns.js` — run snapshots, skipped/queued/receiving/quiet/no-response states, raw streams, timers, retention.
- Create `frontend-react/src/hooks/__tests__/useRconCommandRuns.test.jsx`.
- Create `frontend-react/src/components/rcon/RconCommandRun.jsx` — compact one-line and expandable multiline target results.
- Create `frontend-react/src/components/rcon/RconOutputFilters.jsx` — All, bounded direct target filters, searchable overflow.
- Create `frontend-react/src/components/rcon/GlobalRconOutput.jsx` — All runs versus raw selected-instance output.
- Create `frontend-react/src/components/rcon/__tests__/RconCommandRun.test.jsx`.
- Create `frontend-react/src/components/rcon/__tests__/RconOutputFilters.test.jsx`.

### Page, navigation, docs, release

- Create `frontend-react/src/pages/GlobalRconPage.jsx`.
- Create `frontend-react/src/pages/__tests__/GlobalRconPage.test.jsx`.
- Modify `frontend-react/src/App.jsx`.
- Modify `frontend-react/src/components/Navbar.jsx`.
- Create `frontend-react/src/components/__tests__/Navbar.test.jsx` — authenticated desktop/mobile navigation ordering.
- Modify `frontend-react/src/index.css` only for layout/state styles not expressible cleanly with existing utilities.
- Modify `docs/rcon_integration.md` to match live individual and fleet contracts.
- Modify `docs/user/operations/rcon-console.md` with the Global RCON workflow and verification warning.
- Modify `mkdocs.yml` and `docs/user/index.md` to expose Global RCON documentation.
- Modify `VERSION`, `docs/user/version.json`, and `docs/user/releases.md` together to `1.15.0`.

---

### Task 1: Shared Backend RCON Transport Helpers

**Files:**
- Create: `ui/rcon_transport.py`
- Modify: `ui/socketio_events.py:21-80,117-240`
- Create: `tests/test_rcon_transport.py`
- Modify: `tests/test_socketio_events.py`

- [ ] **Step 1: Write failing target-resolution and publication tests**

```python
# tests/test_rcon_transport.py
from unittest.mock import Mock

import pytest

from ui import db
from ui.models import Host, InstanceStatus, QLInstance


def add_target(*, status=InstanceStatus.RUNNING, port=28888, password='secret'):
    host = Host(name='Paris', provider='vultr', ip_address='203.0.113.10')
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(
        name='Paris-1', hostname='Paris-1', port=27960, host_id=host.id,
        status=status, zmq_rcon_port=port, zmq_rcon_password=password,
    )
    db.session.add(instance)
    db.session.commit()
    return host, instance


def test_resolve_fleet_target_returns_server_side_credentials(app):
    from ui.rcon_transport import resolve_fleet_target
    with app.app_context():
        host, instance = add_target()
        resolved = resolve_fleet_target(host.id, instance.id)
        assert resolved.ip == '203.0.113.10'
        assert resolved.rcon_port == 28888
        assert resolved.rcon_password == 'secret'
        assert resolved.room == f'rcon:{host.id}:{instance.id}'


@pytest.mark.parametrize(
    ('status', 'port', 'password', 'reason'),
    [
        (InstanceStatus.STOPPED, 28888, 'secret', 'Instance is not running'),
        (InstanceStatus.RUNNING, None, 'secret', 'RCON not configured'),
        (InstanceStatus.RUNNING, 28888, None, 'RCON not configured'),
    ],
)
def test_resolve_fleet_target_rejects_ineligible_targets(app, status, port, password, reason):
    from ui.rcon_transport import RconTargetError, resolve_fleet_target
    with app.app_context():
        host, instance = add_target(status=status, port=port, password=password)
        with pytest.raises(RconTargetError, match=reason):
            resolve_fleet_target(host.id, instance.id)


def test_publish_json_reports_zero_subscribers(monkeypatch):
    from ui import rcon_transport
    fake = Mock()
    fake.publish.return_value = 0
    monkeypatch.setattr(rcon_transport, 'get_redis_client', lambda: fake)
    result = rcon_transport.publish_json('rcon:cmd:1:2', {'action': 'command', 'cmd': 'status'})
    assert result.ok is False
    assert result.reason == 'RCON service unavailable'
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
pytest tests/test_rcon_transport.py tests/test_socketio_events.py -v
```

Expected: collection or import failures because `ui.rcon_transport` does not exist.

- [ ] **Step 3: Implement the shared transport module**

```python
# ui/rcon_transport.py
from dataclasses import dataclass
import json
import os
import threading

import redis

from ui.models import InstanceStatus, QLInstance
from ui.task_logic.self_host_network import resolve_self_host_management_target

READY_STATUSES = {InstanceStatus.RUNNING, InstanceStatus.UPDATED}


class RconTargetError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedRconTarget:
    host_id: int
    instance_id: int
    ip: str
    rcon_port: int
    rcon_password: str
    self_host: bool

    @property
    def room(self):
        return f'rcon:{self.host_id}:{self.instance_id}'

    @property
    def channel(self):
        prefix = os.environ.get('REDIS_PREFIX', 'rcon')
        return f'{prefix}:cmd:{self.host_id}:{self.instance_id}'


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    subscribers: int = 0
    reason: str | None = None


_client = None
_client_lock = threading.Lock()


def get_redis_client():
    global _client
    with _client_lock:
        if _client is None:
            kwargs = {'decode_responses': True}
            if os.environ.get('REDIS_PASSWORD'):
                kwargs['password'] = os.environ['REDIS_PASSWORD']
            _client = redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'), **kwargs)
    return _client


def resolve_fleet_target(host_id: int, instance_id: int) -> ResolvedRconTarget:
    instance = QLInstance.query.get(instance_id)
    if not instance or instance.host_id != host_id:
        raise RconTargetError('Instance not found on host')
    if instance.status not in READY_STATUSES:
        raise RconTargetError('Instance is not running')
    if not instance.zmq_rcon_port or not instance.zmq_rcon_password:
        raise RconTargetError('RCON not configured')
    self_host = instance.host.provider == 'self'
    ip = resolve_self_host_management_target() if self_host else instance.host.ip_address
    if not ip:
        raise RconTargetError('Host address unavailable')
    return ResolvedRconTarget(
        host_id=host_id, instance_id=instance_id, ip=ip,
        rcon_port=instance.zmq_rcon_port,
        rcon_password=instance.zmq_rcon_password,
        self_host=self_host,
    )


def publish_json(channel: str, payload: dict) -> PublishResult:
    global _client
    try:
        subscribers = get_redis_client().publish(channel, json.dumps(payload))
        if subscribers < 1:
            return PublishResult(False, subscribers, 'RCON service unavailable')
        return PublishResult(True, subscribers)
    except redis.RedisError:
        with _client_lock:
            _client = None
        return PublishResult(False, 0, 'Communication service temporarily unavailable')
```

Also expose `connect_payload(target)`, `command_payload(cmd)`, and `disconnect_payload()` small builders so individual and fleet handlers produce identical Redis contracts.

- [ ] **Step 4: Refactor individual handlers without changing their event contract**

Replace private Redis/target code in `ui/socketio_events.py` with imports from `ui.rcon_transport`. Keep these existing events and payloads unchanged:

```text
rcon:join
rcon:leave
rcon:command
rcon:subscribe_stats
rcon:unsubscribe_stats
```

For individual errors, translate `PublishResult.reason` into the existing `rcon:error` event. Keep self-host target tests green.

- [ ] **Step 5: Run backend regression tests**

Run:

```bash
pytest tests/test_rcon_transport.py tests/test_socketio_events.py tests/test_rcon_self_host_path.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ui/rcon_transport.py ui/socketio_events.py tests/test_rcon_transport.py tests/test_socketio_events.py
git commit -m "refactor: share RCON transport helpers"
```

---

### Task 2: Fleet SocketIO Lifecycle and Fan-Out

**Files:**
- Create: `ui/rcon_fleet_events.py`
- Modify: `ui/socketio_events.py`
- Create: `tests/test_rcon_fleet_events.py`

- [ ] **Step 1: Write failing authenticated fleet-event tests**

Use `socketio.test_client(app, flask_test_client=client)` with an `access_token_cookie` created by `create_access_token`. Seed two running targets and one stopped target. Patch `ui.rcon_fleet_events.publish_json`.

```python
def test_fleet_command_queues_ready_room_members_and_rejects_stopped(
    socket_client, seeded_targets, mock_publish,
):
    running, stopped = seeded_targets
    join_ack = socket_client.emit(
        'rcon:fleet_join',
        {'targets': [running.ref, stopped.ref]},
        callback=True,
    )
    assert join_ack['targets'] == [
        {**running.ref, 'state': 'connecting'},
        {**stopped.ref, 'state': 'rejected', 'reason': 'Instance is not running'},
    ]

    command_ack = socket_client.emit(
        'rcon:fleet_command',
        {'run_id': 'run-1', 'cmd': 'status', 'targets': [running.ref, stopped.ref]},
        callback=True,
    )
    assert command_ack['run_id'] == 'run-1'
    assert command_ack['targets'][0]['state'] == 'queued'
    assert command_ack['targets'][1]['state'] == 'rejected'
    mock_publish.assert_any_call(
        f"rcon:cmd:{running.host_id}:{running.instance_id}",
        {'action': 'command', 'cmd': 'status'},
    )


def test_fleet_command_deduplicates_targets(socket_client, running_target, mock_publish):
    socket_client.emit('rcon:fleet_join', {'targets': [running_target.ref]}, callback=True)
    ack = socket_client.emit(
        'rcon:fleet_command',
        {'run_id': 'run-2', 'cmd': 'status', 'targets': [running_target.ref, running_target.ref]},
        callback=True,
    )
    assert len(ack['targets']) == 1


def test_fleet_command_rejects_target_not_joined_by_sender(socket_client, running_target):
    ack = socket_client.emit(
        'rcon:fleet_command',
        {'run_id': 'run-3', 'cmd': 'status', 'targets': [running_target.ref]},
        callback=True,
    )
    assert ack['targets'][0]['reason'] == 'Target not joined'


def test_fleet_leave_clears_only_fleet_rooms(socket_client, running_target, mock_publish):
    socket_client.emit('rcon:fleet_join', {'targets': [running_target.ref]}, callback=True)
    ack = socket_client.emit('rcon:fleet_leave', callback=True)
    assert ack == {'left': 1}
```

Also test missing auth, malformed targets, empty/whitespace commands, host/instance mismatch, zero Redis subscribers, partial publication failure, and no credential values in acknowledgements.

- [ ] **Step 2: Run the fleet tests and verify RED**

Run:

```bash
pytest tests/test_rcon_fleet_events.py -v
```

Expected: failures because fleet events are not registered.

- [ ] **Step 3: Implement the fleet handler registry**

```python
# ui/rcon_fleet_events.py
from collections import defaultdict
from threading import RLock

from flask import request
from flask_socketio import join_room, leave_room, rooms

from ui.rcon_transport import (
    RconTargetError, command_payload, connect_payload,
    disconnect_payload, publish_json, resolve_fleet_target,
)

_fleet_targets = defaultdict(set)
_fleet_lock = RLock()


def target_key(raw):
    if not isinstance(raw, dict):
        raise RconTargetError('Invalid target')
    host_id = raw.get('host_id')
    instance_id = raw.get('instance_id')
    if not isinstance(host_id, int) or not isinstance(instance_id, int):
        raise RconTargetError('Invalid target')
    return host_id, instance_id


def unique_targets(raw_targets):
    seen = set()
    for raw in raw_targets if isinstance(raw_targets, list) else []:
        key = target_key(raw)
        if key not in seen:
            seen.add(key)
            yield key


def register_rcon_fleet_events(socketio, authenticated_only):
    @socketio.on('rcon:fleet_join')
    @authenticated_only
    def fleet_join(data):
        return _set_targets(socketio, request.sid, data.get('targets', []))

    @socketio.on('rcon:fleet_targets')
    @authenticated_only
    def fleet_targets(data):
        return _set_targets(socketio, request.sid, data.get('targets', []))

    @socketio.on('rcon:fleet_command')
    @authenticated_only
    def fleet_command(data):
        cmd = data.get('cmd')
        run_id = data.get('run_id')
        if not isinstance(cmd, str) or not cmd.strip():
            return {'run_id': run_id, 'error': 'Command is required', 'targets': []}
        results = []
        for host_id, instance_id in unique_targets(data.get('targets', [])):
            results.append(_send_one(request.sid, host_id, instance_id, cmd.strip()))
        return {'run_id': run_id, 'targets': results}

    @socketio.on('rcon:fleet_leave')
    @authenticated_only
    def fleet_leave():
        return {'left': _leave_all(socketio, request.sid)}
```

Implement `_set_targets`, `_send_one`, `_leave_one`, `_leave_all`, and `cleanup_fleet_sid`. Each result must contain `host_id`, `instance_id`, `state`, and an optional safe `reason`. `_send_one` must verify membership in both `_fleet_targets[request.sid]` and the actual SocketIO room before publishing.

- [ ] **Step 4: Register fleet handlers and disconnect cleanup once**

At the bottom of `ui/socketio_events.py`, after the individual handlers are defined:

```python
from .rcon_fleet_events import cleanup_fleet_sid, register_rcon_fleet_events

register_rcon_fleet_events(socketio, authenticated_only)
```

Update `handle_disconnect()` to call `cleanup_fleet_sid(request.sid)`. Normal React unmount still emits `rcon:fleet_leave`; disconnect cleanup removes registry state and performs best-effort participant-safe disconnect publication without blocking disconnect.

- [ ] **Step 5: Run backend RCON tests**

Run:

```bash
pytest tests/test_rcon_transport.py tests/test_rcon_fleet_events.py tests/test_socketio_events.py tests/test_rcon_self_host_path.py -v
```

Expected: all pass, including partial fleet fan-out.

- [ ] **Step 6: Commit**

```bash
git add ui/rcon_fleet_events.py ui/socketio_events.py tests/test_rcon_fleet_events.py
git commit -m "feat: add fleet RCON socket events"
```

---

### Task 3: Shared Browser Socket and Individual Console Extraction

**Files:**
- Create: `frontend-react/src/hooks/rconSocketTransport.js`
- Create: `frontend-react/src/hooks/__tests__/rconSocketTransport.test.js`
- Modify: `frontend-react/src/hooks/useRconSocket.js`
- Create: `frontend-react/src/components/rcon/RconRawOutputViewer.jsx`
- Create: `frontend-react/src/components/rcon/RconCommandInput.jsx`
- Modify: `frontend-react/src/components/RconConsoleModal.jsx`
- Extend: `frontend-react/src/components/__tests__/RconConsoleModal.test.jsx`

- [ ] **Step 1: Write failing shared-transport tests**

```javascript
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('socket.io-client', () => ({ io: vi.fn(() => ({ disconnect: vi.fn() })) }));

import { acquireRconSocket, releaseRconSocket, resetRconSocketForTests } from '../rconSocketTransport';
import { io } from 'socket.io-client';

describe('rconSocketTransport', () => {
  afterEach(() => resetRconSocketForTests());

  it('shares one socket and disconnects only after the final release', () => {
    const first = acquireRconSocket();
    const second = acquireRconSocket();
    expect(first).toBe(second);
    expect(io).toHaveBeenCalledTimes(1);
    releaseRconSocket();
    expect(first.disconnect).not.toHaveBeenCalled();
    releaseRconSocket({ immediate: true });
    expect(first.disconnect).toHaveBeenCalledOnce();
  });
});
```

Extend the modal test to prove command display, response display, stats subscribe/unsubscribe, and room leave still occur after extraction.

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run:

```bash
cd frontend-react
pnpm test -- src/hooks/__tests__/rconSocketTransport.test.js src/components/__tests__/RconConsoleModal.test.jsx
```

Expected: missing transport/component modules.

- [ ] **Step 3: Implement the reference-counted transport**

```javascript
// frontend-react/src/hooks/rconSocketTransport.js
import { io } from 'socket.io-client';

const SOCKET_URL = import.meta.env.VITE_API_BASE_URL || '';
let socket = null;
let users = 0;
let disconnectTimer = null;

export function acquireRconSocket() {
  if (disconnectTimer) {
    clearTimeout(disconnectTimer);
    disconnectTimer = null;
  }
  if (!socket) {
    socket = io(SOCKET_URL, {
      withCredentials: true,
      transports: import.meta.env.DEV ? ['polling'] : ['websocket', 'polling'],
      upgrade: !import.meta.env.DEV,
      reconnection: true,
      reconnectionAttempts: 3,
      reconnectionDelay: 1000,
    });
  }
  users += 1;
  return socket;
}

export function releaseRconSocket({ immediate = false } = {}) {
  users = Math.max(0, users - 1);
  if (users !== 0 || !socket) return;
  const close = () => {
    if (users === 0 && socket) socket.disconnect();
    if (users === 0) socket = null;
    disconnectTimer = null;
  };
  if (immediate) close();
  else disconnectTimer = setTimeout(close, 1000);
}

export function resetRconSocketForTests() {
  if (disconnectTimer) clearTimeout(disconnectTimer);
  socket?.disconnect();
  socket = null;
  users = 0;
  disconnectTimer = null;
}
```

- [ ] **Step 4: Extract raw output and command input**

`RconRawOutputViewer` owns CodeMirror creation/destruction and exposes an imperative API:

```javascript
useImperativeHandle(ref, () => ({
  append({ type, content, timestamp }) { /* preserve current formatting and colors */ },
  clear() { /* replace the whole document with empty text */ },
  getText() { return viewRef.current?.state.doc.toString() || ''; },
}));
```

It must use the existing `quakeColorPlugin`, `rconTheme`, search/default keymaps, line numbers, read-only selection, auto-scroll, and exact 1,000-line oldest-first truncation.

`RconCommandInput` accepts:

```javascript
{
  disabled,
  recipientCount,
  prompt = 'RCON>',
  onSend,
  buttonLabel,
}
```

It owns a 50-entry in-memory history, Up/Down navigation, input clearing, and focus restoration.

- [ ] **Step 5: Refactor `useRconSocket` and modal composition**

`useRconSocket` must preserve its public return shape. On cleanup it must emit its own `rcon:leave` immediately, unsubscribe stats if needed, remove only its listeners, then call `releaseRconSocket()`. Socket transport shutdown remains debounced only for StrictMode; room cleanup is not delayed until the last unrelated hook user.

`RconConsoleModal` becomes a composition of `RconRawOutputViewer` and `RconCommandInput`, remaining below 300 source lines.

- [ ] **Step 6: Run tests and lint**

Run:

```bash
cd frontend-react
pnpm test -- src/hooks/__tests__/rconSocketTransport.test.js src/components/__tests__/RconConsoleModal.test.jsx
pnpm lint
```

Expected: focused tests pass; lint has no new errors.

- [ ] **Step 7: Commit**

```bash
git add frontend-react/src/hooks/rconSocketTransport.js frontend-react/src/hooks/__tests__/rconSocketTransport.test.js frontend-react/src/hooks/useRconSocket.js frontend-react/src/components/rcon/RconRawOutputViewer.jsx frontend-react/src/components/rcon/RconCommandInput.jsx frontend-react/src/components/RconConsoleModal.jsx frontend-react/src/components/__tests__/RconConsoleModal.test.jsx
git commit -m "refactor: share RCON console primitives"
```

---

### Task 4: Persistent Fleet Target Model and Tree

**Files:**
- Create: `frontend-react/src/utils/rconTargets.js`
- Create: `frontend-react/src/utils/__tests__/rconTargets.test.js`
- Create: `frontend-react/src/hooks/useGlobalRconPreferences.js`
- Create: `frontend-react/src/hooks/__tests__/useGlobalRconPreferences.test.jsx`
- Create: `frontend-react/src/components/rcon/RconTargetTree.jsx`
- Create: `frontend-react/src/components/rcon/__tests__/RconTargetTree.test.jsx`

- [ ] **Step 1: Write failing pure target-model tests**

```javascript
import { describe, expect, it } from 'vitest';
import { buildRconHosts, instanceTargetKey, selectionState } from '../rconTargets';

const instances = [
  { id: 11, host_id: 1, name: 'Paris-1', status: 'running', zmq_rcon_port: 28888 },
  { id: 12, host_id: 1, name: 'Paris-2', status: 'stopped', zmq_rcon_port: 28889 },
];

it('keeps stopped instances visible but ineligible', () => {
  const [host] = buildRconHosts([{ id: 1, name: 'Paris' }], instances);
  expect(host.instances).toEqual([
    expect.objectContaining({ key: '1:11', eligible: true }),
    expect.objectContaining({ key: '1:12', eligible: false, disabledReason: 'stopped' }),
  ]);
});

it('computes host partial selection from eligible children only', () => {
  expect(selectionState(['1:11', '1:13'], new Set(['1:11']))).toBe('some');
});

it('uses stable host and instance IDs', () => {
  expect(instanceTargetKey(instances[0])).toBe('1:11');
});
```

- [ ] **Step 2: Write failing persistence-hook tests**

Mock `useAuth()` with user ID `7`, render the hook, and assert:

```javascript
expect(localStorage.getItem('qlsm-global-rcon-targets-7')).toBe('["1:11"]');
expect(localStorage.getItem('qlsm-global-rcon-expanded-hosts-7')).toBe('[1]');
```

Cover malformed JSON, deleted-ID pruning, new instances unchecked, temporary ineligibility retaining the selected key, and storage exceptions degrading to memory state.

- [ ] **Step 3: Implement target utilities and preferences hook**

```javascript
export const READY_INSTANCE_STATUSES = new Set(['running', 'updated']);

export function instanceTargetKey(instance) {
  return `${instance.host_id}:${instance.id}`;
}

export function inventoryEligibility(instance) {
  if (!READY_INSTANCE_STATUSES.has(String(instance.status || '').toLowerCase())) {
    return { eligible: false, reason: String(instance.status || 'not running').toLowerCase() };
  }
  if (!instance.zmq_rcon_port) return { eligible: false, reason: 'RCON not configured' };
  return { eligible: true, reason: null };
}
```

`useGlobalRconPreferences(hosts, instances)` returns:

```javascript
{
  selectedKeys,
  expandedHostIds,
  setTargetChecked,
  setHostChecked,
  selectAllEligible,
  selectNone,
  toggleHostExpanded,
}
```

Persist immediately with per-user keys. Reconcile only against existence; do not remove a selected key merely because its instance is temporarily ineligible.

- [ ] **Step 4: Write and implement target-tree component tests**

Test accessible checkbox names and button names:

```javascript
expect(screen.getByRole('checkbox', { name: 'Select Paris-1' })).toBeChecked();
expect(screen.getByRole('checkbox', { name: 'Select Paris-2' })).toBeDisabled();
expect(screen.getByText('stopped')).toBeInTheDocument();
```

The host checkbox must set `indeterminate` through a ref when only some eligible children are selected. `Select All` excludes ineligible instances. Runtime connection failure changes the indicator/reason but does not disable an inventory-eligible checkbox.

- [ ] **Step 5: Run target tests**

Run:

```bash
cd frontend-react
pnpm test -- src/utils/__tests__/rconTargets.test.js src/hooks/__tests__/useGlobalRconPreferences.test.jsx src/components/rcon/__tests__/RconTargetTree.test.jsx
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend-react/src/utils/rconTargets.js frontend-react/src/utils/__tests__/rconTargets.test.js frontend-react/src/hooks/useGlobalRconPreferences.js frontend-react/src/hooks/__tests__/useGlobalRconPreferences.test.jsx frontend-react/src/components/rcon/RconTargetTree.jsx frontend-react/src/components/rcon/__tests__/RconTargetTree.test.jsx
git commit -m "feat: add persistent global RCON target tree"
```

---

### Task 5: Fleet Browser Session Hook

**Files:**
- Create: `frontend-react/src/hooks/useFleetRconSession.js`
- Create: `frontend-react/src/hooks/__tests__/useFleetRconSession.test.jsx`

- [ ] **Step 1: Write failing hook tests with a fake Socket.IO client**

Use a fake socket implementing `on`, `off`, `emit`, `connected`, and acknowledgement callbacks. Cover:

```javascript
it('joins restored targets and tracks status by target key', () => {
  const { result } = renderHook(() => useFleetRconSession({
    targets: [{ host_id: 1, instance_id: 11 }],
    enabled: true,
    onMessage: vi.fn(),
  }));
  expect(fakeSocket.emit).toHaveBeenCalledWith(
    'rcon:fleet_join',
    { targets: [{ host_id: 1, instance_id: 11 }] },
    expect.any(Function),
  );
  act(() => fakeSocket.fire('rcon:status', { host_id: 1, instance_id: 11, status: 'connected' }));
  expect(result.current.statuses.get('1:11')).toBe('ready');
});
```

Also test desired-target updates emit `rcon:fleet_targets`, messages preserve IDs, send emits exactly one `rcon:fleet_command`, acknowledgements are returned, disconnect marks targets failed, cleanup emits `rcon:fleet_leave`, and no stats event is emitted.

- [ ] **Step 2: Run the hook test and verify RED**

Run:

```bash
cd frontend-react
pnpm test -- src/hooks/__tests__/useFleetRconSession.test.jsx
```

Expected: missing hook.

- [ ] **Step 3: Implement the fleet session hook**

```javascript
export function useFleetRconSession({ targets, enabled, onMessage }) {
  const [statuses, setStatuses] = useState(new Map());
  const socketRef = useRef(null);
  const targetsRef = useRef(targets);

  // acquire once while enabled; register filtered rcon:status/message/error listeners
  // emit fleet_join on socket connect
  // emit fleet_targets when the stable desired target signature changes
  // map backend connected -> ready; preserve connecting/error/disconnected
  // emit fleet_leave before releasing transport

  const sendCommand = useCallback((runId, cmd, readyTargets) => new Promise((resolve) => {
    socketRef.current.emit(
      'rcon:fleet_command',
      { run_id: runId, cmd, targets: readyTargets },
      (ack) => resolve(ack),
    );
  }), []);

  return { statuses, sendCommand };
}
```

Use refs for current target IDs and message callback so listener registration does not churn. Ignore `rcon:message`/`rcon:status` events whose target key is not in the current desired set.

- [ ] **Step 4: Run fleet hook and transport tests**

Run:

```bash
cd frontend-react
pnpm test -- src/hooks/__tests__/useFleetRconSession.test.jsx src/hooks/__tests__/rconSocketTransport.test.js
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend-react/src/hooks/useFleetRconSession.js frontend-react/src/hooks/__tests__/useFleetRconSession.test.jsx
git commit -m "feat: add global RCON fleet session hook"
```

---

### Task 6: Command Runs, Multiline Grouping, and Output Filters

**Files:**
- Create: `frontend-react/src/hooks/useRconCommandRuns.js`
- Create: `frontend-react/src/hooks/__tests__/useRconCommandRuns.test.jsx`
- Create: `frontend-react/src/components/rcon/RconCommandRun.jsx`
- Create: `frontend-react/src/components/rcon/RconOutputFilters.jsx`
- Create: `frontend-react/src/components/rcon/GlobalRconOutput.jsx`
- Create: `frontend-react/src/components/rcon/__tests__/RconCommandRun.test.jsx`
- Create: `frontend-react/src/components/rcon/__tests__/RconOutputFilters.test.jsx`

- [ ] **Step 1: Write failing command-run state tests with fake timers**

```javascript
vi.useFakeTimers();
const { result } = renderHook(() => useRconCommandRuns());

act(() => {
  result.current.startRun({
    id: 'run-1', command: 'map thunderstruck',
    readyTargets: [{ key: '1:11', name: 'Paris-1' }],
    skippedTargets: [{ key: '2:21', name: 'NJ-1', reason: 'not ready' }],
  });
  result.current.applyDispatchAck('run-1', {
    targets: [{ host_id: 1, instance_id: 11, state: 'queued' }],
  });
  result.current.appendMessage({ host_id: 1, instance_id: 11, content: 'line one', timestamp: '12:00:00' });
  result.current.appendMessage({ host_id: 1, instance_id: 11, content: 'line two', timestamp: '12:00:01' });
});
expect(result.current.runs[0].results['1:11'].lines).toHaveLength(2);
expect(result.current.runs[0].results['2:21'].state).toBe('skipped');

act(() => vi.advanceTimersByTime(1500));
expect(result.current.runs[0].results['1:11'].state).toBe('quiet');
```

Cover five-second `no response yet`, late-line reopening, next-run attribution, unsolicited lines going only to raw stream, 50-run retention, 1,000 raw-line retention, rejection acknowledgements, and connection failures.

- [ ] **Step 2: Run the state test and verify RED**

Run:

```bash
cd frontend-react
pnpm test -- src/hooks/__tests__/useRconCommandRuns.test.jsx
```

Expected: missing hook.

- [ ] **Step 3: Implement command-run state with explicit constants**

```javascript
export const QUIET_AFTER_MS = 1500;
export const NO_RESPONSE_AFTER_MS = 5000;
export const MAX_RUNS = 50;
export const MAX_RAW_LINES = 1000;
```

Use refs for active run IDs and timer handles per target. Clear all timers on unmount. `startRun` must close prior attribution windows before assigning the new run to ready targets. `appendMessage` always appends to raw target output; it appends to a command result only if that target currently has an active run.

- [ ] **Step 4: Write failing rendering tests**

`RconCommandRun` expectations:

```javascript
expect(screen.getByText('Player permission level set to 5')).toBeVisible();
expect(screen.getByRole('button', { name: /Paris-1.*33 lines/i })).toHaveAttribute('aria-expanded', 'false');
fireEvent.click(screen.getByRole('button', { name: /Paris-1.*33 lines/i }));
expect(screen.getByText('Server Initialization')).toBeVisible();
```

Test one-line compact rows, output through five lines expanded inline, longer output collapsed, error blocks automatically expanded, Expand All/Collapse All, target-label click selecting its raw filter, and copy controls.

`RconOutputFilters` must render `ALL`, a bounded direct target list, and a searchable `+ N more` overflow without modifying targets.

- [ ] **Step 5: Implement output components**

`GlobalRconOutput` accepts:

```javascript
{
  activeFilter,
  onFilterChange,
  selectedTargets,
  runs,
  rawStreams,
}
```

For `ALL`, render newest command runs in chronological submission order with `RconCommandRun`. For a target key, feed its raw events into `RconRawOutputViewer`. Prefix target names once per result block, never once per multiline line.

- [ ] **Step 6: Run output tests**

Run:

```bash
cd frontend-react
pnpm test -- src/hooks/__tests__/useRconCommandRuns.test.jsx src/components/rcon/__tests__/RconCommandRun.test.jsx src/components/rcon/__tests__/RconOutputFilters.test.jsx
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend-react/src/hooks/useRconCommandRuns.js frontend-react/src/hooks/__tests__/useRconCommandRuns.test.jsx frontend-react/src/components/rcon/RconCommandRun.jsx frontend-react/src/components/rcon/RconOutputFilters.jsx frontend-react/src/components/rcon/GlobalRconOutput.jsx frontend-react/src/components/rcon/__tests__/RconCommandRun.test.jsx frontend-react/src/components/rcon/__tests__/RconOutputFilters.test.jsx
git commit -m "feat: group global RCON command output"
```

---

### Task 7: Global RCON Page, Route, and Navigation

**Files:**
- Create: `frontend-react/src/pages/GlobalRconPage.jsx`
- Create: `frontend-react/src/pages/__tests__/GlobalRconPage.test.jsx`
- Modify: `frontend-react/src/App.jsx`
- Modify: `frontend-react/src/components/Navbar.jsx`
- Create: `frontend-react/src/components/__tests__/Navbar.test.jsx`
- Modify: `frontend-react/src/index.css`

- [ ] **Step 1: Write failing page integration tests**

Mock inventory hooks, preferences, fleet session, and command runs. Assert:

```javascript
expect(screen.getByRole('heading', { name: 'Global RCON' })).toBeInTheDocument();
expect(screen.getByRole('button', { name: 'Send to 14 targets' })).toBeEnabled();
```

On send, verify:

```javascript
expect(startRun).toHaveBeenCalledWith(expect.objectContaining({
  readyTargets: expect.arrayContaining([expect.objectContaining({ key: '1:11' })]),
  skippedTargets: expect.arrayContaining([expect.objectContaining({ key: '2:21' })]),
}));
expect(sendCommand).toHaveBeenCalledWith(expect.any(String), 'qlx !setperm 7656119 5', [
  { host_id: 1, instance_id: 11 },
]);
```

Also prove zero ready targets disables Send, the All/raw filter does not alter selection, inventory errors render safely, and no confirmation dialog or stats control exists.

- [ ] **Step 2: Write failing navigation tests**

Render `Navbar` with authenticated context and assert desktop link ordering from DOM position:

```javascript
const links = screen.getAllByRole('link').map((link) => link.textContent.trim());
expect(links.indexOf('GLOBAL RCON')).toBeGreaterThan(links.indexOf('SERVERS'));
expect(links.indexOf('GLOBAL RCON')).toBeLessThan(links.indexOf('DOCS'));
expect(screen.getByRole('link', { name: /global rcon/i })).toHaveAttribute('href', '/global-rcon');
```

Add route coverage proving `/global-rcon` renders through `ProtectedRoute`.

- [ ] **Step 3: Implement the page composition**

`GlobalRconPage` must derive current objects from live `serversData`, never store full stale instance objects. Compose:

```text
useServers
useHostOrder
useGlobalRconPreferences
buildRconHosts
useFleetRconSession
useRconCommandRuns
RconTargetTree
RconOutputFilters
GlobalRconOutput
RconCommandInput
```

Send flow:

```javascript
const handleSend = async (command) => {
  const id = crypto.randomUUID();
  const readyTargets = selectedTargets.filter((target) => statuses.get(target.key) === 'ready');
  const skippedTargets = selectedTargets
    .filter((target) => statuses.get(target.key) !== 'ready')
    .map((target) => ({ ...target, reason: statuses.get(target.key) || 'not ready' }));
  startRun({ id, command, readyTargets, skippedTargets });
  const ack = await sendCommand(id, command, readyTargets.map(({ host_id, id: instance_id }) => ({ host_id, instance_id })));
  applyDispatchAck(id, ack);
};
```

The displayed recipient count and command payload both use the same `readyTargets` snapshot.

- [ ] **Step 4: Add route and navigation links**

In `App.jsx`, import `GlobalRconPage` and add:

```jsx
<Route path="/global-rcon" element={<GlobalRconPage />} />
```

In desktop and mobile Navbar sections, add a `Terminal` icon link immediately after Servers and before Docs.

- [ ] **Step 5: Implement restrained responsive styling**

Desktop: fixed-width target pane around 18rem and flexible output pane. Mobile/narrow widths: target pane becomes an upper collapsible section and output remains usable below. Reuse theme variables and existing console styles. Add only scoped `.global-rcon-*` selectors to `index.css`; do not copy the entire File Manager stylesheet.

- [ ] **Step 6: Run page/navigation tests and frontend checks**

Run:

```bash
cd frontend-react
pnpm test -- src/pages/__tests__/GlobalRconPage.test.jsx src/components/__tests__/Navbar.test.jsx
pnpm lint
pnpm build
```

Expected: tests pass, lint has no new errors, production build succeeds.

- [ ] **Step 7: Visually verify without starting or restarting the dev server**

Use the user's already-running dev environment if available. Verify desktop and narrow layouts, 15-target density, tri-state checkboxes, disabled reasons, ready/skipped count, multiline expansion, output filters, dark/light themes, and focus/history behavior. If no dev server is running, record that visual verification is blocked rather than starting one against repository rules.

- [ ] **Step 8: Commit**

```bash
git add frontend-react/src/pages/GlobalRconPage.jsx frontend-react/src/pages/__tests__/GlobalRconPage.test.jsx frontend-react/src/App.jsx frontend-react/src/components/Navbar.jsx frontend-react/src/components/__tests__/Navbar.test.jsx frontend-react/src/index.css
git commit -m "feat: add Global RCON page"
```

---

### Task 8: Documentation and Version Synchronization

**Files:**
- Modify: `docs/rcon_integration.md`
- Modify: `docs/user/operations/rcon-console.md`
- Modify: `mkdocs.yml`
- Modify: `docs/user/index.md`
- Modify: `VERSION`
- Modify: `docs/user/version.json`
- Modify: `docs/user/releases.md`
- Create: `tests/test_global_rcon_docs.py`

- [ ] **Step 1: Add documentation assertions before edits**

Create a lightweight documentation/version test:

```python
# tests/test_global_rcon_docs.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_global_rcon_docs_and_versions_stay_synchronized():
    version_file = (ROOT / 'VERSION').read_text().strip()
    version_manifest = json.loads((ROOT / 'docs/user/version.json').read_text())
    integration_doc = (ROOT / 'docs/rcon_integration.md').read_text()
    user_doc = (ROOT / 'docs/user/operations/rcon-console.md').read_text()
    mkdocs = (ROOT / 'mkdocs.yml').read_text()
    user_index = (ROOT / 'docs/user/index.md').read_text()

    assert version_file == version_manifest['latest'] == '1.15.0'
    assert 'rcon:fleet_command' in integration_doc
    assert 'line-by-line' in integration_doc
    assert '/global-rcon' in user_doc
    assert 'qlx !getperm' in user_doc
    assert 'Global RCON' in mkdocs
    assert 'Global RCON' in user_index
```

- [ ] **Step 2: Run the documentation/version test and verify RED**

Run:

```bash
pytest tests/test_global_rcon_docs.py -v
```

Expected: version and Global RCON documentation assertions fail.

- [ ] **Step 3: Correct `docs/rcon_integration.md`**

Document the live default SocketIO namespace and current event names. Replace stale claims about implemented REST endpoints, `/rcon` namespace, `text` response fields, and whole-response payloads. Add fleet events, per-SID fleet registry, per-instance fan-out, `content`, line-by-line delivery, no command correlation ID, and no global Redis command channel.

- [ ] **Step 4: Expand the user RCON guide**

Add:

- Individual RCON versus Global RCON.
- Target selection, persistence, eligibility, and readiness indicators.
- `Send to N targets` semantics.
- Skipped target behavior and absence of delayed retries.
- One-line versus expandable multiline output.
- All versus per-instance output filters.
- No live stats in Global RCON.
- Mutation/read-back example using `!setperm` then `!getperm`.
- Explicit warning that queued/quiet is not semantic success.

Add a **Global RCON** navigation entry in `mkdocs.yml` adjacent to the existing RCON Console operation, and add a Global RCON link beside RCON Console in `docs/user/index.md`.

- [ ] **Step 5: Bump all version sources together**

Set:

```text
VERSION: 1.15.0
docs/user/version.json latest: 1.15.0
```

Insert the release row:

```markdown
| `v1.15.0` | 2026-07-21 | — | Add a Global RCON page for persistent multi-instance targeting, concurrent fleet command fan-out, and grouped per-target output. |
```

- [ ] **Step 6: Run documentation/version tests**

Run:

```bash
pytest tests/test_global_rcon_docs.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add docs/rcon_integration.md docs/user/operations/rcon-console.md mkdocs.yml docs/user/index.md VERSION docs/user/version.json docs/user/releases.md tests/test_global_rcon_docs.py
git commit -m "docs: document Global RCON workflow"
```

---

### Task 9: Full Verification and Delivery Readiness

**Files:**
- Modify only feature files implicated by failures from the commands below.

- [ ] **Step 1: Run complete backend tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Run complete frontend tests**

```bash
cd frontend-react
pnpm test
```

Expected: all tests pass.

- [ ] **Step 3: Run lint and production build**

```bash
cd frontend-react
pnpm lint
pnpm build
```

Expected: no new lint errors and successful Vite build.

- [ ] **Step 4: Verify source-file size constraints**

Run a Python script that counts nonblank, non-comment source lines in every new/modified `.py`, `.js`, and `.jsx` file. Split focused responsibilities if any new source file exceeds 300 lines; never leave a file above 500 lines.

- [ ] **Step 5: Review the final diff for contract and secret safety**

```bash
git diff design/global-rcon...HEAD --check
git diff design/global-rcon...HEAD --stat
git status --short
```

Inspect the full diff and verify:

- No RCON passwords appear in browser payloads, acknowledgements, or logs.
- No `rcon:cmd:global` channel exists.
- Global RCON emits no stats subscription.
- Skipped targets receive no command publication and no retry.
- Individual RCON remains backward compatible.
- Spec, implementation, tests, docs, and version files agree.

- [ ] **Step 6: Run a live smoke only with explicit environment permission**

Do not start, stop, restart, or kill QLSM dev services. If the user authorizes use of an already-running environment, verify with harmless `status` across selected test instances before any mutation. For permission workflow, perform read-only `qlx !getperm <steamid64>` before mutation and repeat it after mutation. Never use production permission changes as an unannounced smoke test.

- [ ] **Step 7: Commit verification fixes if any**

```bash
git add -u
git commit -m "test: harden Global RCON delivery"
```

Skip this commit if verification required no changes.

- [ ] **Step 8: Stop before PR creation**

Report branch, commits, exact test/build results, visual/live verification status, and any blocker. Do not push, open a PR, merge, or deploy without the user's explicit instruction.
