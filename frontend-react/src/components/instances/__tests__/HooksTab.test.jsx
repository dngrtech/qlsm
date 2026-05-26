import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HooksTab from '../HooksTab';
import * as api from '../../../services/api';

vi.mock('../../../services/api');

function hooksResponse(overrides = {}) {
  return {
    available: [
      { filename: 'a.so', size: 1024, modified: 1, enabled: true, order: 1, description: 'Speed hook' },
      { filename: 'b.so', size: 2048, modified: 1, enabled: true, order: 2, description: '' },
      { filename: 'c.so', size: 3072, modified: 1, enabled: false, order: null, description: '' },
    ],
    system_hooks_active: [],
    ...overrides,
  };
}

describe('HooksTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchInstanceHooks.mockResolvedValue(hooksResponse());
    api.saveInstanceHooks.mockResolvedValue({ task_id: 't1' });
    api.uploadInstanceHook.mockResolvedValue({});
    api.deleteInstanceHook.mockResolvedValue({});
    api.renameInstanceHook.mockResolvedValue({});
    api.setInstanceHookDescription.mockResolvedValue({});
    api.downloadInstanceHook.mockResolvedValue(new Blob());
  });

  it('renders user hooks with enabled state and order', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => expect(screen.getByTestId('hook-row-a.so')).toBeInTheDocument());
    expect(screen.getByRole('checkbox', { name: /enable a.so/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /enable c.so/i })).not.toBeChecked();
  });

  it('hides system hooks section when system_hooks_active is empty', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(screen.queryByText(/system hooks/i)).not.toBeInTheDocument();
  });

  it('shows system hooks section when non-empty', async () => {
    api.fetchInstanceHooks.mockResolvedValueOnce(hooksResponse({
      system_hooks_active: [{ filename: 'force_rate.so', size: 15880 }],
    }));

    render(<HooksTab instanceId={1} />);

    await waitFor(() => expect(screen.getByText(/system hooks/i)).toBeInTheDocument());
    expect(screen.getByText('force_rate.so')).toBeInTheDocument();
  });

  it('toggling a checkbox marks the form dirty and enables Apply', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    const apply = screen.getByRole('button', { name: /apply.*restart/i });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /enable c.so/i }));
    expect(apply).toBeEnabled();
  });

  it('Apply sends the enabled list in display order', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    fireEvent.click(screen.getByRole('checkbox', { name: /enable c.so/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply.*restart/i }));

    await waitFor(() => expect(api.saveInstanceHooks).toHaveBeenCalled());
    expect(api.saveInstanceHooks).toHaveBeenCalledWith(1, ['a.so', 'b.so', 'c.so'], undefined);
  });

  it('renders hook descriptions from GET data', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(screen.getByText('Speed hook')).toBeInTheDocument();
  });

  it('calls onApplied after a successful save', async () => {
    const onApplied = vi.fn();
    render(<HooksTab instanceId={1} onApplied={onApplied} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    fireEvent.click(screen.getByRole('checkbox', { name: /enable c.so/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply.*restart/i }));

    await waitFor(() => expect(onApplied).toHaveBeenCalled());
  });

  it('shows Upload .so button for live instance', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(screen.getByRole('button', { name: /upload .so/i })).toBeInTheDocument();
  });

  it('hides Upload .so button when draftId is set', async () => {
    render(<HooksTab instanceId={1} draftId="draft-abc" />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(screen.queryByRole('button', { name: /upload .so/i })).not.toBeInTheDocument();
  });

  it('upload calls uploadInstanceHook and reloads the list', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(api.fetchInstanceHooks).toHaveBeenCalledTimes(1);

    const file = new File(['ELF content'], 'new.so', { type: 'application/octet-stream' });
    const input = document.querySelector('input[type="file"][accept=".so"]');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(api.uploadInstanceHook).toHaveBeenCalledWith(1, file));
    await waitFor(() => expect(api.fetchInstanceHooks).toHaveBeenCalledTimes(2));
  });

  it('shows error banner when upload fails', async () => {
    api.uploadInstanceHook.mockRejectedValueOnce({ error: { message: 'Not an ELF file' } });
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    const file = new File(['bad'], 'bad.so', { type: 'application/octet-stream' });
    const input = document.querySelector('input[type="file"][accept=".so"]');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(screen.getByText('Not an ELF file')).toBeInTheDocument());
  });

  it('delete via actions menu shows confirmation modal', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    fireEvent.click(screen.getByRole('button', { name: /actions for a.so/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /delete/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/delete hook\?/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/will be permanently deleted/i)).toBeInTheDocument();
  });

  it('confirming delete calls deleteInstanceHook and reloads', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(api.fetchInstanceHooks).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /actions for a.so/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /delete/i }));

    await waitFor(() => screen.getByText(/delete hook\?/i));
    const deleteBtn = screen.getAllByRole('button', { name: /delete/i }).find(
      (b) => b.textContent.trim() === 'Delete' && !b.disabled,
    );
    fireEvent.click(deleteBtn);

    await waitFor(() => expect(api.deleteInstanceHook).toHaveBeenCalledWith(1, 'a.so'));
    await waitFor(() => expect(api.fetchInstanceHooks).toHaveBeenCalledTimes(2));
  });

  it('cancelling delete dismisses the modal', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    fireEvent.click(screen.getByRole('button', { name: /actions for a.so/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /delete/i }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /cancel/i }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.deleteInstanceHook).not.toHaveBeenCalled();
  });
});
