import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddHostModal from '../AddHostModal';

const mocks = vi.hoisted(() => ({
  createHost: vi.fn(),
  getSelfHostDefaults: vi.fn(),
  testHostConnection: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
  createHost: mocks.createHost,
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
      <input aria-label="Host Name" value={props.name} onChange={props.onNameChange} onBlur={props.onNameBlur} />
      <button type="button" onClick={() => props.onProviderChange('self')}>Choose self</button>
      <button type="button" onClick={() => props.onTimezoneChange('UTC')}>Set timezone</button>
      <input aria-label="Host Public IP" value={props.ipAddress || ''} onChange={props.onIpAddressChange} />
      <input aria-label="SSH User" value={props.sshUser || ''} onChange={props.onSshUserChange} />
    </div>
  ),
}));

describe('AddHostModal self provider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSelfHostDefaults.mockResolvedValue({ ssh_user: 'rage', host_ip: '203.0.113.10' });
  });

  it('loads defaults and submits a self-host payload without connection test', async () => {
    mocks.createHost.mockResolvedValue({ message: 'Self host queued.' });

    render(<AddHostModal isOpen={true} onClose={vi.fn()} onHostAdded={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Host Name'), { target: { value: 'self-host' } });
    fireEvent.click(screen.getByRole('button', { name: /choose self/i }));
    await waitFor(() => expect(mocks.getSelfHostDefaults).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByLabelText('SSH User')).toHaveValue('rage'));
    await waitFor(() => expect(screen.getByLabelText('Host Public IP')).toHaveValue('203.0.113.10'));
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
});
