import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AddHostFormFields from '../AddHostFormFields';

vi.mock('../../common/FloatingListbox', () => ({
  default: ({ label, disabled = false }) => (
    <div
      data-testid={`listbox-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
      data-disabled={disabled ? 'true' : 'false'}
    >
      {label}
    </div>
  ),
}));

function renderFields(props = {}) {
  return render(
    <AddHostFormFields
      name="cloud-host"
      onNameChange={vi.fn()}
      nameError={null}
      onNameBlur={vi.fn()}
      provider="vultr"
      providerListOptions={[
        { id: 'self', name: 'QLSM Host (self-deployment)' },
        { id: 'standalone', name: 'Standalone' },
        { id: 'vultr', name: 'VULTR' },
      ]}
      onProviderChange={vi.fn()}
      vultrConfigured={false}
      vultrUnavailableMessage="Vultr deployment is unavailable until VULTR_API_KEY is added to the environment."
      selectedContinent="North America"
      onContinentChange={vi.fn()}
      vultrContinentOptions={[{ id: 'north-america', name: 'North America' }]}
      region=""
      onRegionChange={vi.fn()}
      vultrFilteredRegions={[{ id: 'ewr', city: 'New Jersey', country: 'US' }]}
      machineSize=""
      onMachineSizeChange={vi.fn()}
      currentSizes={[{ id: 'vc2-1c-1gb', name: 'vc2-1c-1gb' }]}
      ipAddress=""
      onIpAddressChange={vi.fn()}
      sshPort={22}
      onSshPortChange={vi.fn()}
      sshUser="root"
      onSshUserChange={vi.fn()}
      standaloneAuthMethod="key"
      onStandaloneAuthMethodChange={vi.fn()}
      sshKey=""
      onSshKeyChange={vi.fn()}
      sshPassword=""
      onSshPasswordChange={vi.fn()}
      timezone=""
      onTimezoneChange={vi.fn()}
      connectionTestStatus="idle"
      connectionTestMessage=""
      onTestConnection={vi.fn()}
      {...props}
    />
  );
}

describe('AddHostFormFields', () => {
  it('shows the Vultr env warning and disables cloud controls when Vultr is unavailable', () => {
    renderFields();

    expect(screen.getByText(/Vultr deployment is unavailable until VULTR_API_KEY is added to the environment\./i)).toBeInTheDocument();
    expect(screen.getByTestId('vultr-cloud-fields')).toHaveClass('opacity-50');
    expect(screen.getByTestId('listbox-provider')).toHaveAttribute('data-disabled', 'false');
    expect(screen.getByTestId('listbox-continent')).toHaveAttribute('data-disabled', 'true');
    expect(screen.getByTestId('listbox-region')).toHaveAttribute('data-disabled', 'true');
    expect(screen.getByTestId('listbox-machine-size-plan')).toHaveAttribute('data-disabled', 'true');
  });
});

const baseProps = {
  name: 'h', onNameChange: vi.fn(), nameError: null, onNameBlur: vi.fn(),
  provider: 'vultr', providerListOptions: [{ id: 'vultr', name: 'Vultr' }],
  onProviderChange: vi.fn(), vultrConfigured: true, vultrUnavailableMessage: '',
  selectedContinent: '', onContinentChange: vi.fn(), vultrContinentOptions: [],
  region: '', onRegionChange: vi.fn(), vultrFilteredRegions: [],
  machineSize: '', onMachineSizeChange: vi.fn(), currentSizes: [],
  ipAddress: '', onIpAddressChange: vi.fn(), sshPort: 22, onSshPortChange: vi.fn(),
  sshUser: '', onSshUserChange: vi.fn(),
  standaloneAuthMethod: 'key', onStandaloneAuthMethodChange: vi.fn(),
  sshKey: '', onSshKeyChange: vi.fn(), sshPassword: '', onSshPasswordChange: vi.fn(),
  timezone: '', onTimezoneChange: vi.fn(), connectionTestStatus: 'idle',
  connectionTestMessage: '', onTestConnection: vi.fn(), onSwitchToSelfHost: vi.fn(),
  osInfo: null, runtime: 'minqlx', onRuntimeChange: vi.fn(),
};

describe('AddHostFormFields runtime picker', () => {
  it('renders the runtime picker for every provider', () => {
    ['vultr', 'standalone', 'self'].forEach(provider => {
      const { unmount } = render(<AddHostFormFields {...baseProps} provider={provider} />);
      expect(screen.getByTestId('runtime-picker')).toBeInTheDocument();
      unmount();
    });
  });

  it('tells the operator the choice cannot be changed later', () => {
    render(<AddHostFormFields {...baseProps} />);
    expect(screen.getByTestId('runtime-immutable-warning')).toHaveTextContent(/cannot be changed/i);
  });
});
