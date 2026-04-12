import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

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
