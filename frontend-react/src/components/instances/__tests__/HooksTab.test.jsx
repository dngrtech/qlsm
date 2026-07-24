import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HooksTab from '../HooksTab';
import * as api from '../../../services/api';

vi.mock('../../../services/api');

const baseAvailable = [
  { filename: 'a.so', size: 1024, modified: 1, enabled: true, order: 1, description: 'Speed hook' },
  { filename: 'b.so', size: 2048, modified: 1, enabled: true, order: 2, description: '' },
  { filename: 'c.so', size: 3072, modified: 1, enabled: false, order: null, description: '' },
];

function renderTab(overrides = {}) {
  const props = {
    instanceId: 1,
    available: baseAvailable,
    missing: [],
    systemHooks: [],
    enabledOrder: ['a.so', 'b.so'],
    dirty: false,
    onToggleHook: vi.fn(),
    onReorderHooks: vi.fn(),
    onRemoveMissing: vi.fn(),
    onRefresh: vi.fn(),
    ...overrides,
  };
  const view = render(<HooksTab {...props} />);
  return { ...view, props };
}

describe('HooksTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.uploadInstanceHook.mockResolvedValue({});
    api.replaceInstanceHook.mockResolvedValue({});
    api.deleteInstanceHook.mockResolvedValue({});
    api.renameInstanceHook.mockResolvedValue({});
    api.setInstanceHookDescription.mockResolvedValue({});
    api.downloadInstanceHook.mockResolvedValue(new Blob());
  });

  it('renders user hooks with enabled state and order', () => {
    renderTab();

    expect(screen.getByTestId('hook-row-a.so')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /enable a.so/i })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /enable c.so/i })).toHaveAttribute('aria-pressed', 'false');
  });

  it('hides system hooks section when systemHooks is empty', () => {
    renderTab();

    expect(screen.queryByText(/system hooks/i)).not.toBeInTheDocument();
  });

  it('shows system hooks section when non-empty', () => {
    renderTab({ systemHooks: [{ filename: 'force_rate.so', size: 15880 }] });

    expect(screen.getByText(/system hooks/i)).toBeInTheDocument();
    expect(screen.getByText('force_rate')).toBeInTheDocument();
  });

  it('has no in-tab Apply/Cancel footer', () => {
    renderTab({ dirty: true });

    expect(screen.queryByRole('button', { name: /apply.*restart/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^cancel$/i })).not.toBeInTheDocument();
  });

  it('toggling c.so calls onToggleHook', async () => {
    const { props } = renderTab();

    fireEvent.click(screen.getByRole('button', { name: /enable c.so/i }));

    await waitFor(() => expect(props.onToggleHook).toHaveBeenCalledWith('c.so'));
  });

  it('renders hook descriptions from controlled data', () => {
    renderTab();

    expect(screen.getByText('Speed hook')).toBeInTheDocument();
  });

  it('shows Upload .so button for live instance', () => {
    renderTab();

    expect(screen.getByRole('button', { name: /upload .so/i })).toBeInTheDocument();
  });

  it('upload calls uploadInstanceHook and onRefresh after success', async () => {
    const { props } = renderTab();

    const file = new File(['ELF content'], 'new.so', { type: 'application/octet-stream' });
    fireEvent.change(screen.getByTestId('hook-upload-input'), { target: { files: [file] } });

    await waitFor(() => expect(api.uploadInstanceHook).toHaveBeenCalledWith(1, file));
    expect(props.onRefresh).toHaveBeenCalledWith({ hooksChanged: false });
  });

  it('uploading over an enabled hook marks hook files changed for restart forcing', async () => {
    const { props } = renderTab();

    const file = new File(['ELF content'], 'a.so', { type: 'application/octet-stream' });
    fireEvent.change(screen.getByTestId('hook-upload-input'), { target: { files: [file] } });

    await waitFor(() => expect(api.uploadInstanceHook).toHaveBeenCalledWith(1, file));
    expect(props.onRefresh).toHaveBeenCalledWith({ hooksChanged: true });
  });

  it('replacing an ENABLED hook binary marks hook files changed for restart forcing', async () => {
    const { props } = renderTab();

    const row = screen.getByTestId('hook-row-a.so');
    const input = row.querySelector('input[type="file"]');
    const file = new File(['ELF content'], 'a.so', { type: 'application/octet-stream' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(api.replaceInstanceHook).toHaveBeenCalledWith(1, 'a.so', file));
    expect(props.onRefresh).toHaveBeenCalledWith({ hooksChanged: true });
  });

  it('replacing a DISABLED hook binary does not force a restart', async () => {
    const { props } = renderTab();

    const row = screen.getByTestId('hook-row-c.so');
    const input = row.querySelector('input[type="file"]');
    const file = new File(['ELF content'], 'c.so', { type: 'application/octet-stream' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(api.replaceInstanceHook).toHaveBeenCalledWith(1, 'c.so', file));
    expect(props.onRefresh).toHaveBeenCalledWith({ hooksChanged: false });
  });

  it('replacing via the "⋮" actions menu also forces a restart for an ENABLED hook', async () => {
    // Each row renders two file inputs: the inline replace icon's own input,
    // and a second one owned by HookActionsMenu. Target the second explicitly
    // so this test can't accidentally pass by hitting the inline one instead.
    const { props } = renderTab();

    const row = screen.getByTestId('hook-row-a.so');
    const inputs = row.querySelectorAll('input[type="file"]');
    expect(inputs).toHaveLength(2);
    const menuInput = inputs[1];
    const file = new File(['ELF content'], 'a.so', { type: 'application/octet-stream' });
    fireEvent.change(menuInput, { target: { files: [file] } });

    await waitFor(() => expect(api.replaceInstanceHook).toHaveBeenCalledWith(1, 'a.so', file));
    expect(props.onRefresh).toHaveBeenCalledWith({ hooksChanged: true });
  });

  it('replacing via the "⋮" actions menu does not force a restart for a DISABLED hook', async () => {
    const { props } = renderTab();

    const row = screen.getByTestId('hook-row-c.so');
    const inputs = row.querySelectorAll('input[type="file"]');
    expect(inputs).toHaveLength(2);
    const menuInput = inputs[1];
    const file = new File(['ELF content'], 'c.so', { type: 'application/octet-stream' });
    fireEvent.change(menuInput, { target: { files: [file] } });

    await waitFor(() => expect(api.replaceInstanceHook).toHaveBeenCalledWith(1, 'c.so', file));
    expect(props.onRefresh).toHaveBeenCalledWith({ hooksChanged: false });
  });

  it('shows error banner when upload fails', async () => {
    api.uploadInstanceHook.mockRejectedValueOnce({ error: { message: 'Not an ELF file' } });
    renderTab();

    const file = new File(['bad'], 'bad.so', { type: 'application/octet-stream' });
    fireEvent.change(screen.getByTestId('hook-upload-input'), { target: { files: [file] } });

    await waitFor(() => expect(screen.getByText('Not an ELF file')).toBeInTheDocument());
  });

  it('dirty hint appears when dirty', () => {
    renderTab({ dirty: true });

    expect(screen.getByText(/Unsaved hook changes/i)).toBeInTheDocument();
    expect(screen.getByText(/click Save Configuration to apply/i)).toBeInTheDocument();
  });

  it('delete via actions menu shows confirmation modal', async () => {
    renderTab();

    const row = screen.getByTestId('hook-row-a.so');
    fireEvent.click(within(row).getByRole('button', { name: /actions for a.so/i }));
    fireEvent.click(within(row).getByRole('menuitem', { name: /delete/i, hidden: true }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/delete hook\?/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/This cannot be undone/i)).toBeInTheDocument();
  });

  it('confirming delete calls deleteInstanceHook and onRefresh', async () => {
    const { props } = renderTab();

    const row = screen.getByTestId('hook-row-a.so');
    fireEvent.click(within(row).getByRole('button', { name: /actions for a.so/i }));
    fireEvent.click(within(row).getByRole('menuitem', { name: /delete/i, hidden: true }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /delete/i }));

    await waitFor(() => expect(api.deleteInstanceHook).toHaveBeenCalledWith(1, 'a.so'));
    expect(props.onRefresh).toHaveBeenCalledTimes(1);
  });

  it('cancelling delete dismisses the modal', async () => {
    renderTab();

    const row = screen.getByTestId('hook-row-a.so');
    fireEvent.click(within(row).getByRole('button', { name: /actions for a.so/i }));
    fireEvent.click(within(row).getByRole('menuitem', { name: /delete/i, hidden: true }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.deleteInstanceHook).not.toHaveBeenCalled();
  });
});
