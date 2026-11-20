import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPage from '../SettingsPage';

const mocks = vi.hoisted(() => ({
  getApiKey: vi.fn(),
  regenerateApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
  getVultrKeySetting: vi.fn(),
  setVultrKeySetting: vi.fn(),
  getDeferRestartsSetting: vi.fn(),
  setDeferRestartsSetting: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  getApiKey: mocks.getApiKey,
  regenerateApiKey: mocks.regenerateApiKey,
  revokeApiKey: mocks.revokeApiKey,
  getVultrKeySetting: mocks.getVultrKeySetting,
  setVultrKeySetting: mocks.setVultrKeySetting,
  getDeferRestartsSetting: mocks.getDeferRestartsSetting,
  setDeferRestartsSetting: mocks.setDeferRestartsSetting,
}));

vi.mock('../../components/NotificationProvider', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}));

describe('SettingsPage Vultr key field', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getApiKey.mockResolvedValue(null);
    mocks.getVultrKeySetting.mockResolvedValue({ key: null });
    mocks.setVultrKeySetting.mockResolvedValue({ key: 'new-vultr-key' });
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: false });
  });

  it('saves the Vultr key and shows a success notification', async () => {
    render(<SettingsPage />);
    const input = await screen.findByLabelText(/vultr api key/i);
    fireEvent.change(input, { target: { value: 'new-vultr-key' } });
    fireEvent.click(screen.getByRole('button', { name: /save vultr key/i }));

    await waitFor(() => {
      expect(mocks.setVultrKeySetting).toHaveBeenCalledWith('new-vultr-key');
      expect(mocks.showSuccess).toHaveBeenCalled();
    });
  });
});

describe('SettingsPage Defer restarts toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getApiKey.mockResolvedValue(null);
    mocks.getVultrKeySetting.mockResolvedValue({ key: null });
  });

  it('shows the stored value and saves the flipped one', async () => {
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: false });
    mocks.setDeferRestartsSetting.mockResolvedValue({ enabled: true });
    render(<SettingsPage />);

    const toggle = screen.getByRole('button', { name: /toggle defer restarts/i });
    await waitFor(() => expect(mocks.getDeferRestartsSetting).toHaveBeenCalled());
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(toggle);

    await waitFor(() => expect(toggle).toHaveAttribute('aria-pressed', 'true'));
    expect(mocks.setDeferRestartsSetting).toHaveBeenCalledWith(true);
    expect(mocks.showSuccess).toHaveBeenCalled();
  });
});
