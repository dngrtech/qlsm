import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const viewer = vi.hoisted(() => ({ events: [], appendCalls: 0, clearCalls: 0, mounts: 0 }));
vi.mock('../RconRawOutputViewer', async () => {
  const React = await import('react');
  return {
    default: React.forwardRef(function Viewer(_props, ref) {
      React.useEffect(() => {
        viewer.mounts += 1;
      }, []);
      React.useImperativeHandle(ref, () => ({
        clear: () => { viewer.clearCalls += 1; viewer.events = []; },
        append: (event) => { viewer.appendCalls += 1; viewer.events.push(event); },
      }), []);
      return <div data-testid="raw-viewer" />;
    }),
  };
});

import GlobalRconOutput from '../GlobalRconOutput';

beforeEach(() => {
  viewer.events = [];
  viewer.appendCalls = 0;
  viewer.clearCalls = 0;
  viewer.mounts = 0;
});

const older = {
  id: 'r1', command: 'older', timestamp: 'before',
  results: [{ key: '1:11', name: 'Retained Alpha', state: 'quiet', lines: [{ type: 'response', content: 'ok', timestamp: 'then' }] }],
};
const newer = {
  id: 'r2', command: 'newer', timestamp: 'now',
  results: [{ key: '2:22', name: 'Historical Bravo', state: 'failed', lines: [] }],
};
const selected = [{ key: '1:11', name: 'Live Alpha', host_id: 1, instance_id: 11 }];
const streams = new Map([
  ['1:11', [{ type: 'command', content: 'status', attempted: true, timestamp: 'now' }, { type: 'response', content: 'ok', timestamp: 'then' }]],
  ['3:33', [{ type: 'error', content: 'offline', timestamp: 'later' }]],
]);

