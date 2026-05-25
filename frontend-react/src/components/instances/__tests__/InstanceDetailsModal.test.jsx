import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import InstanceDetailsModal from '../InstanceDetailsModal';

const mocks = vi.hoisted(() => ({
  addNotification: vi.fn(),
  deleteInstance: vi.fn(),
  getInstanceById: vi.fn(),
  restartInstance: vi.fn(),
  startInstance: vi.fn(),
  stopInstance: vi.fn(),
  updateInstance: vi.fn(),
  updateInstanceLanRate: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
  deleteInstance: mocks.deleteInstance,
  getInstanceById: mocks.getInstanceById,
  restartInstance: mocks.restartInstance,
  startInstance: mocks.startInstance,
  stopInstance: mocks.stopInstance,
  updateInstance: mocks.updateInstance,
  updateInstanceLanRate: mocks.updateInstanceLanRate,
}));

vi.mock('@headlessui/react', () => {
  const Transition = ({ show, children }) => (show ? <>{children}</> : null);
  Transition.Root = ({ show, children }) => (show ? <>{children}</> : null);
  Transition.Child = ({ children }) => <>{children}</>;
  return { Transition };
});

vi.mock('../../ConfirmationModal', () => ({
  default: () => null,
}));

vi.mock('../../NotificationProvider', () => ({
  useNotification: () => ({
    addNotification: mocks.addNotification,
  }),
}));

vi.mock('../../StatusIndicator', () => ({
  default: ({ status }) => <span>{status}</span>,
}));

vi.mock('../LiveServerStatusModal', () => ({
  default: () => null,
}));

vi.mock('../../common/QlColorString', () => ({
  default: ({ children }) => <span>{children}</span>,
}));

vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="info-tooltip">{text}</span>,
}));

describe('InstanceDetailsModal lan rate guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.deleteInstance.mockResolvedValue({});
    mocks.restartInstance.mockResolvedValue({});
    mocks.startInstance.mockResolvedValue({});
    mocks.stopInstance.mockResolvedValue({});
    mocks.updateInstance.mockResolvedValue({});
    mocks.updateInstanceLanRate.mockResolvedValue({ message: 'updated' });
  });

  it('shows 99k as unavailable on ubuntu when disabled', async () => {
    mocks.getInstanceById.mockResolvedValue({
      id: 4,
      name: 'inst-4',
      host_id: 9,
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: false,
      host_ip_address: '203.0.113.10',
      port: 27960,
      hostname: 'Ubuntu Server',
      lan_rate_enabled: false,
      status: 'RUNNING',
    });

    render(
      <InstanceDetailsModal
        isOpen={true}
        instanceId={4}
        onClose={vi.fn()}
        onInstanceDeleted={vi.fn()}
        onInstanceUpdated={vi.fn()}
        onOpenEditConfig={vi.fn()}
        onOpenHostDrawer={vi.fn()}
        serverStatus={null}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).toBeDisabled();
    expect(screen.getByTestId('info-tooltip')).toHaveTextContent(/99k LAN Rate currently requires Debian/);
  });

  it('enables 99k on a migrated ubuntu host (lan_rate_uses_hook: true)', async () => {
    mocks.getInstanceById.mockResolvedValue({
      id: 11,
      name: 'inst-11',
      host_id: 12,
      host_name: 'ubuntu-migrated',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: true,
      host_ip_address: '203.0.113.20',
      port: 27962,
      hostname: 'Migrated Ubuntu',
      lan_rate_enabled: false,
      status: 'RUNNING',
    });

    render(
      <InstanceDetailsModal
        isOpen={true}
        instanceId={11}
        onClose={vi.fn()}
        onInstanceDeleted={vi.fn()}
        onInstanceUpdated={vi.fn()}
        onOpenEditConfig={vi.fn()}
        onOpenHostDrawer={vi.fn()}
        serverStatus={null}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).not.toBeDisabled();
    expect(screen.queryByTestId('info-tooltip')).not.toBeInTheDocument();
  });

  it('allows disabling 99k for ubuntu when already enabled', async () => {
    mocks.getInstanceById.mockResolvedValue({
      id: 5,
      name: 'inst-5',
      host_id: 10,
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: false,
      host_ip_address: '203.0.113.11',
      port: 27961,
      hostname: 'Ubuntu Server',
      lan_rate_enabled: true,
      status: 'RUNNING',
    });

    render(
      <InstanceDetailsModal
        isOpen={true}
        instanceId={5}
        onClose={vi.fn()}
        onInstanceDeleted={vi.fn()}
        onInstanceUpdated={vi.fn()}
        onOpenEditConfig={vi.fn()}
        onOpenHostDrawer={vi.fn()}
        serverStatus={null}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(toggle);

    await waitFor(() => expect(mocks.updateInstanceLanRate).toHaveBeenCalledWith(5, false));
  });

  it('shows assigned CPU affinity in details', async () => {
    mocks.getInstanceById.mockResolvedValue({
      id: 6,
      name: 'inst-6',
      host_id: 10,
      host_name: 'cpu-host',
      host_os_type: 'debian',
      host_ip_address: '203.0.113.12',
      port: 27960,
      hostname: 'CPU Server',
      lan_rate_enabled: false,
      status: 'RUNNING',
      cpu_affinity: 1,
    });

    render(
      <InstanceDetailsModal
        isOpen={true}
        instanceId={6}
        onClose={vi.fn()}
        onInstanceDeleted={vi.fn()}
        onInstanceUpdated={vi.fn()}
        onOpenEditConfig={vi.fn()}
        onOpenHostDrawer={vi.fn()}
        serverStatus={null}
      />
    );

    expect(await screen.findByText('CPU Affinity')).toBeInTheDocument();
    expect(screen.getByText('CPU 1')).toBeInTheDocument();
  });

  it('shows automatic CPU affinity when unset', async () => {
    mocks.getInstanceById.mockResolvedValue({
      id: 7,
      name: 'inst-7',
      host_id: 10,
      host_name: 'one-cpu-host',
      host_os_type: 'debian',
      host_ip_address: '203.0.113.13',
      port: 27961,
      hostname: 'Automatic Server',
      lan_rate_enabled: false,
      status: 'RUNNING',
      cpu_affinity: null,
    });

    render(
      <InstanceDetailsModal
        isOpen={true}
        instanceId={7}
        onClose={vi.fn()}
        onInstanceDeleted={vi.fn()}
        onInstanceUpdated={vi.fn()}
        onOpenEditConfig={vi.fn()}
        onOpenHostDrawer={vi.fn()}
        serverStatus={null}
      />
    );

    expect(await screen.findByText('CPU Affinity')).toBeInTheDocument();
    expect(screen.getByText('Automatic')).toBeInTheDocument();
  });
});
