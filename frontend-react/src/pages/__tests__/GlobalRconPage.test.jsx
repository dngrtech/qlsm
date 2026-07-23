import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  startRun: vi.fn(), applyDispatchAck: vi.fn(), appendMessage: vi.fn(), applyTargetStatus: vi.fn(),
  sendCommand: vi.fn().mockResolvedValue({ run_id: 'run-id', targets: [] }),
  prefArgs: null, fleetArgs: null, inventoryError: null, statuses: null,
}));
vi.mock('../../hooks/useServers', () => ({ useServers: () => ({
  serversData: [{ id: 1, name: 'Host', instances: [
    { id: 11, host_id: 1, name: 'Ready', status: 'running', zmq_rcon_port: 27960 },
    { id: 12, host_id: 1, name: 'Waiting', status: 'running', zmq_rcon_port: 27961 },
  ] }], loading: false, error: state.inventoryError,
}) }));
vi.mock('../../hooks/useHostOrder', () => ({ useHostOrder: () => ({ getOrderedHosts: (hosts) => hosts }) }));
vi.mock('../../hooks/useGlobalRconPreferences', () => ({ default: (args) => {
  state.prefArgs = args;
  return { selectedKeys: new Set(['1:11', '1:12']), expandedHostIds: new Set([1]), setTargetChecked: vi.fn(), setHostChecked: vi.fn(), selectAllEligible: vi.fn(), selectNone: vi.fn(), toggleHostExpanded: vi.fn() };
} }));
vi.mock('../../hooks/useFleetRconSession', () => ({ useFleetRconSession: (args) => {
  state.fleetArgs = args;
  return { connected: true, statuses: state.statuses ?? new Map([['1:11', { state: 'ready' }], ['1:12', { state: 'connecting' }]]), sendCommand: state.sendCommand };
} }));
vi.mock('../../hooks/useRconCommandRuns', () => ({ default: () => ({
  runs: [], rawStreams: new Map(), startRun: state.startRun, applyDispatchAck: state.applyDispatchAck,
  appendMessage: state.appendMessage, applyTargetStatus: state.applyTargetStatus,
}) }));
vi.mock('../../components/rcon/RconTargetTree', () => ({ default: () => <div data-testid="target-tree" /> }));
vi.mock('../../components/rcon/GlobalRconOutput', () => ({ default: ({ commandInput, onFilterChange }) => (
  <div data-testid="output">
    <button onClick={() => onFilterChange('1:11')}>activate-1:11</button>
    <button onClick={() => onFilterChange('1:12')}>activate-1:12</button>
    {commandInput}
  </div>
) }));
vi.mock('../../components/rcon/RconCommandInput', () => ({ default: ({ disabled, buttonLabel, onSend }) => <button disabled={disabled} onClick={() => onSend('status')}>{buttonLabel}</button> }));

import GlobalRconPage from '../GlobalRconPage';

beforeEach(() => {
  state.inventoryError = null; state.statuses = null;
  Object.values(state).forEach((value) => value?.mockClear?.());
});
describe('GlobalRconPage', () => {
  it('uses ready snapshot for run and fleet command without stats or confirmation', async () => {
    render(<GlobalRconPage />);
    expect(screen.getByRole('heading', { name: /global rcon/i })).toBeInTheDocument();
    expect(state.prefArgs.inventoryReady).toBe(true);
    expect(state.fleetArgs.targets).toEqual([{ host_id: 1, instance_id: 11 }, { host_id: 1, instance_id: 12 }]);
    const send = screen.getByRole('button', { name: 'Send to 1 target' });
    fireEvent.click(send);
    await vi.waitFor(() => expect(state.sendCommand).toHaveBeenCalled());
    expect(state.startRun).toHaveBeenCalledWith(expect.objectContaining({ command: 'status', readyTargets: [expect.objectContaining({ key: '1:11' })], skippedTargets: [expect.objectContaining({ key: '1:12' })] }));
    expect(state.sendCommand.mock.calls[0].slice(1)).toEqual(['status', [{ host_id: 1, instance_id: 11 }]]);
    expect(state.applyDispatchAck).toHaveBeenCalled();
    expect(screen.queryByText(/real-time game events/i)).not.toBeInTheDocument();
  });

  it('scopes Send to only the active target tab, ignoring the rest of the selection', async () => {
    render(<GlobalRconPage />);
    fireEvent.click(screen.getByRole('button', { name: 'activate-1:11' }));
    const send = screen.getByRole('button', { name: 'Send to Ready' });
    fireEvent.click(send);
    await vi.waitFor(() => expect(state.sendCommand).toHaveBeenCalled());
    expect(state.startRun).toHaveBeenCalledWith(expect.objectContaining({
      readyTargets: [expect.objectContaining({ key: '1:11' })], skippedTargets: [],
    }));
    expect(state.sendCommand.mock.calls[0].slice(1)).toEqual(['status', [{ host_id: 1, instance_id: 11 }]]);
  });

  it('disables Send when the active tab targets a selected instance that is not ready, even though another is', () => {
    render(<GlobalRconPage />);
    fireEvent.click(screen.getByRole('button', { name: 'activate-1:12' }));
    expect(screen.getByRole('button', { name: 'Send to Waiting' })).toBeDisabled();
  });

  it('routes fleet session events into the command run store', () => {
    render(<GlobalRconPage />);
    expect(state.fleetArgs.onMessage).toBe(state.appendMessage);
    expect(state.fleetArgs.onStatus).toBe(state.applyTargetStatus);
    expect(state.fleetArgs.enabled).toBe(true);
  });

  it('disables send without ready targets and renders inventory errors safely', () => {
    state.statuses = new Map([['1:11', { state: 'connecting' }], ['1:12', { state: 'failed', reason: 'offline' }]]);
    const { rerender } = render(<GlobalRconPage />);
    expect(screen.getByRole('button', { name: 'Send to 0 targets' })).toBeDisabled();
    // useServers reports failures as plain strings, not Error instances.
    state.inventoryError = 'Failed to fetch hosts';
    rerender(<GlobalRconPage />);
    expect(screen.getByText(/unable to load server inventory: failed to fetch hosts/i)).toBeInTheDocument();
    state.inventoryError = new Error('offline');
    rerender(<GlobalRconPage />);
    expect(screen.getByText(/unable to load server inventory: offline/i)).toBeInTheDocument();
  });

  it('keeps selection stable while the narrow target pane is toggled', () => {
    render(<GlobalRconPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Hide targets' }));
    expect(screen.getByRole('button', { name: 'Show targets' })).toHaveAttribute('aria-expanded', 'false');
    expect(state.fleetArgs.targets).toEqual([{ host_id: 1, instance_id: 11 }, { host_id: 1, instance_id: 12 }]);
  });
});
