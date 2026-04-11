import React from 'react';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import SelfHostFields from '../SelfHostFields';

vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="server-address-tooltip">{text}</span>,
}));

it('renders the Server address label and tooltip copy', () => {
  render(
    <SelfHostFields
      ipAddress="203.0.113.10"
      onIpAddressChange={() => {}}
      sshUser="root"
      onSshUserChange={() => {}}
      timezone="UTC"
      onTimezoneChange={() => {}}
    />
  );

  expect(screen.getByLabelText('Server address')).toBeInTheDocument();
  expect(screen.getByTestId('server-address-tooltip')).toHaveTextContent(
    'Address clients use to connect to this server.'
  );
});
