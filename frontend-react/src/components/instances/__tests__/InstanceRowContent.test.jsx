import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import InstanceRowContent from '../InstanceRowContent';

vi.mock('../../StatusIndicator', () => ({
  default: ({ status }) => <span>{status}</span>,
}));

vi.mock('../../InstanceActionsMenu', () => ({
  default: () => <button type="button">Actions</button>,
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
});
