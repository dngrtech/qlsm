import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import InstanceOptionsRow from '../InstanceOptionsRow';

vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => (
    <span data-testid={text.startsWith('99k') ? 'lan-rate-tooltip' : 'info-tooltip'}>{text}</span>
  ),
}));

describe('InstanceOptionsRow', () => {
  it('renders the Ubuntu lan rate reason in the shared tooltip slot', () => {
    render(
      <InstanceOptionsRow
        lanRateEnabled={false}
        onLanRateChange={vi.fn()}
        lanRateDisabled={true}
        lanRateUnavailableReason="99k LAN rate is not compatible with Ubuntu."
      />
    );

    expect(screen.getByText('99k LAN Rate')).toBeInTheDocument();
    expect(screen.getByTestId('lan-rate-tooltip')).toHaveTextContent('99k LAN rate is not compatible with Ubuntu.');
  });

  it('renders the lan rate toggle on and locked when QLSM fixes 99k on', () => {
    const onLanRateChange = vi.fn();
    render(
      <InstanceOptionsRow
        lanRateEnabled={false}
        onLanRateChange={onLanRateChange}
        lanRateDisabled={false}
        lanRateForcedOn={true}
        lanRateUnavailableReason="99k LAN rate: QLSM runs minqlxtended hosts at 99k."
      />
    );

    const toggle = screen.getByRole('button', { name: /Toggle 99k LAN Rate/ });
    expect(toggle).toBeDisabled();
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('lan-rate-tooltip')).toHaveTextContent('QLSM runs minqlxtended hosts at 99k');

    fireEvent.click(toggle);
    expect(onLanRateChange).not.toHaveBeenCalled();
  });

  const renderRow = (overrides = {}) => {
    const props = {
      lanRateEnabled: false,
      onLanRateChange: vi.fn(),
      lanRateDisabled: false,
      lanRateUnavailableReason: null,
      autoGeneratePasswords: true,
      onAutoGeneratePasswordsChange: vi.fn(),
      zmqStatsPassword: '',
      onZmqStatsPasswordChange: vi.fn(),
      zmqRconPassword: '',
      onZmqRconPasswordChange: vi.fn(),
      passwordErrors: {},
      ...overrides,
    };
    render(<InstanceOptionsRow {...props} />);
    return props;
  };

  it('checks Auto Generate Passwords and disables both inputs by default', () => {
    renderRow();

    expect(screen.getByLabelText('Auto Generate Passwords')).toBeChecked();
    expect(screen.getByLabelText('ZMQ Stats Password')).toBeDisabled();
    expect(screen.getByLabelText('ZMQ RCON Password')).toBeDisabled();
  });

  it('enables both inputs when auto generate is off', () => {
    renderRow({ autoGeneratePasswords: false });

    expect(screen.getByLabelText('Auto Generate Passwords')).not.toBeChecked();
    expect(screen.getByLabelText('ZMQ Stats Password')).toBeEnabled();
    expect(screen.getByLabelText('ZMQ RCON Password')).toBeEnabled();
  });

  it('reports checkbox changes to the parent', () => {
    const props = renderRow();

    fireEvent.click(screen.getByLabelText('Auto Generate Passwords'));

    expect(props.onAutoGeneratePasswordsChange).toHaveBeenCalledWith(false);
  });

  it('reports typed passwords to the parent', () => {
    const props = renderRow({ autoGeneratePasswords: false });

    fireEvent.change(screen.getByLabelText('ZMQ Stats Password'), { target: { value: 'Kp3-xR_9vT=2wQ' } });
    fireEvent.change(screen.getByLabelText('ZMQ RCON Password'), { target: { value: 'aB7_zQ2-mN4kLp' } });

    expect(props.onZmqStatsPasswordChange).toHaveBeenCalledWith('Kp3-xR_9vT=2wQ');
    expect(props.onZmqRconPasswordChange).toHaveBeenCalledWith('aB7_zQ2-mN4kLp');
  });

  it('marks a field invalid when the parent reports an error for it', () => {
    renderRow({ autoGeneratePasswords: false, passwordErrors: { stats: 'ZMQ Stats Password is required.' } });

    expect(screen.getByLabelText('ZMQ Stats Password')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('ZMQ RCON Password')).toHaveAttribute('aria-invalid', 'false');
  });

  it('keeps the typed value visible when auto generate is switched back on', () => {
    renderRow({ autoGeneratePasswords: true, zmqStatsPassword: 'Kp3-xR_9vT=2wQ' });

    const input = screen.getByLabelText('ZMQ Stats Password');
    expect(input).toBeDisabled();
    expect(input).toHaveValue('Kp3-xR_9vT=2wQ');
  });
});
