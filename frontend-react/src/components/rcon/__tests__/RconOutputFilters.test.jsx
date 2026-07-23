import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import RconOutputFilters, { deriveRconOutputTargets } from '../RconOutputFilters';

const selected = [
  { key: '1:11', name: 'Live Alpha', host_id: 1, instance_id: 11, state: 'ready' },
  { key: '2:22', display_name: 'Connecting Bravo', host_id: 2, instance_id: 22, state: 'connecting' },
];

describe('RconOutputFilters target union', () => {
  it('derives a deterministic deduplicated list from the current selection only', () => {
    const duplicated = [...selected, { key: '1:11', name: 'Duplicate Alpha', host_id: 1, instance_id: 11 }];
    expect(deriveRconOutputTargets({ selectedTargets: duplicated })).toEqual([
      expect.objectContaining({ key: '1:11', name: 'Live Alpha' }),
      expect.objectContaining({ key: '2:22', name: 'Connecting Bravo' }),
    ]);
  });

  it('falls back to the key as the name and leaves the input untouched', () => {
    const selectedSnapshot = structuredClone(selected);
    const result = deriveRconOutputTargets({ selectedTargets: selected });
    expect(result.map((target) => target.name)).toEqual(['Live Alpha', 'Connecting Bravo']);
    expect(selected).toEqual(selectedSnapshot);
  });

  it('drops a tab the moment its target is unchecked, regardless of retained run or stream history', () => {
    const { rerender } = render(<RconOutputFilters
      activeFilter="1:11" onFilterChange={() => {}} selectedTargets={selected}
    />);
    expect(screen.getByRole('tab', { name: 'Live Alpha' })).toBeInTheDocument();
    rerender(<RconOutputFilters
      activeFilter="1:11" onFilterChange={() => {}} selectedTargets={selected.slice(1)}
    />);
    expect(screen.queryByRole('tab', { name: 'Live Alpha' })).not.toBeInTheDocument();
  });
});

describe('RconOutputFilters full tab list', () => {
  it('renders only currently selected targets, with no overflow control', async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(<RconOutputFilters
      activeFilter="all" onFilterChange={onFilterChange} selectedTargets={selected}
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
    // ALL + Live Alpha, Connecting Bravo — nothing else, since neither target
    // came from run history or raw streams here.
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.queryByRole('button', { name: /more targets/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('marks the active filter as selected only when its target is still checked', () => {
    render(<RconOutputFilters
      activeFilter="1:11" onFilterChange={() => {}} selectedTargets={selected}
    />);
    expect(screen.getByRole('tab', { name: 'Live Alpha' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('button', { name: /more targets/ })).not.toBeInTheDocument();
  });
});
