import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CheckForUpdatesModal from '../CheckForUpdatesModal';

const mocks = vi.hoisted(() => ({ getDeferRestartsSetting: vi.fn() }));
vi.mock('../../../services/api', () => ({ getDeferRestartsSetting: mocks.getDeferRestartsSetting }));

const RESULT = {
  common_pool_changes: [],
  instances: [{
    id: 5,
    name: 'duel-1',
    status: 'running',
    selected_plugin_changes: [
      { name: 'balance.py', change: 'modified' },
      { name: 'custom.py', change: 'modified' },
    ],
  }],
};

function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

function renderModal(onSubmit = vi.fn()) {
  render(
    <CheckForUpdatesModal
      isOpen
      onClose={vi.fn()}
      onSubmit={onSubmit}
      host={{ id: 1, name: 'host-1' }}
      isChecking={false}
      checkResult={RESULT}
      checkError={null}
    />,
  );
  return onSubmit;
}

describe('CheckForUpdatesModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('waits for the restart setting before selecting and submitting', async () => {
    const setting = deferred();
    mocks.getDeferRestartsSetting.mockReturnValue(setting.promise);
    renderModal();

    expect(screen.getByRole('button', { name: /update selected/i })).toBeDisabled();
    expect(screen.getByLabelText(/custom.py/)).not.toBeChecked();

    await act(async () => { setting.resolve({ enabled: true }); });

    expect(screen.getByLabelText(/custom.py/)).toBeChecked();
    expect(screen.getByLabelText(/restart to apply/i)).not.toBeChecked();
    expect(screen.getByRole('button', { name: /update selected/i })).toBeEnabled();
  });

  it('keeps the operator unticks once selections are initialised', async () => {
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: false });
    const onSubmit = renderModal();

    const custom = await screen.findByLabelText(/custom.py/);
    expect(custom).toBeChecked();
    fireEvent.click(custom);
    expect(custom).not.toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: /update selected/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      update_common_pool: false,
      instances: { 5: ['balance.py'] },
      restart_instances: [5],
    });
  });
});
