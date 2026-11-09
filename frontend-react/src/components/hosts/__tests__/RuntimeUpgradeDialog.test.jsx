import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import RuntimeUpgradeDialog from '../RuntimeUpgradeDialog';
import { getRuntimeUpgrade, startRuntimeUpgrade } from '../../../services/runtimeUpgradeApi';

vi.mock('../../../services/runtimeUpgradeApi', () => ({
  getRuntimeUpgrade: vi.fn(),
  startRuntimeUpgrade: vi.fn(),
}));

const row = (path, kind, extra = {}) => ({
  path, kind, verdict: 'incompatible', reasons: [`${path} reason`],
  replacement: kind === 'replaceable' ? path : null,
  from_catalog: false, originally_checked: true, ...extra,
});

const plan = {
  eligibility: { visible: true, enabled: true, reason: null },
  fingerprint: 'fp-1',
  instances: [
    {
      instance_id: 1, instance_name: 'alpha',
      stripped: [row('a_one.py', 'replaceable'), row('a_two.py', 'replaceable'), row('a_gone.py', 'unavailable')],
      replacements: {}, auto_accepted: ['auto.py'], checked_plugins: [],
    },
    {
      instance_id: 2, instance_name: 'beta',
      stripped: [row('b_one.py', 'replaceable')],
      replacements: {}, auto_accepted: [], checked_plugins: [],
    },
    { instance_id: 3, instance_name: 'gamma', stripped: [], replacements: {}, auto_accepted: [], checked_plugins: [] },
  ],
};

const host = { id: 5, name: 'ubuntu-host' };

function renderDialog(props = {}) {
  const onClose = vi.fn();
  const onStarted = vi.fn();
  render(<RuntimeUpgradeDialog isOpen host={host} onClose={onClose} onStarted={onStarted} {...props} />);
  return { onClose, onStarted };
}

describe('RuntimeUpgradeDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getRuntimeUpgrade.mockResolvedValue(plan);
    startRuntimeUpgrade.mockResolvedValue({ data: { status: 'configuring' } });
  });

  it('renders rows grouped per instance', async () => {
    renderDialog();
    const alpha = await screen.findByRole('region', { name: 'alpha' });
    expect(within(alpha).getByText('a_one.py')).toBeInTheDocument();
    expect(within(alpha).getByText('a_gone.py')).toBeInTheDocument();
    const beta = screen.getByRole('region', { name: 'beta' });
    expect(within(beta).getByText('b_one.py')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'gamma' })).toBeNull();
    expect(getRuntimeUpgrade).toHaveBeenCalledWith(5);
  });

  it('unavailable row has no checkbox', async () => {
    renderDialog();
    const alpha = await screen.findByRole('region', { name: 'alpha' });
    expect(within(alpha).getAllByRole('checkbox')).toHaveLength(2);
    expect(within(alpha).getAllByRole('checkbox').every((box) => box.checked)).toBe(true);
    expect(screen.queryByRole('checkbox', { name: /a_gone\.py/ })).toBeNull();
  });

  it('posts ticked paths per instance', async () => {
    const user = userEvent.setup();
    const { onClose, onStarted } = renderDialog();
    await screen.findByRole('region', { name: 'alpha' });
    await user.click(screen.getByRole('checkbox', { name: /a_two\.py/ }));
    await user.click(screen.getByRole('button', { name: /upgrade$/i }));
    await waitFor(() => expect(startRuntimeUpgrade).toHaveBeenCalledWith(5, {
      fingerprint: 'fp-1',
      accepted_replacements: { 1: ['a_one.py'], 2: ['b_one.py'], 3: [] },
    }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onStarted).toHaveBeenCalledWith(5);
  });

  it('shows confirmation text when nothing to decide', async () => {
    getRuntimeUpgrade.mockResolvedValue({
      ...plan, instances: [{ ...plan.instances[2] }],
    });
    renderDialog();
    expect(await screen.findByText(/Running instances on ubuntu-host will stop during the upgrade and start again\. Stopped instances stay stopped\. If the upgrade fails, QLSM restores minqlx and the original instance states\. Interrupted recovery continues when the host is reachable\./)).toBeInTheDocument();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('shows 409 message from the dry run', async () => {
    getRuntimeUpgrade.mockRejectedValue({ response: { status: 409, data: { error: { message: 'Host is busy.' } } } });
    renderDialog();
    expect(await screen.findByRole('alert')).toHaveTextContent('Host is busy.');
    expect(screen.getByRole('button', { name: /upgrade$/i })).toBeDisabled();
  });

  it('shows 409 message from the start request and stays open', async () => {
    const user = userEvent.setup();
    startRuntimeUpgrade.mockRejectedValue({ response: { status: 409, data: { error: { message: 'Plugins changed; review again.' } } } });
    const { onClose } = renderDialog();
    await screen.findByRole('region', { name: 'alpha' });
    await user.click(screen.getByRole('button', { name: /upgrade$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Plugins changed; review again.');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('labels disabled plugins and lists them after enabled ones', async () => {
    getRuntimeUpgrade.mockResolvedValue({
      ...plan,
      instances: [{
        instance_id: 1, instance_name: 'alpha',
        stripped: [
          row('a_off.py', 'unavailable', { originally_checked: false }),
          row('b_on.py', 'unavailable'),
        ],
        replacements: {}, auto_accepted: [], checked_plugins: ['b_on.py'],
      }],
    });
    renderDialog();
    const alpha = await screen.findByRole('region', { name: 'alpha' });
    const items = within(alpha).getAllByRole('listitem').filter((li) => li.parentElement.parentElement === alpha);
    expect(items.map((li) => li.querySelector('.text-sm').textContent)).toEqual(['b_on.py', 'a_off.py']);
    expect(within(items[1]).getByText('Not enabled')).toBeInTheDocument();
    expect(within(items[0]).queryByText('Not enabled')).not.toBeInTheDocument();
  });
});
