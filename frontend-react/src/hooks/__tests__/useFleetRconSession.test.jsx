import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const socketFactory = vi.hoisted(() => ({ io: vi.fn() }));
vi.mock('socket.io-client', () => ({ io: socketFactory.io }));

import { FLEET_ACK_TIMEOUT_MS, useFleetRconSession } from '../useFleetRconSession';
import {
  acquireRconSocket,
  releaseRconSocket,
  resetRconSocketForTests,
} from '../rconSocketTransport';

const one = { host_id: 1, instance_id: 11 };
const two = { host_id: 2, instance_id: 22 };
const three = { host_id: 3, instance_id: 33 };
const four = { host_id: 4, instance_id: 44 };

function createSocket(connected = false) {
  const listeners = new Map();
  const callbacks = new Map();
  const socket = {
    connected,
    disconnect: vi.fn(() => { socket.connected = false; }),
    removeAllListeners: vi.fn(() => listeners.clear()),
    on: vi.fn((event, fn) => {
      const handlers = listeners.get(event) ?? new Set();
      handlers.add(fn);
      listeners.set(event, handlers);
    }),
    off: vi.fn((event, fn) => listeners.get(event)?.delete(fn)),
    emit: vi.fn((event, payload, callback) => {
      if (callback) {
        const pending = callbacks.get(event) ?? [];
        pending.push(callback);
        callbacks.set(event, pending);
      }
    }),
    trigger(event, payload) {
      if (event === 'connect') socket.connected = true;
      if (event === 'disconnect') socket.connected = false;
      for (const fn of [...(listeners.get(event) ?? [])]) fn(payload);
    },
    ack(event, payload, index = 0) { callbacks.get(event)?.[index]?.(payload); },
    listenerCount(event) { return listeners.get(event)?.size ?? 0; },
  };
  return socket;
}

function mount(socket, overrides = {}, options = {}) {
  socketFactory.io.mockReturnValue(socket);
  const initialProps = {
    enabled: true,
    targets: [one],
    onMessage: vi.fn(),
    onStatus: vi.fn(),
    ...overrides,
  };
  return renderHook((props) => useFleetRconSession(props), {
    initialProps,
    ...options,
  });
}

const calls = (socket, event) => socket.emit.mock.calls.filter(([name]) => name === event);
const state = (result, target) => result.current.statuses.get(`${target.host_id}:${target.instance_id}`);
const ready = (target, reason) => ({ ...target, state: 'ready', ...(reason ? { reason } : {}) });
const rejected = (target, reason) => ({ ...target, state: 'rejected', reason });

beforeEach(() => {
  vi.useFakeTimers();
  resetRconSocketForTests();
  socketFactory.io.mockReset();
});
afterEach(() => {
  resetRconSocketForTests();
  vi.useRealTimers();
});

