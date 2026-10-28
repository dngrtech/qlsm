import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PendingChangesModal from '../PendingChangesModal';

const mocks = vi.hoisted(() => ({ getInstancePendingChanges: vi.fn() }));
vi.mock('../../../services/api', () => ({ getInstancePendingChanges: mocks.getInstancePendingChanges }));

const INSTANCE = { id: 3, name: 'duel-1' };

function renderModal(props = {}) {
  const onClose = vi.fn();
  const onRestart = vi.fn();
  render(
    <PendingChangesModal isOpen onClose={onClose} onRestart={onRestart} instance={INSTANCE} {...props} />,
  );
  return { onClose, onRestart };
}

describe('PendingChangesModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists recorded changes with a colored diff', async () => {
    mocks.getInstancePendingChanges.mockResolvedValue({
      instance_id: 3,
      status: 'updated',
      entries: [{
        id: 1,
        source: 'config_save',
        created_at: '2026-10-19T12:00:00',
        settings: [{ field: 'hostname', before: 'Old', after: 'New' }],
        files: [
          {
            path: 'server.cfg', change: 'modified', binary: false, truncated: false,
            diff: '--- a/server.cfg\n+++ b/server.cfg\n@@ -1 +1 @@\n-set g_gametype 1\n+set g_gametype 4\n',
          },
          { path: 'user-hooks/a.so', change: 'added', binary: true, truncated: false, diff: null },
        ],
      }],
    });

    renderModal();

    expect(await screen.findByText('server.cfg')).toBeInTheDocument();
    expect(mocks.getInstancePendingChanges).toHaveBeenCalledWith(3);
    expect(screen.getByText('Config saved without restart')).toBeInTheDocument();
    expect(screen.getByText('Server hostname:')).toBeInTheDocument();
    expect(screen.getByText('-set g_gametype 1').className).toMatch(/accent-danger/);
    expect(screen.getByText('+set g_gametype 4').className).toMatch(/accent-primary/);
    expect(screen.getByText('user-hooks/a.so')).toBeInTheDocument();
    expect(screen.getByText(/content not shown/i)).toBeInTheDocument();
    expect(screen.getByText(/any restart applies them/i)).toBeInTheDocument();
  });

  it('says so when nothing was recorded', async () => {
    mocks.getInstancePendingChanges.mockResolvedValue({ instance_id: 3, status: 'updated', entries: [] });

    renderModal();

    expect(await screen.findByText(/no change details were recorded/i)).toBeInTheDocument();
  });

  it('shows the API error', async () => {
    mocks.getInstancePendingChanges.mockRejectedValue({ error: { message: 'Instance not found.' } });

    renderModal();

    expect(await screen.findByText('Instance not found.')).toBeInTheDocument();
  });

  it('restarts through the existing restart action and closes', async () => {
    mocks.getInstancePendingChanges.mockResolvedValue({ instance_id: 3, status: 'updated', entries: [] });
    const { onClose, onRestart } = renderModal();
    await screen.findByText(/no change details/i);

    fireEvent.click(screen.getByRole('button', { name: /restart now/i }));

    expect(onRestart).toHaveBeenCalledWith(3, 'duel-1');
    expect(onClose).toHaveBeenCalled();
  });
});
