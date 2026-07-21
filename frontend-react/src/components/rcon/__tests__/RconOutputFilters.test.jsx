import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import RconOutputFilters, { deriveRconOutputTargets } from '../RconOutputFilters';

const selected = [
  { key: '1:11', name: 'Live Alpha', host_id: 1, instance_id: 11, state: 'ready' },
  { key: '2:22', display_name: 'Connecting Bravo', host_id: 2, instance_id: 22, state: 'connecting' },
];
const runs = [{
  id: 'new',
  results: [
    { key: '1:11', name: 'Old Alpha' },
    { key: '3:33', name: 'Deselected Charlie', state: 'failed' },
    { key: '4:44', host_id: 4, instance_id: 44 },
  ],
}, {
  id: 'old',
  results: [{ key: '3:33', name: 'Older Charlie' }],
}];
const streams = new Map([
  ['3:33', [{ content: 'history' }]],
  ['5:55', [{ content: 'deleted target output' }]],
]);

describe('RconOutputFilters target union', () => {
  it('derives a deterministic deduplicated union from selection, retained runs, and raw streams', () => {
    expect(deriveRconOutputTargets({ selectedTargets: selected, runs, rawStreams: streams })).toEqual([
      expect.objectContaining({ key: '1:11', name: 'Live Alpha' }),
      expect.objectContaining({ key: '2:22', name: 'Connecting Bravo' }),
      expect.objectContaining({ key: '3:33', name: 'Deselected Charlie' }),
      expect.objectContaining({ key: '4:44', name: '4:44' }),
      expect.objectContaining({ key: '5:55', name: '5:55' }),
    ]);
  });

  it('uses live descriptor names before newest retained run names and exact-key fallback without mutation', () => {
    const selectedSnapshot = structuredClone(selected);
    const runSnapshot = structuredClone(runs);
    const result = deriveRconOutputTargets({ selectedTargets: selected, runs, rawStreams: streams });
    expect(result.map((target) => target.name)).toEqual([
      'Live Alpha', 'Connecting Bravo', 'Deselected Charlie', '4:44', '5:55',
    ]);
    expect(selected).toEqual(selectedSnapshot);
    expect(runs).toEqual(runSnapshot);
  });

  it('removes a filter only after selection, retained run history, and raw stream are all absent', () => {
    const { rerender } = render(<RconOutputFilters
      activeFilter="3:33" onFilterChange={() => {}} selectedTargets={[]} runs={runs} rawStreams={streams}
    />);
    expect(screen.getByRole('tab', { name: 'Deselected Charlie' })).toBeInTheDocument();
    rerender(<RconOutputFilters
      activeFilter="all" onFilterChange={() => {}} selectedTargets={[]} runs={[]} rawStreams={streams}
    />);
    expect(screen.getByRole('tab', { name: '3:33' })).toBeInTheDocument();
    rerender(<RconOutputFilters
      activeFilter="all" onFilterChange={() => {}} selectedTargets={[]} runs={[]} rawStreams={new Map()}
    />);
    expect(screen.queryByRole('tab', { name: '3:33' })).not.toBeInTheDocument();
  });
});

describe('RconOutputFilters bounded controls', () => {
  it('keeps ALL and bounded direct tabs keyboard-focusable and natively activatable', async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(<RconOutputFilters
      activeFilter="all" onFilterChange={onFilterChange} selectedTargets={selected}
      runs={runs} rawStreams={streams} directLimit={3}
    />);
    const all = screen.getByRole('tab', { name: 'ALL' });
    const alpha = screen.getByRole('tab', { name: 'Live Alpha' });
    expect(all).toHaveAttribute('aria-selected', 'true');
    await user.tab();
    expect(all).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onFilterChange).toHaveBeenLastCalledWith('all');
    await user.tab();
    expect(alpha).toHaveFocus();
    await user.keyboard(' ');
    expect(onFilterChange).toHaveBeenLastCalledWith('1:11');
    expect(screen.getAllByRole('tab')).toHaveLength(4);
    expect(screen.getByRole('button', { name: '+ 2 more targets' })).toBeInTheDocument();
  });

  it('keeps an active overflow target directly visible and reachable', () => {
    render(<RconOutputFilters
      activeFilter="5:55" onFilterChange={() => {}} selectedTargets={selected}
      runs={runs} rawStreams={streams} directLimit={3}
    />);
    expect(screen.getByRole('tab', { name: '5:55' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('button', { name: '+ 2 more targets' })).toBeInTheDocument();
  });

  it('searches overflow case-insensitively by name or key, reports no results, and activates then closes', async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(<RconOutputFilters
      activeFilter="all" onFilterChange={onFilterChange} selectedTargets={selected}
      runs={runs} rawStreams={streams} directLimit={2}
    />);
    await user.click(screen.getByRole('button', { name: '+ 3 more targets' }));
    const dialog = screen.getByRole('dialog', { name: 'More RCON output targets' });
    const search = within(dialog).getByRole('searchbox', { name: 'Search targets' });
    await user.type(search, 'CHARLIE');
    expect(within(dialog).getByRole('button', { name: 'Deselected Charlie' })).toBeInTheDocument();
    await user.clear(search);
    await user.type(search, '5:55');
    await user.click(within(dialog).getByRole('button', { name: '5:55' }));
    expect(onFilterChange).toHaveBeenCalledWith('5:55');
    expect(screen.queryByRole('dialog', { name: 'More RCON output targets' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '+ 3 more targets' }));
    await user.type(screen.getByRole('searchbox', { name: 'Search targets' }), 'missing');
    expect(screen.getByText('No matching targets.')).toBeInTheDocument();
  });
});
