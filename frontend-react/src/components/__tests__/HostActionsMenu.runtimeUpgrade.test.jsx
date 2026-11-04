import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import HostActionsMenu from '../HostActionsMenu';

vi.mock('@headlessui/react', () => {
  const Menu = ({ children }) => <div>{children({ open: true, close: vi.fn() })}</div>;
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
  useFloating: () => ({ x: 0, y: 0, strategy: 'absolute', refs: { setFloating: vi.fn(), setReference: vi.fn() } }),
}));

vi.mock('../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="upgrade-tooltip">{text}</span>,
}));

vi.mock('../ConfirmationModal', () => ({ default: () => null }));

vi.mock('../addons/AddonMenuSection', () => ({
  useAddonMenu: () => ({ modal: null, items: () => null }),
}));

function renderMenu(runtimeUpgrade) {
  const onOpenRuntimeUpgrade = vi.fn();
  render(
    <HostActionsMenu
      host={{ id: 7, name: 'h', status: 'active', runtime_upgrade: runtimeUpgrade }}
      handleDelete={vi.fn()}
      onOpenRuntimeUpgrade={onOpenRuntimeUpgrade}
    />
  );
  return { onOpenRuntimeUpgrade };
}

describe('HostActionsMenu runtime upgrade item', () => {
  it('hides item for minqlxtended host', () => {
    renderMenu({ visible: false, enabled: false, reason: null });
    expect(screen.queryByText('Upgrade to minqlxtended')).toBeNull();
  });

  it('disabled item shows info tooltip with reason', () => {
    const { onOpenRuntimeUpgrade } = renderMenu({ visible: true, enabled: false, reason: 'Debian hosts cannot be upgraded.' });
    const button = screen.getByRole('button', { name: /upgrade to minqlxtended/i });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByTestId('upgrade-tooltip')).toHaveTextContent('Debian hosts cannot be upgraded.');
    fireEvent.click(button);
    expect(onOpenRuntimeUpgrade).not.toHaveBeenCalled();
  });

  it('enabled item calls onOpenRuntimeUpgrade', () => {
    const { onOpenRuntimeUpgrade } = renderMenu({ visible: true, enabled: true, reason: null });
    const button = screen.getByRole('button', { name: /upgrade to minqlxtended/i });
    expect(button).toHaveAttribute('aria-disabled', 'false');
    expect(screen.queryByTestId('upgrade-tooltip')).toBeNull();
    fireEvent.click(button);
    expect(onOpenRuntimeUpgrade).toHaveBeenCalledWith(7);
  });
});
