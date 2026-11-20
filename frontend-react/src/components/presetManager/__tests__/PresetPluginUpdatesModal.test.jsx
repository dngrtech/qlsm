import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PresetPluginUpdatesModal from '../PresetPluginUpdatesModal';

const mocks = vi.hoisted(() => ({
  checkPresetPluginUpdates: vi.fn(),
  applyPresetPluginUpdates: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
  checkPresetPluginUpdates: mocks.checkPresetPluginUpdates,
  applyPresetPluginUpdates: mocks.applyPresetPluginUpdates,
}));

const staleResult = {
  preset_id: 3,
  name: 'duel',
  runtime: 'minqlx',
  plugin_changes: [{ name: 'stale.py', change: 'modified' }],
  plugins: [
    { name: 'custom.py', status: 'local' },
    { name: 'same.py', status: 'current' },
    { name: 'stale.py', status: 'outdated' },
  ],
};

const freshResult = {
  ...staleResult,
  plugin_changes: [],
  plugins: staleResult.plugins.map(p => ({ ...p, status: p.status === 'outdated' ? 'current' : p.status })),
};

describe('PresetPluginUpdatesModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists every plugin and only lets outdated ones be selected', async () => {
    mocks.checkPresetPluginUpdates.mockResolvedValue(staleResult);
    render(<PresetPluginUpdatesModal isOpen onClose={() => {}} preset={{ id: 3, name: 'duel' }} />);

    const stale = await screen.findByRole('checkbox', { name: /stale\.py/ });
    expect(stale).toBeChecked();
    expect(stale).toBeEnabled();
    expect(screen.getByRole('checkbox', { name: /same\.py/ })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /custom\.py/ })).toBeDisabled();
    expect(screen.getByText(/not in plugin pool/)).toBeInTheDocument();
    expect(mocks.checkPresetPluginUpdates).toHaveBeenCalledWith(3);
  });

  it('applies the selected files and re-checks', async () => {
    const user = userEvent.setup();
    const onApplied = vi.fn();
    mocks.checkPresetPluginUpdates
      .mockResolvedValueOnce(staleResult)
      .mockResolvedValueOnce(freshResult);
    mocks.applyPresetPluginUpdates.mockResolvedValue({
      data: { updated: ['stale.py'], skipped: [] },
      message: "Updated 1 plugin file(s) in preset 'duel'.",
    });
    render(<PresetPluginUpdatesModal isOpen onClose={() => {}} preset={{ id: 3, name: 'duel' }} onApplied={onApplied} />);

    await screen.findByRole('checkbox', { name: /stale\.py/ });
    await user.click(screen.getByRole('button', { name: /update selected/i }));

    await waitFor(() => expect(mocks.applyPresetPluginUpdates).toHaveBeenCalledWith(3, { files: ['stale.py'] }));
    expect(onApplied).toHaveBeenCalledWith({ updated: ['stale.py'], skipped: [] });
    expect(await screen.findByText(/Updated 1 plugin file/)).toBeInTheDocument();
    await waitFor(() => expect(mocks.checkPresetPluginUpdates).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: /update selected/i })).toBeDisabled();
  });

  it('shows the backend error', async () => {
    mocks.checkPresetPluginUpdates.mockRejectedValue({ error: { message: 'Built-in presets are updated with QLSM releases, not from here.' } });
    render(<PresetPluginUpdatesModal isOpen onClose={() => {}} preset={{ id: 1, name: 'default' }} />);
    expect(await screen.findByText(/Built-in presets are updated/)).toBeInTheDocument();
  });
});
