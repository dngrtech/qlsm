import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import InstanceRowContent from '../InstanceRowContent';

vi.mock('../../StatusIndicator', () => ({
  default: ({ status }) => <span>{status}</span>,
}));

vi.mock('../../InstanceActionsMenu', () => ({
  default: () => <button type="button">Actions</button>,
}));

vi.mock('../PendingChangesModal', () => ({
  default: ({ instance, onRestart }) => (
    <div>
      pending-changes-modal {instance.id}
      <button type="button" onClick={() => onRestart(instance.id, instance.name)}>modal-restart</button>
    </div>
  ),
}));

function renderRow(overrides = {}) {
  const props = {
    inst: {
      id: 1,
      name: 'Inst',
      hostname: 'Host',
      port: 27960,
      status: 'running',
      lan_rate_enabled: false,
      ld_preload_hooks: 'a.so,b.so',
      ...overrides.inst,
    },
    host: { id: 1, ip_address: '203.0.113.1', os_type: 'debian' },
    pollableStatuses: [],
    serverStatus: null,
    onOpenDetails: vi.fn(),
    onOpenLiveStatus: vi.fn(),
    onRestart: vi.fn(),
    onDelete: vi.fn(),
    onStop: vi.fn(),
    onStart: vi.fn(),
    onToggleLanRate: vi.fn(),
    onEditConfig: vi.fn(),
    onViewLogs: vi.fn(),
    onViewChatLogs: vi.fn(),
    onOpenRcon: vi.fn(),
  };
  render(<InstanceRowContent {...props} />);
  return props;
}

describe('InstanceRowContent', () => {
  it('renders the instance name as a clickable link', () => {
    const props = renderRow();

    fireEvent.click(screen.getByRole('button', { name: 'Inst' }));

    expect(props.onOpenDetails).toHaveBeenCalledWith(1);
  });

  it('reads 25k on a minqlx host with the toggle off', () => {
    renderRow({ inst: { lan_rate_enabled: false, host_runtime: 'minqlx' } });

    expect(screen.getByText('25k')).toBeInTheDocument();
  });

  it('reads 99k on a minqlxtended host even with the stored flag off', () => {
    // QLSM runs these hosts at 99k, so the Rate column must not read 25k while
    // the details modal reads Enabled for the same instance.
    renderRow({ inst: { lan_rate_enabled: false, host_runtime: 'minqlxtended' } });

    expect(screen.getByText('99k')).toBeInTheDocument();
    expect(screen.queryByText('25k')).not.toBeInTheDocument();
  });

  it('opens the pending changes modal from the Updated badge and restarts from it', () => {
    const props = renderRow({ inst: { status: 'updated' } });

    expect(screen.queryByText(/pending-changes-modal/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /show pending changes/i }));
    expect(screen.getByText(/pending-changes-modal 1/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'modal-restart' }));
    expect(props.onRestart).toHaveBeenCalledWith(1, 'Inst');
  });

  it('keeps a plain status badge for other statuses', () => {
    renderRow({ inst: { status: 'running' } });

    expect(screen.queryByRole('button', { name: /show pending changes/i })).not.toBeInTheDocument();
  });
});
