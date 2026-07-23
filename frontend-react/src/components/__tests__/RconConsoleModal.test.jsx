import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const socketFactory = vi.hoisted(() => ({ io: vi.fn() }));
const transportSpies = vi.hoisted(() => ({ releaseRconSocket: vi.fn() }));
vi.mock('socket.io-client', () => ({ io: socketFactory.io }));
vi.mock('../../hooks/rconSocketTransport', async (importOriginal) => {
  const actual = await importOriginal();
  transportSpies.releaseRconSocket.mockImplementation(actual.releaseRconSocket);
  return { ...actual, releaseRconSocket: transportSpies.releaseRconSocket };
});

import RconConsoleModal from '../RconConsoleModal';
import { resetRconSocketForTests } from '../../hooks/rconSocketTransport';

function createSocket() {
  const listeners = new Map();
  return {
    connected: false,
    emit: vi.fn(),
    disconnect: vi.fn(),
    removeAllListeners: vi.fn(() => listeners.clear()),
    on: vi.fn((event, listener) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event).add(listener);
    }),
    off: vi.fn((event, listener) => listeners.get(event)?.delete(listener)),
    trigger(event, payload) {
      if (event === 'connect') this.connected = true;
      if (event === 'disconnect') this.connected = false;
      [...(listeners.get(event) || [])].forEach((listener) => listener(payload));
    },
    listenerCount(event) {
      return listeners.get(event)?.size || 0;
    },
  };
}

const instance = { id: 15, host_id: 8, name: 'Arena', zmq_rcon_port: 28888 };
const target = { host_id: 8, instance_id: 15 };

function renderModal(socket) {
  socketFactory.io.mockReturnValue(socket);
  return render(<RconConsoleModal isOpen onClose={vi.fn()} instance={instance} />);
}

