import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import BackupRestorePage from '../BackupRestorePage';

const mocks = vi.hoisted(() => ({
  exportBackup: vi.fn(),
  importBackup: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  exportBackup: mocks.exportBackup,
  importBackup: mocks.importBackup,
}));

vi.mock('../../components/NotificationProvider', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}));

describe('BackupRestorePage export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.exportBackup.mockResolvedValue({ blob: new Blob(['x']), filename: 'qlsm-backup-test.qlsmbak' });
    window.URL.createObjectURL = vi.fn(() => 'blob:mock-url');
    window.URL.revokeObjectURL = vi.fn();
  });

  it('exports directly when a password is entered', async () => {
    render(<BackupRestorePage />);
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'secret123' } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'secret123' } });
    fireEvent.click(screen.getByRole('button', { name: /export backup/i }));

    await waitFor(() => {
      expect(mocks.exportBackup).toHaveBeenCalledWith('secret123');
    });
  });

  it('requires the risk checkbox before exporting with no password', async () => {
    render(<BackupRestorePage />);
    const exportButton = screen.getByRole('button', { name: /export backup/i });
    fireEvent.click(exportButton);

    // Risk modal appears; export must not have been called yet.
    expect(await screen.findByText(/i understand the risk/i)).toBeInTheDocument();
    expect(mocks.exportBackup).not.toHaveBeenCalled();

    const checkbox = screen.getByRole('checkbox', { name: /i understand the risk/i });
    const confirmButton = screen.getByRole('button', { name: /continue/i });
    expect(confirmButton).toBeDisabled();

    fireEvent.click(checkbox);
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mocks.exportBackup).toHaveBeenCalledWith(null);
    });
  });

  it('rejects mismatched password confirmation without calling the API', async () => {
    render(<BackupRestorePage />);
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'secret123' } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'different' } });
    fireEvent.click(screen.getByRole('button', { name: /export backup/i }));

    await waitFor(() => {
      expect(mocks.showError).toHaveBeenCalled();
    });
    expect(mocks.exportBackup).not.toHaveBeenCalled();
  });
});

describe('BackupRestorePage import', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.importBackup.mockResolvedValue({ message: 'Backup restored successfully.' });
  });

  const selectFile = () => {
    const file = new File(['backup contents'], 'backup.qlsmbak');
    const input = screen.getByLabelText(/backup file/i);
    fireEvent.change(input, { target: { files: [file] } });
    return file;
  };

  it('disables the import button until RESTORE is typed', async () => {
    render(<BackupRestorePage />);
    selectFile();
    const importButton = screen.getByRole('button', { name: /^import backup$/i });
    expect(importButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/type restore to confirm/i), { target: { value: 'RESTORE' } });
    expect(importButton).toBeEnabled();
  });

  it('calls importBackup with the file and password once confirmed', async () => {
    render(<BackupRestorePage />);
    selectFile();
    fireEvent.change(screen.getByLabelText(/backup password/i), { target: { value: 'pw' } });
    fireEvent.change(screen.getByLabelText(/type restore to confirm/i), { target: { value: 'RESTORE' } });
    fireEvent.click(screen.getByRole('button', { name: /^import backup$/i }));

    await waitFor(() => {
      expect(mocks.importBackup).toHaveBeenCalledWith(expect.any(File), 'pw');
      expect(mocks.showSuccess).toHaveBeenCalled();
    });
  });

  it('shows an explicit wipe warning before the confirm field is usable', () => {
    render(<BackupRestorePage />);
    expect(screen.getByText(/permanently wipe/i)).toBeInTheDocument();
  });

  it.each([true, false])('keeps restart guidance visible after import with addon_state_restored=%s', async (addonStateRestored) => {
    mocks.importBackup.mockResolvedValue({
      message: 'Backup restored successfully.',
      data: { restart_required: true, addon_state_restored: addonStateRestored },
    });
    render(<BackupRestorePage />);
    selectFile();
    const confirmation = screen.getByLabelText(/type restore to confirm/i);
    fireEvent.change(confirmation, { target: { value: 'RESTORE' } });
    fireEvent.click(screen.getByRole('button', { name: /^import backup$/i }));

    const guidance = await screen.findByRole('alert');
    expect(confirmation).toHaveValue('');
    expect(guidance).toHaveTextContent(/restart.*all.*application.*worker/i);
    if (addonStateRestored) {
      expect(guidance).not.toHaveTextContent(/re-enable.*configure/i);
    } else {
      expect(guidance).toHaveTextContent(/re-enable.*configure/i);
    }
    fireEvent.change(confirmation, { target: { value: 'RE' } });
    expect(guidance).toBeVisible();
  });

  it('warns when the restored backup was made on a different QLSM version', async () => {
    mocks.importBackup.mockResolvedValue({ message: 'Backup restored successfully.', data: { qlsm_version: '0.0.1-does-not-match' } });
    render(<BackupRestorePage />);
    selectFile();
    fireEvent.change(screen.getByLabelText(/type restore to confirm/i), { target: { value: 'RESTORE' } });
    fireEvent.click(screen.getByRole('button', { name: /^import backup$/i }));

    await waitFor(() => {
      expect(mocks.showSuccess).toHaveBeenCalledWith(expect.stringMatching(/0\.0\.1-does-not-match/));
    });
  });
});
