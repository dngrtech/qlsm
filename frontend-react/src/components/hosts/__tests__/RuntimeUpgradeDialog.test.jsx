import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import RuntimeUpgradeDialog from '../RuntimeUpgradeDialog';
import { getRuntimeUpgrade, startRuntimeUpgrade, validateRuntimeUploadPlugin } from '../../../services/runtimeUpgradeApi';

vi.mock('../../../services/runtimeUpgradeApi', () => ({
  getRuntimeUpgrade: vi.fn(),
  startRuntimeUpgrade: vi.fn(),
  validateRuntimeUploadPlugin: vi.fn(),
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
    validateRuntimeUploadPlugin.mockResolvedValue({ path: 'x76admin.py', verdict: 'unknown' });
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

  const uploadPlan = {
    ...plan,
    instances: [
      { ...plan.instances[0], stripped: [row('x76admin.py', 'unavailable'), row('sub/deep.py', 'unavailable'), row('x76-bad.py', 'unavailable')] },
      { ...plan.instances[1], stripped: [row('x76admin.py', 'unavailable')] },
    ],
  };
  const pyFile = (text = 'code') => new File([text], 'x76admin.py', { type: 'text/x-python' });
  const uploadIn = async (user, instanceName, file = pyFile()) => {
    const region = screen.getByRole('region', { name: instanceName });
    await user.upload(within(region).getByTestId('upload-input-x76admin.py'), file);
  };

  it('mirrors an upload into other instances and sends the payload', async () => {
    getRuntimeUpgrade.mockResolvedValue(uploadPlan);
    const user = userEvent.setup();
    renderDialog();
    await screen.findByRole('region', { name: 'alpha' });
    await uploadIn(user, 'alpha');
    const beta = screen.getByRole('region', { name: 'beta' });
    expect(await within(beta).findByRole('button', { name: 'Replace x76admin.py' })).toBeInTheDocument();
    expect(within(beta).getByText(/Your uploaded version will be installed\./)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /upgrade$/i }));
    await waitFor(() => expect(startRuntimeUpgrade).toHaveBeenCalledWith(5, {
      fingerprint: 'fp-1',
      accepted_replacements: { 1: [], 2: [] },
      uploaded_files: { f1: { path: 'x76admin.py', text: 'code' } },
      uploaded_file_ids: { 1: { 'x76admin.py': 'f1' }, 2: { 'x76admin.py': 'f1' } },
    }));
  });

  it('offers no upload for nested or non-identifier paths', async () => {
    getRuntimeUpgrade.mockResolvedValue(uploadPlan);
    renderDialog();
    const alpha = await screen.findByRole('region', { name: 'alpha' });
    expect(within(alpha).queryByRole('button', { name: 'Upload sub/deep.py' })).toBeNull();
    expect(within(alpha).queryByRole('button', { name: 'Upload x76-bad.py' })).toBeNull();
    expect(within(alpha).getByRole('button', { name: 'Upload x76admin.py' })).toBeInTheDocument();
    expect(within(alpha).getAllByText(/won't be installed/)).toHaveLength(3);
  });

  it('drops uploads when the dialog is closed and reopened', async () => {
    getRuntimeUpgrade.mockResolvedValue(uploadPlan);
    const user = userEvent.setup();
    const { rerender } = render(<RuntimeUpgradeDialog isOpen host={host} onClose={vi.fn()} onStarted={vi.fn()} />);
    await screen.findByRole('region', { name: 'alpha' });
    await uploadIn(user, 'alpha');
    await within(screen.getByRole('region', { name: 'beta' })).findByRole('button', { name: 'Replace x76admin.py' });
    rerender(<RuntimeUpgradeDialog isOpen={false} host={host} onClose={vi.fn()} onStarted={vi.fn()} />);
    rerender(<RuntimeUpgradeDialog isOpen host={host} onClose={vi.fn()} onStarted={vi.fn()} />);
    await screen.findByRole('region', { name: 'alpha' });
    await user.click(screen.getByRole('button', { name: /upgrade$/i }));
    await waitFor(() => expect(startRuntimeUpgrade).toHaveBeenCalled());
    expect(startRuntimeUpgrade.mock.calls[0][1]).not.toHaveProperty('uploaded_files');
    expect(startRuntimeUpgrade.mock.calls[0][1]).not.toHaveProperty('uploaded_file_ids');
  });

  it('disables Upgrade while a check runs, and a close mid-check does not leak the counter', async () => {
    getRuntimeUpgrade.mockResolvedValue(uploadPlan);
    let resolve;
    validateRuntimeUploadPlugin.mockReturnValue(new Promise((r) => { resolve = r; }));
    const user = userEvent.setup();
    const { rerender } = render(<RuntimeUpgradeDialog isOpen host={host} onClose={vi.fn()} onStarted={vi.fn()} />);
    await screen.findByRole('region', { name: 'alpha' });
    await uploadIn(user, 'alpha');
    await waitFor(() => expect(screen.getByRole('button', { name: /upgrade$/i })).toBeDisabled());
    rerender(<RuntimeUpgradeDialog isOpen={false} host={host} onClose={vi.fn()} onStarted={vi.fn()} />);
    rerender(<RuntimeUpgradeDialog isOpen host={host} onClose={vi.fn()} onStarted={vi.fn()} />);
    await screen.findByRole('region', { name: 'alpha' });
    expect(screen.getByRole('button', { name: /upgrade$/i })).not.toBeDisabled();
    resolve({ path: 'x76admin.py', verdict: 'unknown' });
    await new Promise((r) => { setTimeout(r, 20); });
    expect(screen.getByRole('button', { name: /upgrade$/i })).not.toBeDisabled();
    expect(screen.getAllByRole('button', { name: 'Upload x76admin.py' })).toHaveLength(2);
  });

  it('reloads the plan, resets uploads and shows a note after a 409', async () => {
    getRuntimeUpgrade.mockResolvedValue(uploadPlan);
    startRuntimeUpgrade.mockRejectedValue({ response: { status: 409, data: { error: { message: 'Plan changed.' } } } });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByRole('region', { name: 'alpha' });
    await uploadIn(user, 'alpha');
    await within(screen.getByRole('region', { name: 'beta' })).findByRole('button', { name: 'Replace x76admin.py' });
    await user.click(screen.getByRole('button', { name: /upgrade$/i }));
    expect(await screen.findByText(/Uploads were reset because the plan changed/)).toBeInTheDocument();
    await waitFor(() => expect(getRuntimeUpgrade).toHaveBeenCalledTimes(2));
    const alpha = await screen.findByRole('region', { name: 'alpha' });
    expect(await within(alpha).findByRole('button', { name: 'Upload x76admin.py' })).toBeInTheDocument();
  });
});
