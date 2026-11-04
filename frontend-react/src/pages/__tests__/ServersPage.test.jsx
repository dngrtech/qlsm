import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ServersPage from '../ServersPage';

const mocks = vi.hoisted(() => ({
  addNotification: vi.fn(),
  EditConfigModal: vi.fn(() => null),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  toggleExpand: vi.fn(),
  noop: vi.fn(),
  NullComponent: () => null,
  RconConsole: vi.fn(() => null),
  RuntimeUpgradeDialog: vi.fn(),
  serversData: [],
  stats: { totalHosts: 1, totalInstances: 0, runningInstances: 0 },
}));

vi.mock('../../hooks/useServers', () => ({
  POLLABLE_HOST_STATUSES: ['provisioning', 'configuring'],
  POLLABLE_INSTANCE_STATUSES: ['deploying'],
  useServers: () => ({
    serversData: mocks.serversData,
    stats: mocks.stats,
    loading: false,
    error: null,
    toggleExpand: mocks.toggleExpand,
    expandAll: mocks.noop,
    collapseAll: mocks.noop,
    refreshData: mocks.noop,
    deleteModal: { open: false, item: null, type: null },
    requestDeleteHost: mocks.noop,
    requestDeleteInstance: mocks.noop,
    confirmDelete: mocks.noop,
    closeDeleteModal: mocks.noop,
    restartModal: { open: false, instance: null },
    requestRestartInstance: mocks.noop,
    confirmRestart: mocks.noop,
    closeRestartModal: mocks.noop,
  }),
}));

vi.mock('../../components/hosts/SortableHostList', () => ({
  default: ({ hosts, renderHostCard }) => (
    <div>
      {hosts.map((host) => (
        <div key={host.id}>
          {renderHostCard(host, { attributes: {}, listeners: {} })}
        </div>
      ))}
    </div>
  ),
}));

vi.mock('../../components/instances/SortableInstanceList', () => ({
  default: ({ instances, renderInstanceContent }) => (
    <div>
      {instances.map((instance) => (
        <div key={instance.id}>{renderInstanceContent(instance)}</div>
      ))}
    </div>
  ),
}));

vi.mock('../../components/HostActionsMenu', () => ({
  default: ({ host, onOpenRuntimeUpgrade }) => (
    <>
      <button type="button">Actions</button>
      <button type="button" onClick={() => onOpenRuntimeUpgrade(host.id)}>{`upgrade-${host.id}`}</button>
    </>
  ),
}));

vi.mock('../../components/hosts/RuntimeUpgradeDialog', () => ({
  default: (props) => {
    mocks.RuntimeUpgradeDialog(props);
    return props.isOpen ? <div>{`upgrade-dialog ${props.host?.name}`}</div> : null;
  },
}));

vi.mock('../../components/StatusIndicator', () => ({
  default: ({ status }) => <span>{status}</span>,
}));

vi.mock('../../components/NotificationProvider', () => ({
  useNotification: () => ({
    addNotification: mocks.addNotification,
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
  }),
}));

vi.mock('../../hooks/useQlfilterActions', () => ({
  useQlfilterActions: () => ({ handleQlfilterAction: mocks.noop }),
}));

vi.mock('../../hooks/useHostRestart', () => ({
  useHostRestart: () => ({
    hostForRestart: null,
    isRestartModalOpen: false,
    requestRestart: mocks.noop,
    confirmRestart: mocks.noop,
    closeRestartModal: mocks.noop,
  }),
}));

vi.mock('../../hooks/useViewLogs', () => ({
  useViewLogs: () => ({
    selectedInstanceForLogs: null,
    isViewLogsModalOpen: false,
    openViewLogs: mocks.noop,
    closeViewLogs: mocks.noop,
  }),
}));

vi.mock('../../hooks/useViewChatLogs', () => ({
  useViewChatLogs: () => ({
    selectedInstanceForChatLogs: null,
    isViewChatLogsModalOpen: false,
    openViewChatLogs: mocks.noop,
    closeViewChatLogs: mocks.noop,
  }),
}));

vi.mock('../../hooks/useViewMinqlxLogs', () => ({
  useViewMinqlxLogs: () => ({
    selectedInstanceForMinqlxLogs: null,
    isViewMinqlxLogsModalOpen: false,
    openViewMinqlxLogs: mocks.noop,
    closeViewMinqlxLogs: mocks.noop,
  }),
}));

vi.mock('../../hooks/useInstanceLanRate', () => ({
  useInstanceLanRate: () => ({
    lanRateAction: null,
    isLanRateModalOpen: false,
    requestToggleLanRate: mocks.noop,
    confirmToggleLanRate: mocks.noop,
    closeLanRateModal: mocks.noop,
  }),
}));

vi.mock('../../hooks/useInstanceStopStart', () => ({
  useInstanceStopStart: () => ({
    stopStartAction: null,
    isStopStartModalOpen: false,
    requestStop: mocks.noop,
    requestStart: mocks.noop,
    confirmStopStart: mocks.noop,
    closeStopStartModal: mocks.noop,
  }),
}));

