import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import EditPresetPage from '../EditPresetPage';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  getPresetById: vi.fn(),
  updatePreset: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => mocks.navigate,
  useParams: () => ({ presetId: '7' }),
}));

vi.mock('../../services/api', () => ({
  getPresetById: mocks.getPresetById,
  updatePreset: mocks.updatePreset,
}));

// A plain `() => null` mock would hide whether the admin list round-trips at
// all -- render what it is given and expose a setter, same as the call-site
// tests in EditInstanceConfigModal/AddInstanceForm.
vi.mock('../../components/operators/OwnerAdminEditor', () => ({
  default: ({ adminEntries, onAdminEntriesChange }) => (
    <div>
      {(adminEntries || []).map((entry) => (
        <span key={entry.steam_id64}>{`seeded:${entry.steam_id64}:${entry.level}`}</span>
      ))}
      <button
        type="button"
        onClick={() => onAdminEntriesChange([{ steam_id64: '76561198012345678', level: 2 }])}
      >
        set-admins
      </button>
    </div>
  ),
}));

describe('EditPresetPage admin list wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.alert = vi.fn();
    mocks.updatePreset.mockResolvedValue({});
  });

  it('omits admins entirely from a save on a legacy preset that never recorded a list', async () => {
    // Regression guard: this preset predates the admin feature (no admins.json),
    // so it loads with admins: null. Sending that back unconditionally is
    // rejected by the backend's admin validator ("admins must be a list."),
    // breaking save on every pre-existing preset.
    mocks.getPresetById.mockResolvedValue({
      name: 'legacy-preset',
      description: '',
      server_cfg: '',
      mappool: '',
      access: '',
      workshop: '',
      factory: '',
      admins: null,
    });

    render(<EditPresetPage />);

    await screen.findByDisplayValue('legacy-preset');
    fireEvent.click(screen.getByRole('button', { name: /update preset/i }));

    await waitFor(() => expect(mocks.updatePreset).toHaveBeenCalledTimes(1));
    const payload = mocks.updatePreset.mock.calls[0][1];
    expect(Object.prototype.hasOwnProperty.call(payload, 'admins')).toBe(false);
  });

  it('sends the edited admin list when the user touches the admin tab', async () => {
    mocks.getPresetById.mockResolvedValue({
      name: 'my-preset',
      description: '',
      server_cfg: '',
      mappool: '',
      access: '',
      workshop: '',
      factory: '',
      admins: null,
    });

    render(<EditPresetPage />);

    await screen.findByDisplayValue('my-preset');
    fireEvent.click(screen.getByRole('button', { name: 'set-admins' }));
    fireEvent.click(screen.getByRole('button', { name: /update preset/i }));

    await waitFor(() => expect(mocks.updatePreset).toHaveBeenCalledTimes(1));
    expect(mocks.updatePreset.mock.calls[0][1].admins)
      .toEqual([{ steam_id64: '76561198012345678', level: 2 }]);
  });

  it('seeds and re-sends an existing admin list untouched', async () => {
    mocks.getPresetById.mockResolvedValue({
      name: 'preset-with-admins',
      description: '',
      server_cfg: '',
      mappool: '',
      access: '',
      workshop: '',
      factory: '',
      admins: [{ steam_id64: '76561198087654321', level: 4 }],
    });

    render(<EditPresetPage />);

    await screen.findByText('seeded:76561198087654321:4');
    fireEvent.click(screen.getByRole('button', { name: /update preset/i }));

    await waitFor(() => expect(mocks.updatePreset).toHaveBeenCalledTimes(1));
    expect(mocks.updatePreset.mock.calls[0][1].admins)
      .toEqual([{ steam_id64: '76561198087654321', level: 4 }]);
  });
});
