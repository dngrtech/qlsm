import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SavePresetModal from '../SavePresetModal';

const mocks = vi.hoisted(() => ({
  validatePresetName: vi.fn(),
}));

vi.mock('@headlessui/react', () => {
  const Dialog = ({ open, children, ...props }) => (open ? <div role="dialog" {...props}>{children}</div> : null);
  Dialog.Panel = ({ children, transition: _transition, ...props }) => {
    void _transition;
    return <div {...props}>{children}</div>;
  };
  Dialog.Title = ({ children, ...props }) => <div {...props}>{children}</div>;
  const DialogBackdrop = ({ transition: _transition, ...props }) => {
    void _transition;
    return <div {...props} />;
  };

  return { Dialog, DialogBackdrop };
});

vi.mock('../../../services/api', () => ({
  validatePresetName: mocks.validatePresetName,
}));

describe('SavePresetModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.validatePresetName.mockResolvedValue({ is_valid: true });
  });

  it('does not call onSave when Enter is pressed after a preset has been saved', () => {
    const onSave = vi.fn();

    render(
      <SavePresetModal
        isOpen={true}
        onClose={vi.fn()}
        onSave={onSave}
        savedPreset={{ id: 42, name: 'saved-from-edit' }}
        onDownload={vi.fn()}
      />
    );

    const nameInput = screen.getByLabelText(/preset name/i);
    fireEvent.change(nameInput, { target: { value: 'another-preset' } });
    fireEvent.keyDown(nameInput, { key: 'Enter', code: 'Enter', charCode: 13 });

    expect(onSave).not.toHaveBeenCalled();
    expect(mocks.validatePresetName).not.toHaveBeenCalled();
  });

  it('shows a disabled download button with a hint before the preset is saved', () => {
    const onDownload = vi.fn();

    render(
      <SavePresetModal
        isOpen={true}
        onClose={vi.fn()}
        onSave={vi.fn()}
        savedPreset={null}
        onDownload={onDownload}
      />
    );

    const downloadButton = screen.getByRole('button', { name: /download preset/i });
    expect(downloadButton).toBeDisabled();

    fireEvent.click(downloadButton);
    expect(onDownload).not.toHaveBeenCalled();
  });

  it('does not render the download section when downloads are unsupported', () => {
    render(
      <SavePresetModal
        isOpen={true}
        onClose={vi.fn()}
        onSave={vi.fn()}
        savedPreset={null}
        onDownload={null}
      />
    );

    expect(screen.queryByRole('button', { name: /download preset/i })).not.toBeInTheDocument();
  });
});
