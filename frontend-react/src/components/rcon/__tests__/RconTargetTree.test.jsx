import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import RconTargetTree from '../RconTargetTree';
import { buildRconHosts } from '../../../utils/rconTargets';

const model = buildRconHosts(
  [{ id: 1, name: 'Alpha host' }, { id: 2, name: 'Empty host' }],
  [
    { id: 11, host_id: 1, name: 'Ready server', status: 'running', zmq_rcon_port: 27960 },
    { id: 12, host_id: 1, name: 'Stopped server', status: 'stopped', zmq_rcon_port: 27961 },
    { id: 13, host_id: 1, name: 'No RCON server', status: 'running', zmq_rcon_port: null },
  ],
);

function renderTree(overrides = {}) {
  const props = {
    hosts: model,
    selectedKeys: new Set(),
    expandedHostIds: new Set([1]),
    setTargetChecked: vi.fn(),
    setHostChecked: vi.fn(),
    selectAllEligible: vi.fn(),
    selectNone: vi.fn(),
    toggleHostExpanded: vi.fn(),
    ...overrides,
  };
  return { ...render(<RconTargetTree {...props} />), props };
}

describe('RconTargetTree', () => {
  it('shows unavailable rows, stable reasons, and remembered disabled checks', () => {
    renderTree({ selectedKeys: new Set(['1:12']) });
    expect(screen.getByRole('checkbox', { name: 'Select Stopped server on Alpha host' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Select Stopped server on Alpha host' })).toBeChecked();
    expect(screen.getByText('stopped')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select No RCON server on Alpha host' })).toBeDisabled();
    expect(screen.getByText('RCON not configured')).toBeInTheDocument();
  });

  it('sets host tri-state indeterminate from eligible children only', () => {
    const { rerender, props } = renderTree({ selectedKeys: new Set(['1:11']) });
    const host = screen.getByRole('checkbox', { name: 'Select Alpha host' });
    expect(host.indeterminate).toBe(false);
    expect(host).toBeChecked();

    const twoEligible = model.map((item) => item.id === 1 ? {
      ...item,
      instances: [
        ...item.instances,
        { ...item.instances.find((instance) => instance.eligible), id: 14, key: '1:14', label: 'Other server' },
      ],
    } : item);
    rerender(<RconTargetTree {...props} hosts={twoEligible} selectedKeys={new Set(['1:11'])} />);
    expect(screen.getByRole('checkbox', { name: 'Select Alpha host' }).indeterminate).toBe(true);
  });

  it('wires Select All, Select None, target, and eligible-only host operations', () => {
    const { props } = renderTree({ selectedKeys: new Set(['1:12']) });
    fireEvent.click(screen.getByRole('button', { name: 'Select All' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select None' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Ready server on Alpha host' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Alpha host' }));
    expect(props.selectAllEligible).toHaveBeenCalledOnce();
    expect(props.selectNone).toHaveBeenCalledOnce();
    expect(props.setTargetChecked).toHaveBeenCalledWith('1:11', true);
    expect(props.setHostChecked).toHaveBeenCalledWith(new Set(['1:11']), true);
  });

  it('uses accessible expand/collapse names and persists through callback', () => {
    const { props, rerender } = renderTree();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse Alpha host' }));
    expect(props.toggleHostExpanded).toHaveBeenCalledWith(1);
    rerender(<RconTargetTree {...props} expandedHostIds={new Set()} />);
    expect(screen.getByRole('button', { name: 'Expand Alpha host' })).toBeInTheDocument();
    // Instances stay mounted (revealed via an animated max-height, not
    // conditional rendering) so collapse can transition instead of snapping.
    const checkbox = screen.getByRole('checkbox', { name: 'Select Ready server on Alpha host' });
    expect(checkbox).toBeInTheDocument();
    expect(checkbox.closest('div').className).toMatch(/max-h-0/);
  });

  it('renders connecting, ready, and failed runtime indicators without disabling eligible failures', () => {
    const runtimeStates = new Map([
      ['1:11', { state: 'failed', reason: 'Timed out' }],
      ['1:12', 'connecting'],
      ['1:13', { status: 'ready' }],
    ]);
    renderTree({ runtimeStates });
    expect(screen.getByRole('status', { name: 'Failed: Timed out' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Connecting' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Ready' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select Ready server on Alpha host' })).toBeEnabled();
  });

  it('shows a current/max player count from server status, and a dash when none is available yet', () => {
    renderTree({ serverStatuses: { 11: { players: [{}, {}, {}, {}], maxplayers: 16 } } });
    expect(screen.getByText('4/16')).toBeInTheDocument();
    // Stopped server (12) and No RCON server (13) have no status entry.
    expect(screen.getAllByText('—')).toHaveLength(2);
  });

  it('uses host context to distinguish identical instance checkbox labels', () => {
    const duplicateModel = buildRconHosts(
      [{ id: 1, name: 'Paris' }, { id: 2, name: 'London' }],
      [
        { id: 11, host_id: 1, name: 'Arena', status: 'running', zmq_rcon_port: 27960 },
        { id: 21, host_id: 2, name: 'Arena', status: 'running', zmq_rcon_port: 27961 },
      ],
    );
    renderTree({ hosts: duplicateModel, expandedHostIds: new Set([1, 2]) });
    expect(screen.getByRole('checkbox', { name: 'Select Arena on Paris' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select Arena on London' })).toBeInTheDocument();
  });
});
