import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BulkActionsModal from '../BulkActionsModal';

const mocks = vi.hoisted(() => ({
  checkPluginUpdates: vi.fn(),
  applyPluginUpdates: vi.fn(),
  getDeferRestartsSetting: vi.fn(),
  // The Apply preset tab stays mounted (hidden) next to this one.
  getPresets: vi.fn(),
  getPresetKeepCvars: vi.fn(),
  previewPresetApply: vi.fn(),
  applyPresetToInstance: vi.fn(),
}));

vi.mock('../../../services/api', () => mocks);

const hosts = [
  { id: 1, name: 'alpha', status: 'ACTIVE' },
  { id: 2, name: 'bravo', status: 'ACTIVE' },
  { id: 3, name: 'charlie', status: 'PROVISIONING' },
];

const hostCheck = (instId, file) => ({
  data: {
    common_pool_changes: [],
    common_pool_error: null,
    instances: [
      { id: instId, name: `inst${instId}`, port: 27960, status: 'running', selected_plugin_changes: [{ name: file, change: 'modified' }] },
    ],
  },
});

const clickCheck = () => fireEvent.click(screen.getByRole('button', { name: /check for updates/i }));

const renderModal = () => {
  const result = render(<BulkActionsModal isOpen onClose={() => {}} hosts={hosts} />);
  clickCheck();
  return result;
};

