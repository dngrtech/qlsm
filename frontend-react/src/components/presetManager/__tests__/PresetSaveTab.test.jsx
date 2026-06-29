import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PresetSaveTab from '../PresetSaveTab';

const mocks = vi.hoisted(() => ({ validatePresetName: vi.fn() }));
vi.mock('../../../services/api', () => ({ validatePresetName: mocks.validatePresetName }));
vi.mock('../PresetNameCombobox', () => ({
  default: ({ value, onChange }) => (
    <input aria-label="Preset Name" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

const presets = [
  { id: 1, name: 'duel-cfg', description: 'Comp duel', is_builtin: false },
  { id: 9, name: 'builtin-ffa', description: 'stock', is_builtin: true },
];

describe('PresetSaveTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.validatePresetName.mockResolvedValue({ is_valid: true });
  });

  const setup = (props = {}) => render(
    <PresetSaveTab
      presets={presets}
      onSavePreset={vi.fn()}
      onOverwritePreset={vi.fn()}
      isSaving={false}
      savedPreset={null}
      {...props}
    />
  );

  it('shows New preset mode and a Save Preset button for a brand-new name', async () => {
    const onSavePreset = vi.fn();
    setup({ onSavePreset });
    fireEvent.change(screen.getByLabelText('Preset Name'), { target: { value: 'fresh-name' } });
    expect(screen.getByText('New preset')).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: /save preset/i });
    fireEvent.click(btn);
    await waitFor(() => expect(onSavePreset).toHaveBeenCalledWith({ name: 'fresh-name', description: null }));
  });

  it('enters overwrite mode and auto-fills description when name matches a non-builtin preset', () => {
    setup();
    fireEvent.change(screen.getByLabelText('Preset Name'), { target: { value: 'duel-cfg' } });
    expect(screen.getByText('Overwriting')).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i).value).toBe('Comp duel');
    expect(screen.getByRole('button', { name: /overwrite preset/i })).toBeInTheDocument();
  });

  it('does NOT enter overwrite mode for a builtin name (stays New preset)', () => {
    setup();
    fireEvent.change(screen.getByLabelText('Preset Name'), { target: { value: 'builtin-ffa' } });
    expect(screen.getByText('New preset')).toBeInTheDocument();
  });

  it('respects a manually edited description on subsequent name changes', () => {
    setup();
    const desc = screen.getByLabelText(/description/i);
    fireEvent.change(desc, { target: { value: 'my own text' } });
    fireEvent.change(screen.getByLabelText('Preset Name'), { target: { value: 'duel-cfg' } });
    expect(desc.value).toBe('my own text');
  });

  it('calls onOverwritePreset with the matched id when overwriting', async () => {
    const onOverwritePreset = vi.fn();
    setup({ onOverwritePreset });
    fireEvent.change(screen.getByLabelText('Preset Name'), { target: { value: 'duel-cfg' } });
    fireEvent.click(screen.getByRole('button', { name: /overwrite preset/i }));
    await waitFor(() => expect(onOverwritePreset).toHaveBeenCalledWith(1, { description: 'Comp duel' }));
  });

  it('clears name and description via Save as new instead', () => {
    setup();
    fireEvent.change(screen.getByLabelText('Preset Name'), { target: { value: 'duel-cfg' } });
    fireEvent.click(screen.getByText(/save as new instead/i));
    expect(screen.getByLabelText('Preset Name').value).toBe('');
    expect(screen.getByText('New preset')).toBeInTheDocument();
  });
});