describe('useFleetRconSession lifecycle', () => {
  it('acquires the current shared socket, joins once with normalized complete targets, and emits no stats', () => {
    const socket = createSocket(true);
    const { result } = mount(socket, { targets: [one, { host_id: '1', instance_id: '11' }, two] });

    expect(result.current.connected).toBe(true);
    expect(calls(socket, 'rcon:fleet_join')).toEqual([
      ['rcon:fleet_join', { targets: [one, two] }, expect.any(Function)],
    ]);
    expect(socket.emit.mock.calls.some(([name]) => name.includes('stats'))).toBe(false);
    expect([...result.current.statuses]).toEqual([
      ['1:11', { state: 'connecting' }], ['2:22', { state: 'connecting' }],
    ]);
  });

  it('waits for async connect, installs only one listener of each kind, and cleans up its own listeners', () => {
    const socket = createSocket();
    const { unmount } = mount(socket);
    expect(calls(socket, 'rcon:fleet_join')).toHaveLength(0);
    for (const event of ['connect', 'disconnect', 'connect_error', 'rcon:status', 'rcon:message', 'rcon:error']) {
      expect(socket.listenerCount(event)).toBe(1);
    }

    act(() => socket.trigger('connect'));
    expect(calls(socket, 'rcon:fleet_join')).toHaveLength(1);
    const before = socket.emit.mock.calls.length;
    unmount();
    expect(socket.emit.mock.calls.slice(before)).toEqual([['rcon:fleet_leave', {}]]);
    for (const event of ['connect', 'disconnect', 'connect_error', 'rcon:status', 'rcon:message', 'rcon:error']) {
      expect(socket.listenerCount(event)).toBe(0);
    }
  });

  it('immediately invalidates add, removal, and re-add and emits each complete desired snapshot', () => {
    const socket = createSocket(true);
    const hook = mount(socket);
    act(() => socket.trigger('rcon:status', { ...one, status: 'connected' }));
    expect(state(hook.result, one)).toEqual({ state: 'ready' });

    hook.rerender({ ...hook.result.current, enabled: true, targets: [one, two] });
    expect(state(hook.result, one)).toEqual({ state: 'ready' });
    expect(state(hook.result, two)).toEqual({ state: 'connecting' });
    hook.rerender({ enabled: true, targets: [two], onMessage: vi.fn(), onStatus: vi.fn() });
    expect(hook.result.current.statuses.has('1:11')).toBe(false);
    hook.rerender({ enabled: true, targets: [one, two], onMessage: vi.fn(), onStatus: vi.fn() });
    expect(state(hook.result, one)).toEqual({ state: 'connecting' });
    expect(calls(socket, 'rcon:fleet_targets').map(([, payload]) => payload)).toEqual([
      { targets: [one, two] }, { targets: [two] }, { targets: [one, two] },
    ]);
  });

  it('uses monotonic lifecycle transitions when acknowledgements race statuses', () => {
    const socket = createSocket(true);
    const onStatus = vi.fn();
    const { result } = mount(socket, { targets: [one, two, three, four], onStatus });
    act(() => {
      socket.trigger('rcon:status', { ...one, status: 'connected' });
      socket.trigger('rcon:status', { ...three, status: 'error', reason: 'offline' });
      socket.ack('rcon:fleet_join', { targets: [
        { ...one, state: 'connecting' }, { ...two, state: 'rejected', reason: 'denied' },
        { ...three, state: 'rejected', reason: 'stale' }, { ...four, state: 'accepted' },
      ] });
    });
    expect(state(result, one)).toEqual({ state: 'ready' });
    expect(state(result, two)).toEqual({ state: 'failed', reason: 'denied' });
    expect(state(result, three)).toEqual({ state: 'failed', reason: 'offline' });
    expect(state(result, four)).toEqual({ state: 'connecting' });
    expect(onStatus).toHaveBeenCalledWith(ready(one));
    expect(onStatus).toHaveBeenCalledWith({ ...three, state: 'failed', reason: 'offline' });
  });

  it('marks only current exact targets from valid status and ignores stale or partial payloads', () => {
    const socket = createSocket(true);
    const { result } = mount(socket);
    act(() => {
      socket.trigger('rcon:status', { host_id: 1, status: 'connected' });
      socket.trigger('rcon:status', { instance_id: 11, status: 'connected' });
      socket.trigger('rcon:status', { ...two, status: 'connected' });
      socket.trigger('rcon:status', { ...one, status: 'connecting' });
    });
    expect(state(result, one)).toEqual({ state: 'connecting' });
    act(() => socket.trigger('rcon:status', { ...one, status: 'connected' }));
    expect(result.current.readyTargets).toEqual([one]);
    act(() => socket.trigger('rcon:status', { ...one, status: 'disconnected', reason: 'lost' }));
    expect(state(result, one)).toEqual({ state: 'failed', reason: 'lost' });
    act(() => socket.trigger('rcon:status', {
      host_id: '1', instance_id: '11', status: 'connected',
    }));
    expect(state(result, one)).toEqual({ state: 'failed', reason: 'lost' });
  });

  it('ignores stale target events while disconnected, then accepts fresh reconnect events before join ack', async () => {
    const socket = createSocket(true);
    const onMessage = vi.fn();
    const onStatus = vi.fn();
    const { result } = mount(socket, { targets: [one, two], onMessage, onStatus });
    act(() => {
      socket.trigger('rcon:status', { ...one, status: 'connected' });
      socket.trigger('rcon:status', { ...two, status: 'connected' });
    });
    onStatus.mockClear();
    act(() => socket.trigger('disconnect'));
    expect(result.current.connected).toBe(false);
    expect(state(result, one)).toEqual({ state: 'failed', reason: 'Socket disconnected' });
    expect(state(result, two)).toEqual({ state: 'failed', reason: 'Socket disconnected' });
    expect(onStatus.mock.calls.map(([value]) => value)).toEqual([
      { ...one, state: 'failed', reason: 'Socket disconnected' },
      { ...two, state: 'failed', reason: 'Socket disconnected' },
    ]);
    act(() => {
      socket.trigger('rcon:status', { ...one, status: 'connected' });
      socket.trigger('rcon:message', { ...one, content: 'stale output' });
      socket.trigger('rcon:error', { ...one, error: 'stale error' });
    });
    expect(state(result, one)).toEqual({ state: 'failed', reason: 'Socket disconnected' });
    expect(onStatus.mock.calls.map(([value]) => value)).toEqual([
      { ...one, state: 'failed', reason: 'Socket disconnected' },
      { ...two, state: 'failed', reason: 'Socket disconnected' },
    ]);
    expect(onMessage).not.toHaveBeenCalled();
    await expect(result.current.sendCommand('old', 'status', [one]))
      .resolves.toEqual({ run_id: 'old', targets: [rejected(one, 'Target is not ready')] });

    act(() => socket.trigger('connect'));
    expect(state(result, one)).toEqual({ state: 'connecting' });
    expect(state(result, two)).toEqual({ state: 'connecting' });
    expect(calls(socket, 'rcon:fleet_join')).toHaveLength(2);
    expect(result.current.readyTargets).toEqual([]);
    act(() => {
      socket.trigger('rcon:message', { ...one, content: 'fresh output' });
      socket.trigger('rcon:error', { ...one, error: 'fresh error' });
      socket.trigger('rcon:status', { ...one, status: 'connected' });
    });
    expect(state(result, one)).toEqual({ state: 'ready' });
    expect(state(result, two)).toEqual({ state: 'connecting' });
    expect(onMessage.mock.calls.map(([value]) => value)).toEqual([
      { ...one, content: 'fresh output' },
      { ...one, error: 'fresh error', type: 'error', content: 'fresh error' },
    ]);
    expect(onStatus.mock.calls.slice(2).map(([value]) => value)).toEqual([
      { ...one, state: 'failed', reason: 'fresh error' },
      { ...one, state: 'ready' },
    ]);
  });

  it('uses a safe connect_error message and ignores target events until a fresh connect', () => {
    const socket = createSocket(true);
    const onMessage = vi.fn();
    const onStatus = vi.fn();
    const { result } = mount(socket, { targets: [one, two], onMessage, onStatus });
    act(() => {
      socket.trigger('connect_error', new Error('transport unavailable'));
      socket.trigger('connect_error', new Error('transport unavailable'));
      socket.trigger('rcon:status', { ...one, status: 'connected' });
      socket.trigger('rcon:message', { ...one, content: 'stale output' });
      socket.trigger('rcon:error', { ...one, error: 'stale error' });
    });

    expect(state(result, one)).toEqual({ state: 'failed', reason: 'transport unavailable' });
    expect(state(result, two)).toEqual({ state: 'failed', reason: 'transport unavailable' });
    expect(onStatus).toHaveBeenCalledTimes(2);
    expect(onMessage).not.toHaveBeenCalled();
  });

  it('filters messages by both IDs and the latest desired set', () => {
    const socket = createSocket(true);
    const onMessage = vi.fn();
    const hook = mount(socket, { onMessage });
    act(() => {
      socket.trigger('rcon:message', { host_id: 1, content: 'partial' });
      socket.trigger('rcon:message', { ...two, content: 'wrong' });
      socket.trigger('rcon:message', { ...one, content: 'right' });
      socket.trigger('rcon:message', { host_id: '1', instance_id: '11', content: 'wrong types' });
    });
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith({ ...one, content: 'right' });
    hook.rerender({ enabled: true, targets: [], onMessage, onStatus: vi.fn() });
    act(() => socket.trigger('rcon:message', { ...one, content: 'late' }));
    expect(onMessage).toHaveBeenCalledTimes(1);
  });

  it('strictly filters errors, fails exact current targets once, and raw-routes duplicate evidence', () => {
    const socket = createSocket(true);
    const onMessage = vi.fn();
    const onStatus = vi.fn();
    const hook = mount(socket, { onMessage, onStatus });
    act(() => socket.trigger('rcon:status', { ...one, status: 'connected' }));
    onStatus.mockClear();

    act(() => {
      socket.trigger('rcon:error', { error: 'untagged' });
      socket.trigger('rcon:error', { host_id: 1, error: 'partial' });
      socket.trigger('rcon:error', { ...two, error: 'mismatch' });
      socket.trigger('rcon:error', { host_id: '1', instance_id: 11, error: 'wrong types' });
      socket.trigger('rcon:error', { host_id: 0, instance_id: 11, error: 'not positive' });
    });
    expect(state(hook.result, one)).toEqual({ state: 'ready' });
    expect(onStatus).not.toHaveBeenCalled();
    expect(onMessage).not.toHaveBeenCalled();

    const exact = { ...one, error: 'backend unavailable', timestamp: 'safe', run_id: 'run-1' };
    act(() => {
      socket.trigger('rcon:error', exact);
      socket.trigger('rcon:error', exact);
    });
    expect(state(hook.result, one)).toEqual({ state: 'failed', reason: 'backend unavailable' });
    expect(onStatus).toHaveBeenCalledTimes(1);
    expect(onStatus).toHaveBeenCalledWith({ ...one, state: 'failed', reason: 'backend unavailable' });
    expect(onMessage).toHaveBeenCalledTimes(2);
    expect(onMessage).toHaveBeenNthCalledWith(1, {
      ...exact, type: 'error', content: 'backend unavailable',
    });

    hook.rerender({ enabled: true, targets: [], onMessage, onStatus });
    act(() => socket.trigger('rcon:error', { ...one, reason: 'removed' }));
    expect(onStatus).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledTimes(2);
  });

  it('routes each exact error message before its deduped terminal status', () => {
    const socket = createSocket(true);
    const order = [];
    const onMessage = vi.fn((payload) => order.push(['message', payload]));
    const onStatus = vi.fn((payload) => order.push(['status', payload]));
    mount(socket, { onMessage, onStatus });
    const exact = { ...one, error: 'backend unavailable', timestamp: 'safe', run_id: 'run-1' };
    const message = { ...exact, type: 'error', content: 'backend unavailable' };
    const failed = { ...one, state: 'failed', reason: 'backend unavailable' };

    act(() => {
      socket.trigger('rcon:error', exact);
      socket.trigger('rcon:error', exact);
    });

    expect(order).toEqual([
      ['message', message],
      ['status', failed],
      ['message', message],
    ]);
    expect(onMessage).toHaveBeenCalledTimes(2);
    expect(onStatus).toHaveBeenCalledTimes(1);
  });

  it.each([
    [{ error: '', reason: 'reason text' }, 'reason text'],
    [{ error: '', reason: '' }, 'RCON error'],
  ])('normalizes an exact error reason from %j', (payload, reason) => {
    const socket = createSocket(true);
    const onMessage = vi.fn();
    const onStatus = vi.fn();
    const { result } = mount(socket, { onMessage, onStatus });

    act(() => socket.trigger('rcon:error', { ...one, ...payload }));

    expect(state(result, one)).toEqual({ state: 'failed', reason });
    expect(onStatus).toHaveBeenCalledWith({ ...one, state: 'failed', reason });
    expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({
      ...one, type: 'error', content: reason,
    }));
  });

  it('ignores an old selection acknowledgement after remove and re-add', () => {
    const socket = createSocket(true);
    const hook = mount(socket);
    hook.rerender({ enabled: true, targets: [], onMessage: vi.fn(), onStatus: vi.fn() });
    hook.rerender({ enabled: true, targets: [one], onMessage: vi.fn(), onStatus: vi.fn() });
    act(() => socket.ack('rcon:fleet_join', { targets: [{ ...one, state: 'rejected', reason: 'old' }] }));
    expect(state(hook.result, one)).toEqual({ state: 'connecting' });
  });

  it('ignores an acknowledgement from a superseded complete desired snapshot', () => {
    const socket = createSocket(true);
    const hook = mount(socket);
    hook.rerender({ enabled: true, targets: [one, two], onMessage: vi.fn(), onStatus: vi.fn() });
    hook.rerender({ enabled: true, targets: [one], onMessage: vi.fn(), onStatus: vi.fn() });
    act(() => socket.ack('rcon:fleet_targets', {
      targets: [{ ...one, state: 'rejected', reason: 'superseded' }],
    }, 0));
    expect(state(hook.result, one)).toEqual({ state: 'connecting' });
  });
});