describe('BulkPluginUpdatesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: false });
    mocks.applyPluginUpdates.mockResolvedValue({ message: 'queued' });
    mocks.getPresets.mockResolvedValue([]);
  });

  it('switching to Apply preset and back keeps the checks, the ticks and the results', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1 ? hostCheck(11, 'x.py') : hostCheck(22, 'y.py')));
    renderModal();
    await screen.findByText('y.py');
    fireEvent.click(screen.getByLabelText(/^x\.py/));
    fireEvent.click(screen.getByRole('button', { name: /update selected/i }));
    await waitFor(() => expect(screen.getByTestId('apply-result-host-2').textContent).toBe('queued'));

    fireEvent.click(screen.getByRole('tab', { name: /apply preset/i }));
    expect(screen.queryByRole('button', { name: /update selected/i })).toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: /update plugins/i }));

    expect(mocks.checkPluginUpdates).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('apply-result-host-2').textContent).toBe('queued');
    // The sent host stays unticked, and so does the file unticked by hand.
    expect(screen.getByLabelText(/y\.py/).checked).toBe(false);
    expect(screen.getByLabelText(/^x\.py/).checked).toBe(false);
  });

  it('lists hosts with their outdated files and no presets', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1 ? hostCheck(11, 'x.py') : hostCheck(22, 'y.py')));
    renderModal();

    expect(await screen.findByText('x.py')).toBeTruthy();
    expect(screen.getByText('y.py')).toBeTruthy();
    expect(screen.getByText('alpha')).toBeTruthy();
    // Presets are updated on the Presets page.
    expect(screen.queryByText(/preset \(/)).toBeNull();
    // Not ACTIVE: listed with the reason, never checked.
    expect(screen.getByText(/PROVISIONING/)).toBeTruthy();
    expect(mocks.checkPluginUpdates).toHaveBeenCalledTimes(2);
    expect(mocks.checkPluginUpdates).not.toHaveBeenCalledWith(3);
  });

  it('a host whose check fails shows the reason and the rest stay selectable', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => {
      if (id === 1) throw { error: { message: 'SSH unreachable' } };
      return hostCheck(22, 'y.py');
    });
    renderModal();

    expect(await screen.findByText('SSH unreachable')).toBeTruthy();
    expect(await screen.findByText('y.py')).toBeTruthy();
    const box = screen.getByLabelText(/y\.py/);
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    expect(box.checked).toBe(false);
  });

  it('apply sends one request per host with only the ticked files', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1 ? hostCheck(11, 'x.py') : hostCheck(22, 'y.py')));
    renderModal();
    await screen.findByText('y.py');

    fireEvent.click(screen.getByRole('button', { name: /update selected/i }));

    await waitFor(() => expect(mocks.applyPluginUpdates).toHaveBeenCalledTimes(2));
    expect(mocks.applyPluginUpdates).toHaveBeenCalledWith(1, {
      update_common_pool: false,
      instances: { 11: ['x.py'] },
      restart_instances: [11],
    });
    expect(mocks.applyPluginUpdates).toHaveBeenCalledWith(2, {
      update_common_pool: false,
      instances: { 22: ['y.py'] },
      restart_instances: [22],
    });
  });

  it('a 409 on one host is shown on its row and the others report queued', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1 ? hostCheck(11, 'x.py') : hostCheck(22, 'y.py')));
    mocks.applyPluginUpdates.mockImplementation(async (id) => {
      if (id === 1) throw { error: { message: 'Host is busy with another task' } };
      return { message: 'queued' };
    });
    renderModal();
    await screen.findByText('y.py');

    fireEvent.click(screen.getByRole('button', { name: /update selected/i }));

    expect(await screen.findByText('Host is busy with another task')).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText('queued').length).toBeGreaterThanOrEqual(1));
    expect(screen.getByTestId('apply-result-host-2').textContent).toBe('queued');
  });

  it('re-rendering with a new hosts array keeps the ticks and does not re-check', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1 ? hostCheck(11, 'x.py') : hostCheck(22, 'y.py')));
    const { rerender } = renderModal();
    await screen.findByText('y.py');
    fireEvent.click(screen.getByLabelText(/y\.py/));

    rerender(<BulkActionsModal isOpen onClose={() => {}} hosts={hosts.map((h) => ({ ...h }))} />);

    expect(screen.getByLabelText(/y\.py/).checked).toBe(false);
    expect(mocks.checkPluginUpdates).toHaveBeenCalledTimes(2);
  });

  it('an instance checkbox ticks and unticks all of its files and is indeterminate when partial', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1
      ? { data: { common_pool_changes: [], instances: [{ id: 11, name: 'inst11', port: 1, status: 'running', selected_plugin_changes: [{ name: 'f1.py', change: 'modified' }, { name: 'f2.py', change: 'modified' }] }] } }
      : hostCheck(22, 'y.py')));
    renderModal();
    await screen.findByText('f1.py');
    const inst = screen.getByLabelText('Select all for instance inst11');
    const f1 = screen.getByLabelText(/^f1\.py/);
    const f2 = screen.getByLabelText(/^f2\.py/);
    expect(inst.checked).toBe(true);

    fireEvent.click(f1);
    expect(inst.checked).toBe(false);
    expect(inst.indeterminate).toBe(true);

    fireEvent.click(inst);
    expect(f1.checked && f2.checked).toBe(true);
    fireEvent.click(inst);
    expect(f1.checked || f2.checked).toBe(false);
  });

  it('a second click does not re-send a host that already succeeded', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1 ? hostCheck(11, 'x.py') : hostCheck(22, 'y.py')));
    mocks.applyPluginUpdates.mockImplementation(async (id) => {
      if (id === 2) throw { error: { message: 'busy' } };
      return { message: 'queued' };
    });
    renderModal();
    await screen.findByText('y.py');
    const button = screen.getByRole('button', { name: /update selected/i });

    fireEvent.click(button);
    await screen.findByText('busy');
    await waitFor(() => expect(button.disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(mocks.applyPluginUpdates).toHaveBeenCalledTimes(3));

    expect(mocks.applyPluginUpdates.mock.calls.filter(([id]) => id === 1)).toHaveLength(1);
  });

  it('opening the dialog checks nothing until Check for updates, and a reopen starts clean', async () => {
    mocks.checkPluginUpdates.mockImplementation(async (id) => (id === 1 ? hostCheck(11, 'x.py') : hostCheck(22, 'y.py')));
    const { rerender } = render(<BulkActionsModal isOpen onClose={() => {}} hosts={hosts} />);
    await new Promise((r) => { setTimeout(r, 20); });
    expect(mocks.checkPluginUpdates).not.toHaveBeenCalled();

    clickCheck();
    await screen.findByText('y.py');
    expect(screen.getByRole('button', { name: /check again/i })).toBeTruthy();

    rerender(<BulkActionsModal isOpen={false} onClose={() => {}} hosts={hosts} />);
    rerender(<BulkActionsModal isOpen onClose={() => {}} hosts={hosts} />);
    expect(await screen.findByRole('button', { name: /check for updates/i })).toBeTruthy();
    expect(screen.queryByText('y.py')).toBeNull();
    expect(mocks.checkPluginUpdates).toHaveBeenCalledTimes(2);
  });

  it('checks at most four hosts at once and stops checking when the dialog closes', async () => {
    const many = [1, 2, 3, 4, 5, 6].map((id) => ({ id, name: `h${id}`, status: 'ACTIVE' }));
    const pending = [];
    mocks.checkPluginUpdates.mockImplementation(() => new Promise((resolve) => { pending.push(resolve); }));
    const { rerender } = render(<BulkActionsModal isOpen onClose={() => {}} hosts={many} />);
    clickCheck();
    await waitFor(() => expect(mocks.checkPluginUpdates).toHaveBeenCalledTimes(4));

    rerender(<BulkActionsModal isOpen={false} onClose={() => {}} hosts={many} />);
    pending.forEach((resolve) => resolve(hostCheck(11, 'x.py')));
    await new Promise((r) => { setTimeout(r, 20); });
    expect(mocks.checkPluginUpdates).toHaveBeenCalledTimes(4);
  });

  it('defaults restart from Defer restarts and never ticks a stopped instance', async () => {
    const check = {
      data: {
        common_pool_changes: [],
        instances: [
          { id: 11, name: 'run', port: 1, status: 'running', selected_plugin_changes: [{ name: 'r.py', change: 'modified' }] },
          { id: 12, name: 'stop', port: 2, status: 'stopped', selected_plugin_changes: [{ name: 's.py', change: 'modified' }] },
        ],
      },
    };
    mocks.checkPluginUpdates.mockResolvedValue(check);

    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: false });
    const first = renderModal();
    await screen.findAllByText('r.py');
    let boxes = screen.getAllByLabelText(/restart to apply/);
    expect(boxes.map((b) => b.checked)).toEqual([true, false, true, false]);
    expect(boxes.filter((_, i) => i % 2 === 1).every((b) => b.disabled)).toBe(true);
    first.unmount();

    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: true });
    renderModal();
    await screen.findAllByText('r.py');
    boxes = screen.getAllByLabelText(/restart to apply/);
    expect(boxes.every((b) => !b.checked)).toBe(true);
  });
});
