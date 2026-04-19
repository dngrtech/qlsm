import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import InstanceBasicInfoForm from '../InstanceBasicInfoForm';

vi.mock('@headlessui/react', () => {
  const Listbox = ({ children }) => <div>{children({ open: false })}</div>;
  Listbox.Label = ({ children, ...props }) => <label {...props}>{children}</label>;
  Listbox.Button = ({ children, ...props }) => <button type="button" {...props}>{children}</button>;
  Listbox.Options = ({ children, ...props }) => <div {...props}>{children}</div>;
  Listbox.Option = ({ children, className }) => {
    const optionState = { selected: false, active: false };
    const resolvedClassName = typeof className === 'function'
      ? className(optionState)
      : className;

    return <div className={resolvedClassName}>{children(optionState)}</div>;
  };
  const Transition = ({ children }) => <>{children}</>;

  return { Listbox, Transition };
});

vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="lan-rate-tooltip">{text}</span>,
}));

describe('InstanceBasicInfoForm', () => {
  it('renders the Ubuntu lan rate reason in the shared tooltip slot', () => {
    render(
      <InstanceBasicInfoForm
        name=""
        onNameChange={vi.fn()}
        selectedHostId="2"
        onHostChange={vi.fn()}
        hosts={[{ id: 2, name: 'ubu-host', provider: 'self-hosted', ip_address: '203.0.113.10' }]}
        port=""
        onPortChange={vi.fn()}
        availablePorts={[]}
        loadingPorts={false}
        hostname=""
        onHostnameChange={vi.fn()}
        lanRateEnabled={false}
        onLanRateChange={vi.fn()}
        lanRateDisabled={true}
        lanRateUnavailableReason="99k LAN rate is not compatible with Ubuntu."
      />
    );

    expect(screen.getByText('99k LAN Rate')).toBeInTheDocument();
    expect(screen.getByTestId('lan-rate-tooltip')).toHaveTextContent('99k LAN rate is not compatible with Ubuntu.');
  });
});
