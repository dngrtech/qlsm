import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import InstanceActionsMenu from '../InstanceActionsMenu';

vi.mock('@headlessui/react', () => {
  const Menu = ({ children }) => <div>{children({ open: true })}</div>;
  Menu.Button = ({ children, ...props }) => <button {...props}>{children}</button>;
  Menu.Items = ({ children, ...props }) => <div {...props}>{children}</div>;
  Menu.Item = ({ children }) => children({ active: false });
  const Transition = ({ children }) => <>{children}</>;
  Transition.Child = ({ children }) => <>{children}</>;
  const Portal = ({ children }) => <>{children}</>;

  return { Menu, Portal, Transition };
});

vi.mock('@floating-ui/react-dom', () => ({
  autoUpdate: vi.fn(),
  flip: vi.fn(() => ({ name: 'flip' })),
  offset: vi.fn(() => ({ name: 'offset' })),
  shift: vi.fn(() => ({ name: 'shift' })),
  useFloating: () => ({
    x: 0,
    y: 0,
    strategy: 'absolute',
    refs: {
      setFloating: vi.fn(),
      setReference: vi.fn(),
    },
  }),
}));

vi.mock('../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="lan-rate-tooltip">{text}</span>,
}));

function renderMenu(instanceOverrides = {}) {
  const handleToggleLanRate = vi.fn();
  render(
    <InstanceActionsMenu
      instance={{
        id: 1,
        name: 'inst-1',
        status: 'running',
        lan_rate_enabled: false,
        host_os_type: 'debian',
        ...instanceOverrides,
      }}
      handleRestart={vi.fn()}
      handleDelete={vi.fn()}
      handleStop={vi.fn()}
      handleStart={vi.fn()}
      handleToggleLanRate={handleToggleLanRate}
      POLLABLE_INSTANCE_STATUSES={[]}
      onOpenEditConfigModal={vi.fn()}
      onViewInstanceDetails={vi.fn()}
      onViewLogs={vi.fn()}
      onViewChatLogs={vi.fn()}
      onOpenRconConsole={vi.fn()}
    />
  );

  return { handleToggleLanRate };
}

describe('InstanceActionsMenu lan rate guard', () => {
  it('disables the 99k action for ubuntu hosts when lan rate is off', () => {
    const { handleToggleLanRate } = renderMenu({
      host_os_type: 'ubuntu',
      lan_rate_enabled: false,
    });

    const actionButton = screen.getByRole('button', { name: /99k lan rate/i });
    expect(actionButton).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByTestId('lan-rate-tooltip')).toHaveTextContent('99k LAN rate is not compatible with Ubuntu.');

    fireEvent.click(actionButton);
    expect(handleToggleLanRate).not.toHaveBeenCalled();
  });

  it('allows disabling 99k for ubuntu hosts when already enabled', () => {
    const { handleToggleLanRate } = renderMenu({
      host_os_type: 'ubuntu',
      lan_rate_enabled: true,
    });

    const actionButton = screen.getByRole('button', { name: /99k lan rate/i });
    expect(actionButton).not.toBeDisabled();

    fireEvent.click(actionButton);
    expect(handleToggleLanRate).toHaveBeenCalledWith(1, 'inst-1', true);
  });
});
