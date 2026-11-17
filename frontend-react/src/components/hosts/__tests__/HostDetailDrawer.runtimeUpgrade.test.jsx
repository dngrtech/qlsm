import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import HostDetailDrawer from '../HostDetailDrawer';
import { getHostById } from '../../../services/api';

vi.mock('../../../services/api', () => ({
  getHostById: vi.fn(),
  deleteHost: vi.fn(),
  updateHost: vi.fn(),
}));
vi.mock('../../NotificationProvider', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), addNotification: vi.fn() }),
}));
vi.mock('../../StatusIndicator', () => ({ default: () => null }));
vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="upgrade-tooltip">{text}</span>,
}));

const baseHost = {
  id: 7, name: 'h', ip_address: '10.0.0.7', provider: 'standalone', status: 'active',
  qlfilter_status: 'not_installed', instances: [], runtime: 'minqlx', is_standalone: true,
};

async function renderDrawer(runtimeUpgrade) {
  getHostById.mockResolvedValue({ ...baseHost, runtime_upgrade: runtimeUpgrade });
  const onOpenRuntimeUpgrade = vi.fn();
  render(
    <HostDetailDrawer host={7} open onClose={vi.fn()} onOpenRuntimeUpgrade={onOpenRuntimeUpgrade}
      onQlfilterAction={vi.fn()} onRequestRestart={vi.fn()} />
  );
  await screen.findByRole('button', { name: /restart/i });
  return { onOpenRuntimeUpgrade };
}

describe('HostDetailDrawer runtime upgrade button', () => {
  beforeEach(() => vi.clearAllMocks());

  it('is hidden when not visible', async () => {
    await renderDrawer({ visible: false, enabled: false, reason: null });
    expect(screen.queryByText('Upgrade to minqlxtended')).toBeNull();
  });

  it('is disabled with the reason tooltip', async () => {
    const { onOpenRuntimeUpgrade } = await renderDrawer({ visible: true, enabled: false, reason: 'needs Ubuntu 24.04' });
    const button = screen.getByRole('button', { name: /upgrade to minqlxtended/i });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(within(button).getByTestId('upgrade-tooltip')).toHaveTextContent('needs Ubuntu 24.04');
    fireEvent.click(button);
    expect(onOpenRuntimeUpgrade).not.toHaveBeenCalled();
  });

  it('calls onOpenRuntimeUpgrade when enabled', async () => {
    const { onOpenRuntimeUpgrade } = await renderDrawer({ visible: true, enabled: true, reason: null });
    fireEvent.click(screen.getByRole('button', { name: /upgrade to minqlxtended/i }));
    await waitFor(() => expect(onOpenRuntimeUpgrade).toHaveBeenCalledWith(7));
  });
});
