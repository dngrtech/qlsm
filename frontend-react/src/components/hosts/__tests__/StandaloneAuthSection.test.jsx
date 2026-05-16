import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import StandaloneAuthSection from '../StandaloneAuthSection';

it('switches to password bootstrap and shows the managed-key helper copy', () => {
  const onTestConnection = vi.fn();

  function Harness() {
    const [authMethod, setAuthMethod] = React.useState('key');
    const [sshPassword, setSshPassword] = React.useState('');

    return (
      <StandaloneAuthSection
        authMethod={authMethod}
        onAuthMethodChange={setAuthMethod}
        sshKey="-----BEGIN OPENSSH PRIVATE KEY-----"
        onSshKeyChange={() => {}}
        sshPassword={sshPassword}
        onSshPasswordChange={(e) => setSshPassword(e.target.value)}
        ipAddress="203.0.113.10"
        sshUser="root"
        connectionTestStatus="idle"
        connectionTestMessage=""
        onTestConnection={onTestConnection}
      />
    );
  }

  render(<Harness />);

  fireEvent.click(screen.getByRole('radio', { name: /password/i }));
  expect(screen.getByLabelText('SSH Password')).toBeInTheDocument();
  expect(screen.getByText(/managed SSH key/i)).toBeInTheDocument();
  expect(screen.getByText(/The password is not stored/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /test connection/i })).toBeDisabled();

  fireEvent.change(screen.getByLabelText('SSH Password'), { target: { value: 'bootstrap-secret' } });
  expect(screen.getByRole('button', { name: /test connection/i })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: /show/i }));
  expect(screen.getByLabelText('SSH Password')).toHaveAttribute('type', 'text');

  fireEvent.click(screen.getByRole('button', { name: /test connection/i }));
  expect(onTestConnection).toHaveBeenCalledTimes(1);
});

it('renders the detected OS message after a successful connection test', () => {
  render(
    <StandaloneAuthSection
      authMethod="password"
      onAuthMethodChange={() => {}}
      sshKey=""
      onSshKeyChange={() => {}}
      sshPassword="bootstrap-secret"
      onSshPasswordChange={() => {}}
      ipAddress="203.0.113.10"
      sshUser="root"
      connectionTestStatus="success"
      connectionTestMessage="Connection successful. Detected OS: Debian GNU/Linux 12 (bookworm)."
      onTestConnection={() => {}}
    />
  );

  expect(screen.getByText(/Detected OS: Debian GNU\/Linux 12/i)).toBeInTheDocument();
});

it('renders success details in green and the Ubuntu warning in red', () => {
  render(
    <StandaloneAuthSection
      authMethod="password"
      onAuthMethodChange={() => {}}
      sshKey=""
      onSshKeyChange={() => {}}
      sshPassword="bootstrap-secret"
      onSshPasswordChange={() => {}}
      ipAddress="203.0.113.10"
      sshUser="root"
      connectionTestStatus="success"
      connectionTestMessage="Connection successful. Detected OS: Ubuntu 24.04.2 LTS. Warning: 99k LAN rate is not compatible with Ubuntu."
      onTestConnection={() => {}}
    />
  );

  expect(screen.getByText(/Detected OS: Ubuntu 24\.04\.2 LTS/i)).toHaveStyle('color: #22d97f');
  expect(screen.getByText(/Warning: 99k LAN rate is not compatible with Ubuntu\./i)).toHaveStyle('color: var(--accent-danger)');
});

const renderSection = (overrides = {}) =>
  render(
    <StandaloneAuthSection
      authMethod="key"
      onAuthMethodChange={vi.fn()}
      sshKey="abc"
      onSshKeyChange={vi.fn()}
      sshPassword=""
      onSshPasswordChange={vi.fn()}
      ipAddress="203.0.113.40"
      sshUser="root"
      connectionTestStatus="idle"
      connectionTestMessage=""
      onTestConnection={vi.fn()}
      onSwitchToSelfHost={vi.fn()}
      {...overrides}
    />
  );

describe('StandaloneAuthSection — qlsm_redirect state', () => {
  it('shows the redirect banner with a "Continue as self-host" button', () => {
    renderSection({
      connectionTestStatus: 'qlsm_redirect',
      connectionTestMessage: 'This server is running QLSM. Add it as your self-host instead?',
    });

    expect(
      screen.getByText(/This server is running QLSM\. Add it as your self-host instead\?/)
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue as self-host/i })).toBeInTheDocument();
  });

  it('invokes onSwitchToSelfHost when the button is clicked', () => {
    const onSwitchToSelfHost = vi.fn();
    renderSection({
      connectionTestStatus: 'qlsm_redirect',
      connectionTestMessage: 'This server is running QLSM. Add it as your self-host instead?',
      onSwitchToSelfHost,
    });

    fireEvent.click(screen.getByRole('button', { name: /continue as self-host/i }));

    expect(onSwitchToSelfHost).toHaveBeenCalledTimes(1);
  });
});

describe('StandaloneAuthSection — qlsm_blocked state', () => {
  it('shows the blocked banner with no action button', () => {
    renderSection({
      connectionTestStatus: 'qlsm_blocked',
      connectionTestMessage: 'This server is your QLSM host and is already registered as a self-host.',
    });

    expect(
      screen.getByText(/This server is your QLSM host and is already registered as a self-host\./)
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /continue as self-host/i })).not.toBeInTheDocument();
  });
});
