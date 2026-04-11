import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddHostModal from '../AddHostModal';

const mocks = vi.hoisted(() => ({
  createHost: vi.fn(),
  getHosts: vi.fn(),
  getSelfHostDefaults: vi.fn(),
  testHostConnection: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
  createHost: mocks.createHost,
  getHosts: mocks.getHosts,
  getSelfHostDefaults: mocks.getSelfHostDefaults,
  testHostConnection: mocks.testHostConnection,
}));

vi.mock('../../NotificationProvider', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
  }),
}));

vi.mock('../AddHostFormFields', () => ({
  default: (props) => (
    <div>
      <div data-testid="provider-value">{props.provider}</div>
      {(props.providerListOptions || []).map((option) => (
        <div key={option.id}>{option.name}</div>
      ))}
      <input aria-label="Host Name" value={props.name} onChange={props.onNameChange} onBlur={props.onNameBlur} />
      {(props.providerListOptions || []).some((option) => option.id === 'self') && (
        <button type="button" onClick={() => props.onProviderChange('self')}>Choose self</button>
      )}
      <button type="button" onClick={() => props.onTimezoneChange('UTC')}>Set timezone</button>
      <input aria-label="Server address" value={props.ipAddress || ''} onChange={props.onIpAddressChange} />
      <input aria-label="SSH User" value={props.sshUser || ''} onChange={props.onSshUserChange} />
    </div>
  ),
}));

describe('AddHostModal self provider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getHosts.mockResolvedValue([]);
    mocks.getSelfHostDefaults.mockResolvedValue({ ssh_user: 'rage', host_ip: '203.0.113.10' });
  });

  it('defaults to self when no self host exists and omits linode', async () => {
    mocks.createHost.mockResolvedValue({ message: 'Self host queued.' });

    render(<AddHostModal isOpen={true} onClose={vi.fn()} onHostAdded={vi.fn()} />);

    await waitFor(() => expect(mocks.getHosts).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('provider-value')).toHaveTextContent('self'));
    expect(screen.getByText('QLSM Host (self-deployment)')).toBeInTheDocument();
    expect(screen.getByText('Standalone')).toBeInTheDocument();
    expect(screen.getByText('VULTR')).toBeInTheDocument();
    expect(screen.queryByText(/linode/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Host Name'), { target: { value: 'self-host' } });
    await waitFor(() => expect(mocks.getSelfHostDefaults).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByLabelText('SSH User')).toHaveValue('rage'));
    await waitFor(() => expect(screen.getByLabelText('Server address')).toHaveValue('203.0.113.10'));
    fireEvent.click(screen.getByRole('button', { name: /set timezone/i }));
    fireEvent.click(screen.getByRole('button', { name: /add host/i }));

    await waitFor(() => expect(mocks.createHost).toHaveBeenCalledWith({
      name: 'self-host',
      provider: 'self',
      ip_address: '203.0.113.10',
      timezone: 'UTC',
      ssh_user: 'rage',
    }));
    expect(mocks.testHostConnection).not.toHaveBeenCalled();
  });

  it('hides self and defaults to standalone when a self host already exists', async () => {
    mocks.getHosts.mockResolvedValue([{ id: 7, provider: 'self', name: 'self-host' }]);

    render(<AddHostModal isOpen={true} onClose={vi.fn()} onHostAdded={vi.fn()} />);

    await waitFor(() => expect(mocks.getHosts).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('provider-value')).toHaveTextContent('standalone'));
    expect(screen.queryByText('QLSM Host (self-deployment)')).not.toBeInTheDocument();
    expect(screen.getByText('Standalone')).toBeInTheDocument();
    expect(screen.getByText('VULTR')).toBeInTheDocument();
    expect(screen.queryByText(/linode/i)).not.toBeInTheDocument();
    expect(mocks.getSelfHostDefaults).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /choose self/i })).not.toBeInTheDocument();
  });
});
