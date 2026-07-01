import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PresetManagerModal from '../PresetManagerModal';

vi.mock('@headlessui/react', () => {
  const Dialog = ({ open, children }) => (open ? <div role="dialog">{children}</div> : null);
  Dialog.Panel = ({ children }) => <div>{children}</div>;
  Dialog.Title = ({ children }) => <div>{children}</div>;
  const DialogBackdrop = () => <div />;
  return { Dialog, DialogBackdrop };
});
vi.mock('../PresetLoadTab', () => ({
  default: ({ onSelect, onRequestDelete, presets }) => (
    <div>
      <button onClick={() => onSelect(1)}>load-row</button>
      <button onClick={() => onRequestDelete(presets[0])}>delete-row</button>
    </div>
  ),
}));
vi.mock('../PresetSaveTab', () => ({ default: () => <div>save-tab-body</div> }));
vi.mock('../../ConfirmationModal', () => ({
  default: ({ isOpen, title, onConfirm, onClose }) =>
    isOpen ? (
      <div>
        <span>{title}</span>
        <button onClick={() => { onConfirm(); onClose(); }}>Confirm Action</button>
      </div>
    ) : null,
}));
const mocks = vi.hoisted(() => ({ deletePreset: vi.fn(), updatePreset: vi.fn(), triggerPresetDownload: vi.fn() }));
vi.mock('../../../services/api', () => ({ deletePreset: mocks.deletePreset, updatePreset: mocks.updatePreset }));
vi.mock('../../../utils/presetDownload', () => ({ triggerPresetDownload: mocks.triggerPresetDownload }));

const presets = [{ id: 1, name: 'duel-cfg', description: 'd', is_builtin: false }];

describe('PresetManagerModal', () => {
  beforeEach(() => vi.clearAllMocks());

  const base = {
    isOpen: true, onClose: vi.fn(), presets, isLoading: false,
    onLoadPreset: vi.fn(), onSavePreset: vi.fn(), onOverwritePreset: vi.fn(),
    onPresetDeleted: vi.fn(), savedPreset: null,
  };

  it('opens on the Load tab and shows Load Selected disabled until a row is selected', () => {
    render(<PresetManagerModal {...base} initialTab="load" />);
    const loadBtn = screen.getByRole('button', { name: /load selected/i });
    expect(loadBtn).toBeDisabled();
    fireEvent.click(screen.getByText('load-row'));
    expect(screen.getByRole('button', { name: /load selected/i })).not.toBeDisabled();
  });

  it('opens on the Save tab when initialTab is save', () => {
    render(<PresetManagerModal {...base} initialTab="save" />);
    expect(screen.getByText('save-tab-body')).toBeInTheDocument();
  });

  it('asks for load confirmation before calling onLoadPreset', () => {
    render(<PresetManagerModal {...base} initialTab="load" />);
    fireEvent.click(screen.getByText('load-row'));
    fireEvent.click(screen.getByRole('button', { name: /load selected/i }));
    expect(screen.getByText(/confirm load preset/i)).toBeInTheDocument();
  });

  it('calls onLoadPreset(selectedId) after the load dialog is confirmed', () => {
    const onLoadPreset = vi.fn();
    render(<PresetManagerModal {...base} initialTab="load" onLoadPreset={onLoadPreset} />);
    fireEvent.click(screen.getByText('load-row'));
    fireEvent.click(screen.getByRole('button', { name: /load selected/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Action' }));
    expect(onLoadPreset).toHaveBeenCalledWith(1);
  });

  it('surfaces an inline error and keeps the row when deletePreset rejects', async () => {
    mocks.deletePreset.mockRejectedValueOnce({ error: { message: 'server boom' } });
    const onPresetDeleted = vi.fn();
    render(<PresetManagerModal {...base} initialTab="load" onPresetDeleted={onPresetDeleted} />);
    fireEvent.click(screen.getByText('delete-row'));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Action' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/server boom/i);
    expect(onPresetDeleted).not.toHaveBeenCalled();
  });
});