describe('useFleetRconSession command acknowledgements', () => {
  function readyHook(targets = [one, two]) {
    const socket = createSocket(true);
    const hook = mount(socket, { targets });
    act(() => targets.forEach((target) => socket.trigger('rcon:status', { ...target, status: 'connected' })));
    return { socket, ...hook };
  }

  it('emits one ready-only snapshot and rejects non-ready targets deterministically', async () => {
    const { socket, result } = readyHook([one, two, three]);
    act(() => socket.trigger('rcon:status', { ...two, status: 'disconnected' }));
    let pending;
    act(() => { pending = result.current.sendCommand('run-1', ' status ', [one, two, three]); });
    expect(calls(socket, 'rcon:fleet_command')).toEqual([[
      'rcon:fleet_command', { run_id: 'run-1', cmd: ' status ', targets: [one, three] }, expect.any(Function),
    ]]);
    act(() => socket.ack('rcon:fleet_command', { run_id: 'run-1', targets: [
      { ...three, state: 'queued' }, { ...one, state: 'rejected', reason: 'busy' },
    ] }));
    await expect(pending).resolves.toEqual({ run_id: 'run-1', targets: [
      rejected(one, 'busy'), rejected(two, 'Target is not ready'), { ...three, state: 'queued' },
    ] });
  });

  it('normalizes order, missing, duplicate, and extra acknowledgement targets', async () => {
    const { socket, result } = readyHook();
    const pending = result.current.sendCommand('order', 'status', [two, one, two]);
    act(() => socket.ack('rcon:fleet_command', { run_id: 'order', targets: [
      { ...three, state: 'queued' }, { ...one, state: 'queued' }, { ...one, state: 'rejected' },
    ] }));
    await expect(pending).resolves.toEqual({ run_id: 'order', targets: [
      rejected(two, 'Missing command acknowledgement'), { ...one, state: 'queued' },
    ] });
  });

  it.each([
    ['malformed', null, 'Malformed command acknowledgement'],
    ['wrong run', { run_id: 'other', targets: [] }, 'Malformed command acknowledgement'],
    ['top-level error', { run_id: 'bad', error: 'secret backend text' }, 'Command acknowledgement error'],
  ])('safely settles a %s acknowledgement', async (_name, ack, reason) => {
    const { socket, result } = readyHook([one]);
    const pending = result.current.sendCommand('bad', 'status', [one]);
    act(() => socket.ack('rcon:fleet_command', ack));
    await expect(pending).resolves.toEqual({ run_id: 'bad', targets: [rejected(one, reason)] });
  });

  it('times out after exactly ten seconds and ignores its late callback', async () => {
    const { socket, result } = readyHook([one]);
    expect(FLEET_ACK_TIMEOUT_MS).toBe(10_000);
    const pending = result.current.sendCommand('slow', 'status', [one]);
    const observer = vi.fn();
    pending.then(observer);
    await act(async () => vi.advanceTimersByTimeAsync(9999));
    expect(observer).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTimeAsync(1));
    await expect(pending).resolves.toEqual({ run_id: 'slow', targets: [
      rejected(one, 'Command acknowledgement timed out'),
    ] });
    act(() => socket.ack('rcon:fleet_command', { run_id: 'slow', targets: [{ ...one, state: 'queued' }] }));
    expect(observer).toHaveBeenCalledOnce();
  });

  it('accepts a valid acknowledgement at 9,999ms without a timeout overwrite', async () => {
    const { socket, result } = readyHook([one]);
    const pending = result.current.sendCommand('boundary', 'status', [one]);

    await act(async () => vi.advanceTimersByTimeAsync(9_999));
    act(() => socket.ack('rcon:fleet_command', {
      run_id: 'boundary', targets: [{ ...one, state: 'queued' }],
    }));
    await act(async () => vi.advanceTimersByTimeAsync(1));

    await expect(pending).resolves.toEqual({
      run_id: 'boundary', targets: [{ ...one, state: 'queued' }],
    });
  });

  it('accepts a fresh command acknowledgement after an earlier timeout', async () => {
    const { socket, result } = readyHook([one]);
    const expired = result.current.sendCommand('expired', 'status', [one]);
    await act(async () => vi.advanceTimersByTimeAsync(FLEET_ACK_TIMEOUT_MS));
    await expect(expired).resolves.toEqual({
      run_id: 'expired', targets: [rejected(one, 'Command acknowledgement timed out')],
    });

    const fresh = result.current.sendCommand('fresh', 'status', [one]);
    expect(calls(socket, 'rcon:fleet_command')).toHaveLength(2);
    act(() => socket.ack('rcon:fleet_command', {
      run_id: 'fresh', targets: [{ ...one, state: 'queued' }],
    }, 1));

    await expect(fresh).resolves.toEqual({
      run_id: 'fresh', targets: [{ ...one, state: 'queued' }],
    });
  });

  it('preserves immediate non-ready results when emitted targets time out', async () => {
    const { socket, result } = readyHook([one, two, three]);
    act(() => {
      socket.trigger('rcon:status', { ...two, status: 'connecting' });
      socket.trigger('rcon:status', { ...three, status: 'error', reason: 'offline' });
    });
    const pending = result.current.sendCommand('mixed-timeout', 'status', [two, one, three]);

    await act(async () => vi.advanceTimersByTimeAsync(10_000));

    await expect(pending).resolves.toEqual({ run_id: 'mixed-timeout', targets: [
      rejected(two, 'Target is not ready'),
      rejected(one, 'Command acknowledgement timed out'),
      rejected(three, 'Target is not ready'),
    ] });
  });

  it('settles every pending command immediately on disconnect without retry', async () => {
    const { socket, result } = readyHook();
    const first = result.current.sendCommand('a', 'a', [one]);
    const second = result.current.sendCommand('b', 'b', [two]);
    act(() => socket.trigger('disconnect'));
    await expect(first).resolves.toEqual({ run_id: 'a', targets: [rejected(one, 'Socket disconnected')] });
    await expect(second).resolves.toEqual({ run_id: 'b', targets: [rejected(two, 'Socket disconnected')] });
    expect(calls(socket, 'rcon:fleet_command')).toHaveLength(2);
    act(() => socket.ack('rcon:fleet_command', {
      run_id: 'a', targets: [{ ...one, state: 'queued' }],
    }));
    await expect(first).resolves.toEqual({ run_id: 'a', targets: [rejected(one, 'Socket disconnected')] });
  });

  it('accepts a fresh command after disconnect, reconnect, and ready status', async () => {
    const { socket, result } = readyHook([one]);
    const interrupted = result.current.sendCommand('interrupted', 'status', [one]);
    act(() => socket.trigger('disconnect'));
    await expect(interrupted).resolves.toEqual({
      run_id: 'interrupted', targets: [rejected(one, 'Socket disconnected')],
    });

    act(() => socket.trigger('connect'));
    expect(calls(socket, 'rcon:fleet_command')).toHaveLength(1);
    act(() => socket.trigger('rcon:status', { ...one, status: 'connected' }));
    const fresh = result.current.sendCommand('reconnected', 'status', [one]);
    act(() => socket.ack('rcon:fleet_command', {
      run_id: 'reconnected', targets: [{ ...one, state: 'queued' }],
    }, 1));

    expect(calls(socket, 'rcon:fleet_command')).toHaveLength(2);
    await expect(fresh).resolves.toEqual({
      run_id: 'reconnected', targets: [{ ...one, state: 'queued' }],
    });
  });

  it.each(['disconnect', 'connect_error'])(
    'settles multiple mixed pending commands independently on %s', async (eventName) => {
      const { socket, result } = readyHook([one, two, three]);
      act(() => socket.trigger('rcon:status', { ...two, status: 'connecting' }));
      const first = result.current.sendCommand('mixed-a', 'a', [two, one]);
      const second = result.current.sendCommand('mixed-b', 'b', [three, two]);

      act(() => socket.trigger(eventName));

      await expect(first).resolves.toEqual({ run_id: 'mixed-a', targets: [
        rejected(two, 'Target is not ready'), rejected(one, 'Socket disconnected'),
      ] });
      await expect(second).resolves.toEqual({ run_id: 'mixed-b', targets: [
        rejected(three, 'Socket disconnected'), rejected(two, 'Target is not ready'),
      ] });
      expect(calls(socket, 'rcon:fleet_command')).toHaveLength(2);
    },
  );

  it('settles pending work on unmount and leaves before releasing the shared socket', async () => {
    const { socket, result, unmount } = readyHook([one]);
    const pending = result.current.sendCommand('gone', 'status', [one]);
    const before = socket.emit.mock.calls.length;
    unmount();
    expect(socket.emit.mock.calls.slice(before)).toEqual([['rcon:fleet_leave', {}]]);
    await expect(pending).resolves.toEqual({ run_id: 'gone', targets: [rejected(one, 'Fleet session closed')] });
    act(() => socket.ack('rcon:fleet_command', {
      run_id: 'gone', targets: [{ ...one, state: 'queued' }],
    }));
    await expect(pending).resolves.toEqual({ run_id: 'gone', targets: [rejected(one, 'Fleet session closed')] });
  });

  it('preserves immediate non-ready results when mixed pending work is unmounted', async () => {
    const { socket, result, unmount } = readyHook([one, two]);
    act(() => socket.trigger('rcon:status', { ...two, status: 'error', reason: 'offline' }));
    const pending = result.current.sendCommand('mixed-gone', 'status', [two, one]);

    unmount();

    await expect(pending).resolves.toEqual({ run_id: 'mixed-gone', targets: [
      rejected(two, 'Target is not ready'), rejected(one, 'Fleet session closed'),
    ] });
  });
});

describe('useFleetRconSession shared ownership', () => {
  it('does not disconnect an individual transport user when the fleet leaves', () => {
    const socket = createSocket(true);
    socketFactory.io.mockReturnValue(socket);
    acquireRconSocket();
    const { unmount } = mount(socket);
    unmount();
    vi.advanceTimersByTime(1000);
    expect(socket.disconnect).not.toHaveBeenCalled();
    releaseRconSocket({ immediate: true });
    expect(socket.disconnect).toHaveBeenCalledOnce();
  });

  it('has no duplicate listeners or leaked users under StrictMode', () => {
    const socket = createSocket(true);
    const { unmount } = mount(socket, {}, { wrapper: StrictMode });
    expect(socket.listenerCount('connect')).toBe(1);
    expect(socket.listenerCount('rcon:status')).toBe(1);
    unmount();
    vi.advanceTimersByTime(1000);
    expect(socket.listenerCount('connect')).toBe(0);
    expect(socket.disconnect).toHaveBeenCalledOnce();
  });
});