vi.mock('../../hooks/useWorkshopUpdate', () => ({
  useWorkshopUpdate: () => ({
    isWorkshopModalOpen: false,
    hostForWorkshopUpdate: null,
    openWorkshopModal: mocks.noop,
    closeWorkshopModal: mocks.noop,
    handleWorkshopUpdateSubmit: mocks.noop,
  }),
}));

vi.mock('../../hooks/useHostAutoRestart', () => ({
  useHostAutoRestart: () => ({
    isAutoRestartModalOpen: false,
    hostForAutoRestart: null,
    openAutoRestartModal: mocks.noop,
    closeAutoRestartModal: mocks.noop,
    handleAutoRestartSubmit: mocks.noop,
  }),
}));

vi.mock('../../hooks/useServerStatus', () => ({
  useServerStatus: () => ({}),
}));

vi.mock('../../hooks/useInstanceOrder', () => ({
  useInstanceOrder: () => ({
    getOrderedInstances: (_hostId, instances) => instances,
    setInstanceOrder: mocks.noop,
  }),
}));

vi.mock('../../hooks/useHostOrder', () => ({
  useHostOrder: () => ({
    getOrderedHosts: (hosts) => hosts,
    setHostOrder: mocks.noop,
  }),
}));

vi.mock('../../components/ConfirmationModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/hosts/HostDetailDrawer', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/hosts/AddHostModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/instances/AddInstanceModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/instances/InstanceDetailsModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/instances/EditInstanceConfigModal', () => ({
  default: (props) => {
    mocks.EditConfigModal(props);
    return props.isOpen ? <div>edit-config-modal</div> : null;
  },
}));
vi.mock('../../components/instances/ViewLogsModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/instances/ViewChatLogsModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/instances/ViewMinqlxLogsModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/RconConsoleModal', () => ({ default: mocks.RconConsole }));
vi.mock('../../components/instances/LiveServerStatusModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/hosts/ForceUpdateWorkshopModal', () => ({ default: mocks.NullComponent }));
vi.mock('../../components/hosts/HostAutoRestartScheduleModal', () => ({ default: mocks.NullComponent }));

describe('ServersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.serversData = [
      {
        id: 1,
        name: 'Arena Host',
        provider: 'standalone',
        region: null,
        ip_address: '203.0.113.10',
        status: 'active',
        qlfilter_status: 'active',
        timezone: 'UTC',
        is_standalone: true,
        expanded: false,
        instances: [],
      },
    ];
    mocks.stats = { totalHosts: 1, totalInstances: 0, runningInstances: 0 };
  });

  it('renders the QLFilter column in the active host-card layout', () => {
    render(
      <MemoryRouter>
        <ServersPage />
      </MemoryRouter>
    );

    expect(screen.getByText('QL-Filter')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'QLFilter enabled' })).toHaveAttribute(
      'src',
      '/images/qlfilter-on.png'
    );
  });

  it('does not mount the RCON console before an instance is selected', () => {
    render(
      <MemoryRouter>
        <ServersPage />
      </MemoryRouter>
    );

    expect(mocks.RconConsole).not.toHaveBeenCalled();
  });

  const renderPage = () => render(
    <MemoryRouter>
      <ServersPage />
    </MemoryRouter>
  );
  const rerenderPage = (view) => act(() => {
    view.rerender(
      <MemoryRouter>
        <ServersPage />
      </MemoryRouter>
    );
  });

  it('derives the runtime-upgrade host from the latest servers data', () => {
    const view = renderPage();
    expect(screen.queryByText(/upgrade-dialog/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('upgrade-1'));
    expect(screen.getByText('upgrade-dialog Arena Host')).toBeInTheDocument();

    // A poll replaces the host object: the dialog gets the new one, not a stale copy.
    mocks.serversData = [{ ...mocks.serversData[0], name: 'Renamed Host' }];
    rerenderPage(view);
    expect(screen.getByText('upgrade-dialog Renamed Host')).toBeInTheDocument();
    const last = mocks.RuntimeUpgradeDialog.mock.calls.at(-1)[0];
    expect(last.host).toBe(mocks.serversData[0]);
  });

  it('closes the runtime-upgrade dialog when its host disappears', () => {
    const view = renderPage();
    fireEvent.click(screen.getByText('upgrade-1'));
    expect(screen.getByText('upgrade-dialog Arena Host')).toBeInTheDocument();

    const host = mocks.serversData[0];
    mocks.serversData = [];
    rerenderPage(view);
    expect(screen.queryByText(/upgrade-dialog/)).not.toBeInTheDocument();

    // It does not pop back open if the host shows up again later.
    mocks.serversData = [host];
    rerenderPage(view);
    expect(screen.queryByText(/upgrade-dialog/)).not.toBeInTheDocument();
  });

});