describe('GlobalRconOutput exact public interface', () => {
  it('renders union filters and all retained runs in supplied newest-first order', () => {
    const onFilterChange = vi.fn();
    render(<GlobalRconOutput
      activeFilter="all" onFilterChange={onFilterChange} selectedTargets={selected}
      runs={[newer, older]} rawStreams={streams}
    />);
    expect(screen.getByRole('tab', { name: 'ALL' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Live Alpha' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Historical Bravo' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '3:33' })).toBeInTheDocument();
    const commands = screen.getAllByRole('heading', { level: 3 });
    expect(commands.map((node) => node.textContent)).toEqual(['> newer', '> older']);
  });

  it('passes target activation from each run through the exact onFilterChange callback', () => {
    const onFilterChange = vi.fn();
    render(<GlobalRconOutput
      activeFilter="all" onFilterChange={onFilterChange} selectedTargets={selected}
      runs={[older]} rawStreams={streams}
    />);
    fireEvent.click(screen.getByRole('button', { name: 'Show raw output for Retained Alpha' }));
    expect(onFilterChange).toHaveBeenCalledWith('1:11');
  });

  it('replays exactly the active target stream without duplication or drops when switching filters', async () => {
    const props = { onFilterChange: () => {}, selectedTargets: selected, runs: [newer, older], rawStreams: streams };
    const { rerender } = render(<GlobalRconOutput activeFilter="1:11" {...props} />);
    await waitFor(() => expect(viewer.events).toEqual(streams.get('1:11')));
    rerender(<GlobalRconOutput activeFilter="3:33" {...props} />);
    await waitFor(() => expect(viewer.events).toEqual(streams.get('3:33')));
    rerender(<GlobalRconOutput activeFilter="1:11" {...props} />);
    await waitFor(() => expect(viewer.events).toEqual(streams.get('1:11')));
  });

  it('appends only each newly arriving target event and resets once when switching target', async () => {
    const first = { type: 'response', content: 'first', timestamp: '1' };
    const second = { type: 'response', content: 'second', timestamp: '2' };
    const third = { type: 'response', content: 'third', timestamp: '3' };
    const other = { type: 'error', content: 'other', timestamp: '4' };
    const base = { onFilterChange: () => {}, selectedTargets: selected, runs: [] };
    const { rerender } = render(<GlobalRconOutput
      activeFilter="1:11" rawStreams={new Map([['1:11', [first]]])} {...base}
    />);
    rerender(<GlobalRconOutput
      activeFilter="1:11" rawStreams={new Map([['1:11', [first, second]]])} {...base}
    />);
    rerender(<GlobalRconOutput
      activeFilter="1:11" rawStreams={new Map([['1:11', [first, second, third]]])} {...base}
    />);

    await waitFor(() => expect(viewer.events).toEqual([first, second, third]));
    expect(viewer.appendCalls).toBe(3);
    expect(viewer.clearCalls).toBe(1);

    rerender(<GlobalRconOutput
      activeFilter="9:99" rawStreams={new Map([['1:11', [first, second, third]], ['9:99', [other]]])} {...base}
    />);
    await waitFor(() => expect(viewer.events).toEqual([other]));
    expect(viewer.appendCalls).toBe(4);
    expect(viewer.clearCalls).toBe(2);
  });

  it('clears and exactly replays a physically trimmed stream', async () => {
    const first = { type: 'response', content: 'old-a\nold-b', timestamp: '1' };
    const second = { type: 'response', content: 'stable', timestamp: '2' };
    const trimmed = { ...first, content: 'old-b' };
    const base = { activeFilter: '1:11', onFilterChange: () => {}, selectedTargets: selected, runs: [] };
    const { rerender } = render(<GlobalRconOutput
      rawStreams={new Map([['1:11', [first, second]]])} {...base}
    />);
    rerender(<GlobalRconOutput
      rawStreams={new Map([['1:11', [trimmed, second]]])} {...base}
    />);

    await waitFor(() => expect(viewer.events).toEqual([trimmed, second]));
    expect(viewer.clearCalls).toBe(2);
    expect(viewer.appendCalls).toBe(4);
  });

  it('does not duplicate final target content under StrictMode effect replay', async () => {
    const events = streams.get('1:11');
    render(<StrictMode><GlobalRconOutput
      activeFilter="1:11" onFilterChange={() => {}} selectedTargets={selected}
      runs={[]} rawStreams={new Map([['1:11', events]])}
    /></StrictMode>);
    await waitFor(() => expect(viewer.events).toEqual(events));
  });

  it('does not mount raw viewers for 50 runs with 15 compact results until search is requested', async () => {
    const compactRuns = Array.from({ length: 50 }, (_, runIndex) => ({
      id: `run-${runIndex}`,
      command: `status-${runIndex}`,
      timestamp: `${runIndex}`,
      results: Array.from({ length: 15 }, (_, resultIndex) => ({
        key: `${runIndex + 1}:${resultIndex + 1}`,
        name: `Target ${runIndex}-${resultIndex}`,
        state: 'quiet',
        lines: [{ type: 'response', content: '^2ok', timestamp: 'now' }],
      })),
    }));
    render(<GlobalRconOutput
      activeFilter="all" onFilterChange={() => {}} runs={compactRuns} rawStreams={new Map()}
    />);

    expect(viewer.mounts).toBe(0);
    const search = document.querySelector('button[aria-label="Search output for Target 0-0"]');
    expect(search).not.toBeNull();
    fireEvent.click(search);
    await waitFor(() => expect(viewer.mounts).toBe(1));
  });

  it('shows honest all-view and target-view empty states while retaining filters', () => {
    const base = { onFilterChange: () => {}, selectedTargets: selected, runs: [], rawStreams: new Map() };
    const { rerender } = render(<GlobalRconOutput activeFilter="all" {...base} />);
    expect(screen.getByText('No commands have been sent.')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Live Alpha' })).toBeInTheDocument();
    rerender(<GlobalRconOutput activeFilter="1:11" {...base} />);
    expect(screen.getByText('No output for this target.')).toBeInTheDocument();
  });
});
