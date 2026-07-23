import { beforeEach, describe, expect, it, vi } from 'vitest';

const socketFactory = vi.hoisted(() => ({
  io: vi.fn(),
}));

vi.mock('socket.io-client', () => ({ io: socketFactory.io }));

import {
  acquireRconSocket,
  releaseRconSocket,
  resetRconSocketForTests,
} from '../rconSocketTransport';

function fakeSocket() {
  return {
    disconnect: vi.fn(),
    removeAllListeners: vi.fn(),
  };
}

describe('rconSocketTransport', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetRconSocketForTests();
    socketFactory.io.mockReset();
  });

  it('creates one configured socket and reuses it for every user', () => {
    const socket = fakeSocket();
    socketFactory.io.mockReturnValue(socket);

    expect(acquireRconSocket()).toBe(socket);
    expect(acquireRconSocket()).toBe(socket);
    expect(socketFactory.io).toHaveBeenCalledTimes(1);
    expect(socketFactory.io).toHaveBeenCalledWith('', expect.objectContaining({
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: 3,
      reconnectionDelay: 1000,
    }));
  });

  it('disconnects only after the final user and one-second grace period', () => {
    const socket = fakeSocket();
    socketFactory.io.mockReturnValue(socket);
    acquireRconSocket();
    acquireRconSocket();

    releaseRconSocket();
    vi.advanceTimersByTime(1000);
    expect(socket.disconnect).not.toHaveBeenCalled();

    releaseRconSocket();
    vi.advanceTimersByTime(999);
    expect(socket.disconnect).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(socket.disconnect).toHaveBeenCalledOnce();
  });

  it('supports immediate final release and never lets extra releases affect a new user', () => {
    const first = fakeSocket();
    const second = fakeSocket();
    socketFactory.io.mockReturnValueOnce(first).mockReturnValueOnce(second);

    acquireRconSocket();
    releaseRconSocket({ immediate: true });
    releaseRconSocket({ immediate: true });
    expect(first.disconnect).toHaveBeenCalledOnce();

    expect(acquireRconSocket()).toBe(second);
    releaseRconSocket({ immediate: true });
    expect(second.disconnect).toHaveBeenCalledOnce();
  });

  it('cancels a pending disconnect when reacquired', () => {
    const socket = fakeSocket();
    socketFactory.io.mockReturnValue(socket);
    acquireRconSocket();
    releaseRconSocket();

    expect(acquireRconSocket()).toBe(socket);
    vi.advanceTimersByTime(1000);
    expect(socket.disconnect).not.toHaveBeenCalled();

    releaseRconSocket({ immediate: true });
    expect(socket.disconnect).toHaveBeenCalledOnce();
  });

  it('reset clears pending lifecycle state and listeners', () => {
    const first = fakeSocket();
    const second = fakeSocket();
    socketFactory.io.mockReturnValueOnce(first).mockReturnValueOnce(second);
    acquireRconSocket();
    releaseRconSocket();

    resetRconSocketForTests();
    vi.advanceTimersByTime(1000);
    expect(first.removeAllListeners).toHaveBeenCalledOnce();
    expect(first.disconnect).toHaveBeenCalledOnce();
    expect(acquireRconSocket()).toBe(second);
  });
});
