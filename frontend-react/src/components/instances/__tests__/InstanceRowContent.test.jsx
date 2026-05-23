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
    onOpenHooks: vi.fn(),
    onViewLogs: vi.fn(),
    onViewChatLogs: vi.fn(),
    onOpenRcon: vi.fn(),
  };
  render(<InstanceRowContent {...props} />);
  return props;
}

describe('InstanceRowContent', () => {
  it('opens Hooks from the hook badge', () => {
    const props = renderRow();

    fireEvent.click(screen.getByRole('button', { name: /open ld_preload hooks/i }));

    expect(props.onOpenHooks).toHaveBeenCalledWith(props.inst);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('hides the hook badge when no hooks are enabled', () => {
    renderRow({ inst: { ld_preload_hooks: null } });

    expect(screen.queryByRole('button', { name: /open ld_preload hooks/i })).not.toBeInTheDocument();
  });
});
