import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
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

describe('AddHostFormFields runtime radios', () => {
  it('starts with neither runtime selected', () => {
    // The choice is irreversible, so QLSM makes no pick on the operator's
    // behalf -- an unaware operator can never land on a runtime by default.
    render(<AddHostFormFields {...baseProps} runtime="" />);
    const radios = screen.getAllByRole('radio', { name: /minqlx/i });
    expect(radios).toHaveLength(2);
    radios.forEach(radio => expect(radio).not.toBeChecked());
  });

  it('checks only the selected runtime', () => {
    render(<AddHostFormFields {...baseProps} runtime="minqlxtended" />);
    expect(screen.getByRole('radio', { name: /^minqlxtended$/i })).toBeChecked();
    expect(screen.getByRole('radio', { name: /^minqlx$/i })).not.toBeChecked();
  });

  it('reports the runtime the operator picked', () => {
    const onRuntimeChange = vi.fn();
    render(<AddHostFormFields {...baseProps} runtime="" onRuntimeChange={onRuntimeChange} />);
    fireEvent.click(screen.getByRole('radio', { name: /^minqlxtended$/i }));
    expect(onRuntimeChange).toHaveBeenCalledWith('minqlxtended');
  });
});

describe('AddHostFormFields runtime tooltips', () => {
  const openTooltip = (runtimeId) => {
    fireEvent.mouseEnter(screen.getByTestId(`runtime-tooltip-${runtimeId}`));
    return screen.getByRole('tooltip');
  };

  it.each([
    ['minqlx', 'https://github.com/MinoMino/minqlx'],
    ['minqlxtended', 'https://github.com/tjone270/minqlxtended'],
  ])('links %s to its upstream repo', (runtimeId, repoUrl) => {
    // One render per runtime: InfoTooltip's close is debounced, so opening both
    // in a single render leaves two bubbles mounted at once.
    render(<AddHostFormFields {...baseProps} runtime="" />);
    expect(within(openTooltip(runtimeId)).getByRole('link')).toHaveAttribute('href', repoUrl);
  });

  it('opens repo links in a new tab without leaking the opener', () => {
    render(<AddHostFormFields {...baseProps} runtime="" />);
    const link = within(openTooltip('minqlx')).getByRole('link');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('tells a cloud operator QLSM provisions the OS', () => {
    render(<AddHostFormFields {...baseProps} provider="vultr" runtime="" />);
    expect(openTooltip('minqlxtended')).toHaveTextContent('QLSM provisions Ubuntu 24.04.');
  });

  it('tells a standalone operator the requirement is checked before creation', () => {
    render(<AddHostFormFields {...baseProps} provider="standalone" runtime="" />);
    expect(openTooltip('minqlxtended')).toHaveTextContent(/Ubuntu 24.04 or newer.*checked before the host is created/i);
  });

  it('warns a self-host operator that nothing is checked up front', () => {
    // This is the one path with no pre-check: the host is created, setup fails,
    // and it lands in Error with deleting it the only way back.
    render(<AddHostFormFields {...baseProps} provider="self" runtime="" />);
    expect(openTooltip('minqlxtended')).toHaveTextContent(/not checked up front/i);
  });
});