describe('RconConsoleModal', () => {
  beforeAll(() => {
    const rect = { bottom: 0, height: 0, left: 0, right: 0, top: 0, width: 0, x: 0, y: 0, toJSON: () => ({}) };
    Range.prototype.getBoundingClientRect = () => rect;
    Range.prototype.getClientRects = () => [];
    Element.prototype.getAnimations = () => [];
  });

  beforeEach(() => {
    resetRconSocketForTests();
    socketFactory.io.mockReset();
    transportSpies.releaseRconSocket.mockClear();
  });

  afterEach(() => resetRconSocketForTests());

  it('joins, sends a command, and appends the command and response', async () => {
    const socket = createSocket();
    renderModal(socket);
    act(() => socket.trigger('connect'));

    await waitFor(() => expect(socket.emit).toHaveBeenCalledWith('rcon:join', target));
    fireEvent.change(screen.getByPlaceholderText('Enter command...'), { target: { value: 'status' } });
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }));
    expect(socket.emit).toHaveBeenCalledWith('rcon:command', { ...target, cmd: 'status' });

    act(() => socket.trigger('rcon:message', { ...target, content: 'map: campgrounds' }));
    await waitFor(() => {
      expect(document.body).toHaveTextContent('> status');
      expect(document.body).toHaveTextContent('map: campgrounds');
    });
  });

  it('keeps connect and connect_error as global transport events', async () => {
    const socket = createSocket();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderModal(socket);

    act(() => socket.trigger('connect'));
    await waitFor(() => {
      expect(document.body).toHaveTextContent('connected');
      expect(socket.emit).toHaveBeenCalledWith('rcon:join', target);
    });

    act(() => socket.trigger('connect_error', new Error('transport unavailable')));
    await waitFor(() => {
      expect(document.body).toHaveTextContent('error');
      expect(document.body).toHaveTextContent('Connection error: transport unavailable');
    });
    consoleError.mockRestore();
  });

  it('subscribes stats by default, toggles them, and cleans up its room immediately', async () => {
    const socket = createSocket();
    const { unmount } = renderModal(socket);
    act(() => socket.trigger('connect'));
    await waitFor(() => expect(socket.emit).toHaveBeenCalledWith('rcon:subscribe_stats', target));

    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(() => expect(socket.emit).toHaveBeenCalledWith('rcon:unsubscribe_stats', target));
    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(() => {
      const subscriptions = socket.emit.mock.calls.filter(([event]) => event === 'rcon:subscribe_stats');
      expect(subscriptions).toHaveLength(2);
    });

    unmount();
    expect(socket.emit).toHaveBeenCalledWith('rcon:unsubscribe_stats', target);
    expect(socket.emit).toHaveBeenCalledWith('rcon:leave', target);
    expect(socket.disconnect).not.toHaveBeenCalled();
  });

  it('unsubscribes stats before leaving and releasing even when stats are disabled', async () => {
    const socket = createSocket();
    const { unmount } = renderModal(socket);
    act(() => socket.trigger('connect'));
    await waitFor(() => expect(socket.emit).toHaveBeenCalledWith('rcon:subscribe_stats', target));

    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(() => expect(socket.emit).toHaveBeenCalledWith('rcon:unsubscribe_stats', target));
    const emitCountBeforeCleanup = socket.emit.mock.calls.length;

    unmount();

    expect(socket.emit.mock.calls.slice(emitCountBeforeCleanup)).toEqual([
      ['rcon:unsubscribe_stats', target],
      ['rcon:leave', target],
    ]);
    expect(transportSpies.releaseRconSocket).toHaveBeenCalledOnce();
    expect(socket.emit.mock.invocationCallOrder.at(-1))
      .toBeLessThan(transportSpies.releaseRconSocket.mock.invocationCallOrder[0]);
  });

  it('rejoins on reconnect without duplicating listeners and removes its listeners on cleanup', async () => {
    const socket = createSocket();
    const { unmount } = renderModal(socket);
    expect(socket.listenerCount('connect')).toBe(1);
    expect(socket.listenerCount('rcon:message')).toBe(1);

    act(() => {
      socket.trigger('connect');
      socket.trigger('disconnect');
      socket.trigger('connect');
    });
    await waitFor(() => {
      const joins = socket.emit.mock.calls.filter(([event]) => event === 'rcon:join');
      expect(joins).toHaveLength(2);
    });
    expect(socket.listenerCount('connect')).toBe(1);

    unmount();
    expect(socket.listenerCount('connect')).toBe(0);
    expect(socket.listenerCount('rcon:message')).toBe(0);
  });

  it('routes targeted responses only to their individual console over the shared socket', async () => {
    const socket = createSocket();
    socketFactory.io.mockReturnValue(socket);
    render(
      <>
        <RconConsoleModal isOpen onClose={vi.fn()} instance={instance} />
        <RconConsoleModal isOpen onClose={vi.fn()} instance={{ ...instance, id: 16, name: 'Duel' }} />
      </>
    );
    expect(socketFactory.io).toHaveBeenCalledOnce();

    act(() => {
      socket.trigger('connect');
      socket.trigger('rcon:message', { ...target, content: 'arena-only output' });
    });
    await waitFor(() => {
      const matchingLines = [...document.querySelectorAll('.cm-line')]
        .filter((line) => line.textContent.includes('arena-only output'));
      expect(matchingLines).toHaveLength(1);
    });
  });

  describe.each([
    {
      eventName: 'rcon:status',
      eventData: { status: 'connecting' },
      visibleText: 'connecting',
    },
    {
      eventName: 'rcon:message',
      eventData: { content: 'strictly-targeted-message' },
      visibleText: 'strictly-targeted-message',
    },
    {
      eventName: 'rcon:stats',
      eventData: { event: { TYPE: 'STRICTLY_TARGETED_STATS' } },
      visibleText: 'STRICTLY_TARGETED_STATS',
    },
    {
      eventName: 'rcon:error',
      eventData: { error: 'RCON service unavailable' },
      visibleText: 'RCON service unavailable',
    },
  ])('$eventName target filtering', ({ eventName, eventData, visibleText }) => {
    it.each([
      ['missing both IDs', {}, false],
      ['missing host ID', { instance_id: target.instance_id }, false],
      ['missing instance ID', { host_id: target.host_id }, false],
      ['mismatched IDs', { host_id: 999, instance_id: 999 }, false],
      ['exact target match', target, true],
    ])('%s', async (_caseName, eventTarget, shouldApply) => {
      const socket = createSocket();
      renderModal(socket);

      act(() => socket.trigger(eventName, { ...eventData, ...eventTarget }));

      if (shouldApply) {
        await waitFor(() => expect(document.body).toHaveTextContent(visibleText));
      } else {
        await waitFor(() => expect(document.body).not.toHaveTextContent(visibleText));
      }
    });
  });

  it('clears the raw output', async () => {
    const socket = createSocket();
    renderModal(socket);
    act(() => {
      socket.trigger('connect');
      socket.trigger('rcon:message', { ...target, content: 'temporary output' });
    });
    await waitFor(() => expect(document.body).toHaveTextContent('temporary output'));

    fireEvent.click(screen.getByRole('button', { name: /clear/i }));
    await waitFor(() => expect(document.body).not.toHaveTextContent('temporary output'));
  });
});
