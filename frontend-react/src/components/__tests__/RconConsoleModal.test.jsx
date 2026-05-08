import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import RconConsoleModal from '../RconConsoleModal';

const mocks = vi.hoisted(() => ({
  sendCommand: vi.fn(),
  subscribeStats: vi.fn(),
  unsubscribeStats: vi.fn(),
}));

vi.mock('../../hooks/useRconSocket', () => ({
  useRconSocket: (_instance, _isOpen, onMessage) => ({
    connected: true,
    status: 'connected',
    sendCommand: (cmd) => {
      onMessage({ type: 'command', content: cmd, timestamp: '12:00:00' });
      onMessage({ type: 'response', content: 'map: campgrounds', timestamp: '12:00:01' });
      mocks.sendCommand(cmd);
      return true;
    },
    subscribeStats: mocks.subscribeStats,
    unsubscribeStats: mocks.unsubscribeStats,
  }),
}));

describe('RconConsoleModal', () => {
  beforeAll(() => {
    const rect = {
      bottom: 0,
      height: 0,
      left: 0,
      right: 0,
      top: 0,
      width: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    };
    Range.prototype.getBoundingClientRect = () => rect;
    Range.prototype.getClientRects = () => [];
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('appends sent commands and RCON responses to the console', async () => {
    render(
      <RconConsoleModal
        isOpen={true}
        onClose={vi.fn()}
        instance={{ id: 15, host_id: 8, name: 'Arena', zmq_rcon_port: 28888 }}
      />
    );

    fireEvent.change(screen.getByPlaceholderText('Enter command...'), {
      target: { value: 'status' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(mocks.sendCommand).toHaveBeenCalledWith('status'));
    await waitFor(() => {
      expect(document.body).toHaveTextContent('> status');
      expect(document.body).toHaveTextContent('map: campgrounds');
    });
  });
});
