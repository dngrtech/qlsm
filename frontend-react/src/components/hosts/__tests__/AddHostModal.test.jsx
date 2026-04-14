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
      <div data-testid="auth-method-value">{props.standaloneAuthMethod || ''}</div>
      {(props.providerListOptions || []).map((option) => (
        <div key={option.id}>{option.name}</div>
      ))}
      <input aria-label="Host Name" value={props.name} onChange={props.onNameChange} onBlur={props.onNameBlur} />
      {(props.providerListOptions || []).some((option) => option.id === 'self') && (
        <button type="button" onClick={() => props.onProviderChange('self')}>Choose self</button>
      )}
      {(props.providerListOptions || []).some((option) => option.id === 'standalone') && (
        <button type="button" onClick={() => props.onProviderChange('standalone')}>Choose standalone</button>
      )}
      <button type="button" onClick={() => props.onTimezoneChange('UTC')}>Set timezone</button>
      <input aria-label="Server address" value={props.ipAddress || ''} onChange={props.onIpAddressChange} />
      <input aria-label="SSH User" value={props.sshUser || ''} onChange={props.onSshUserChange} />
      <button type="button" onClick={() => props.onStandaloneAuthMethodChange?.('password')}>Use password</button>
      <button type="button" onClick={() => props.onStandaloneAuthMethodChange?.('key')}>Use ssh key</button>
      <input aria-label="SSH Password" value={props.sshPassword || ''} onChange={props.onSshPasswordChange} />
      <textarea aria-label="SSH Private Key" value={props.sshKey || ''} onChange={props.onSshKeyChange} />
      <div data-testid="connection-status">{props.connectionTestStatus}</div>
      <div data-testid="connection-message">{props.connectionTestMessage}</div>
      <button type="button" onClick={props.onTestConnection}>Test connection</button>
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

  it('uses password bootstrap payloads and clears connection test state when auth changes', async () => {
    mocks.getHosts.mockResolvedValue([{ id: 7, provider: 'self', name: 'self-host' }]);
    mocks.testHostConnection
      .mockResolvedValueOnce({ success: true, message: 'Connection successful. Detected OS: Debian GNU/Linux 12 (bookworm).' })
      .mockResolvedValueOnce({ success: true, message: 'Connection successful. Detected OS: Ubuntu 24.04.2 LTS. Warning: 99k LAN rate is not compatible with Ubuntu.' });
    mocks.createHost.mockResolvedValue({ message: 'Standalone host added.' });

    render(<AddHostModal isOpen={true} onClose={vi.fn()} onHostAdded={vi.fn()} />);

    await waitFor(() => expect(screen.getByTestId('provider-value')).toHaveTextContent('standalone'));
    fireEvent.change(screen.getByLabelText('Host Name'), { target: { value: 'standalone-host' } });
    fireEvent.click(screen.getByRole('button', { name: /choose standalone/i }));
    fireEvent.click(screen.getByRole('button', { name: /use password/i }));
    fireEvent.change(screen.getByLabelText('Server address'), { target: { value: '198.51.100.25' } });
    fireEvent.change(screen.getByLabelText('SSH User'), { target: { value: 'root' } });
    fireEvent.change(screen.getByLabelText('SSH Password'), { target: { value: 'bootstrap-secret' } });
    fireEvent.click(screen.getByRole('button', { name: /set timezone/i }));
    fireEvent.click(screen.getByRole('button', { name: /test connection/i }));

    await waitFor(() => expect(mocks.testHostConnection).toHaveBeenCalledWith(expect.objectContaining({
      ip_address: '198.51.100.25',
      ssh_port: 22,
      ssh_user: 'root',
      ssh_auth_method: 'password',
      ssh_password: 'bootstrap-secret',
    })));
    await waitFor(() => expect(screen.getByTestId('connection-status')).toHaveTextContent('success'));

    fireEvent.click(screen.getByRole('button', { name: /use ssh key/i }));
    await waitFor(() => expect(screen.getByTestId('auth-method-value')).toHaveTextContent('key'));
    await waitFor(() => expect(screen.getByTestId('connection-status')).toHaveTextContent('idle'));
    fireEvent.click(screen.getByRole('button', { name: /use password/i }));
    await waitFor(() => expect(screen.getByTestId('auth-method-value')).toHaveTextContent('password'));
    await waitFor(() => expect(screen.getByTestId('connection-status')).toHaveTextContent('idle'));
    fireEvent.change(screen.getByLabelText('SSH Password'), { target: { value: 'bootstrap-secret' } });
    fireEvent.click(screen.getByRole('button', { name: /test connection/i }));
    await waitFor(() => expect(mocks.testHostConnection).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId('connection-status')).toHaveTextContent('success'));
    await waitFor(() => expect(screen.getByTestId('connection-message')).toHaveTextContent('99k LAN rate is not compatible with Ubuntu'));

    fireEvent.click(screen.getByRole('button', { name: /add host/i }));

    await waitFor(() => expect(mocks.createHost).toHaveBeenCalledWith({
      name: 'standalone-host',
      provider: 'standalone',
      ip_address: '198.51.100.25',
      ssh_port: 22,
      ssh_user: 'root',
      ssh_auth_method: 'password',
      ssh_password: 'bootstrap-secret',
      timezone: 'UTC',
    }));
  });
});
