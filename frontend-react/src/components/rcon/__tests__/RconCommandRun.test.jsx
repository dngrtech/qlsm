import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const viewer = vi.hoisted(() => ({ mounts: 0, appendCalls: 0, clearCalls: 0 }));
vi.mock('../RconRawOutputViewer', async () => {
  const React = await import('react');
  return {
    default: React.forwardRef(function Viewer({ showMetadata }, ref) {
      const [events, setEvents] = React.useState([]);
      React.useEffect(() => {
        viewer.mounts += 1;
      }, []);
      React.useImperativeHandle(ref, () => ({
        clear: () => { viewer.clearCalls += 1; setEvents([]); },
        append: (event) => {
          viewer.appendCalls += 1;
          setEvents((current) => [...current, event]);
        },
      }), []);
      return <div data-testid="run-viewer" data-show-metadata={String(showMetadata)}>
        {events.map((event) => event.content).join('\n')}
      </div>;
    }),
  };
});

import RconCommandRun from '../RconCommandRun';

function result(key, name, { state = 'quiet', content = 'one', lines, anomaly = false } = {}) {
  return {
    key, name, host_id: 1, instance_id: 11, state,
    reason: state === 'failed' ? 'connection lost' : undefined,
    ack_anomaly: anomaly,
    lines: lines ?? [{ type: 'response', content, timestamp: '12:00:01' }],
  };
}

function makeRun(results = [result('1:11', 'Alpha')]) {
  return { id: 'run-1', command: 'status', timestamp: '12:00:00', results };
}

beforeEach(() => {
  viewer.mounts = 0;
  viewer.appendCalls = 0;
  viewer.clearCalls = 0;
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe('RconCommandRun', () => {
  it.each([1, 5])('shows %i physical output lines in a lightweight color view with opt-in search', async (count) => {
    const content = Array.from({ length: count }, (_, i) => `^2line-${i}`).join('\n');
    const user = userEvent.setup();
    render(<RconCommandRun run={makeRun([result('1:11', 'Alpha', { content })])} />);
    const header = screen.getByRole('button', { name: `Alpha, ${count} ${count === 1 ? 'line' : 'lines'}` });
    expect(header).toHaveAttribute('aria-expanded', 'true');
    expect(screen.queryByTestId('run-viewer')).not.toBeInTheDocument();
    expect(screen.getByText(/line-0/)).toHaveStyle({ color: '#44ff44' });
    expect(screen.queryByText(/\^2/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Search output for Alpha' }));
    expect(screen.getByTestId('run-viewer')).toHaveAttribute('data-show-metadata', 'false');
    await waitFor(() => expect(screen.getByTestId('run-viewer')).toHaveTextContent('line-0'));
    await user.click(screen.getByRole('button', { name: 'Close output search for Alpha' }));
    expect(screen.queryByTestId('run-viewer')).not.toBeInTheDocument();
    expect(screen.getByText(/line-0/)).toBeInTheDocument();
  });

  it('collapses over-five-line output to one physical preview and toggles from its accessible header', async () => {
    const content = 'one\ntwo\nthree\nfour\nfive\nsix';
    render(<RconCommandRun run={makeRun([result('1:11', 'Alpha', { content })])} />);
    const header = screen.getByRole('button', { name: 'Alpha, 6 lines' });
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('one')).toBeInTheDocument();
    expect(screen.queryByText(/six/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('run-viewer')).not.toBeInTheDocument();
    fireEvent.click(header);
    expect(header).toHaveAttribute('aria-expanded', 'true');
    await waitFor(() => expect(screen.getByTestId('run-viewer')).toHaveTextContent('six'));
    fireEvent.click(header);
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('run-viewer')).not.toBeInTheDocument();
  });

  it('appends only the new suffix to an expanded result viewer', async () => {
    const events = Array.from({ length: 8 }, (_, index) => ({
      type: 'response', content: `line-${index}`, timestamp: `${index}`,
    }));
    const runWith = (lines) => makeRun([result('1:11', 'Alpha', { lines })]);
    const { rerender } = render(<RconCommandRun run={runWith(events.slice(0, 6))} />);
    fireEvent.click(screen.getByRole('button', { name: 'Alpha, 6 lines' }));
    await waitFor(() => expect(screen.getByTestId('run-viewer')).toHaveTextContent('line-5'));
    rerender(<RconCommandRun run={runWith(events.slice(0, 7))} />);
    rerender(<RconCommandRun run={runWith(events)} />);

    await waitFor(() => expect(screen.getByTestId('run-viewer')).toHaveTextContent('line-7'));
    expect(viewer.appendCalls).toBe(8);
    expect(viewer.clearCalls).toBe(1);
  });

  it('resets an expanded result viewer when physical trimming replaces its first event', async () => {
    const events = Array.from({ length: 6 }, (_, index) => ({
      type: 'response', content: `line-${index}`, timestamp: `${index}`,
    }));
    const trimmed = [{ ...events[0], content: 'trimmed-first' }, ...events.slice(1)];
    const runWith = (lines) => makeRun([result('1:11', 'Alpha', { lines })]);
    const { rerender } = render(<RconCommandRun run={runWith(events)} />);
    fireEvent.click(screen.getByRole('button', { name: 'Alpha, 6 lines' }));
    await waitFor(() => expect(screen.getByTestId('run-viewer')).toHaveTextContent('line-5'));
    rerender(<RconCommandRun run={runWith(trimmed)} />);

    await waitFor(() => expect(screen.getByTestId('run-viewer')).toHaveTextContent('trimmed-first'));
    expect(viewer.clearCalls).toBe(2);
    expect(viewer.appendCalls).toBe(12);
  });

  it('does not duplicate an auto-expanded result under StrictMode effect replay', async () => {
    const lines = Array.from({ length: 6 }, (_, index) => ({
      type: 'response', content: `line-${index}`, timestamp: `${index}`,
    }));
    render(<StrictMode><RconCommandRun
      run={makeRun([result('1:11', 'Alpha', { state: 'failed', lines })])}
    /></StrictMode>);

    await waitFor(() => expect(screen.getByTestId('run-viewer')).toHaveTextContent('line-5'));
    expect(screen.getByTestId('run-viewer').textContent).toBe(lines.map((line) => line.content).join('\n'));
    expect(viewer.appendCalls).toBe(12);
  });

  it('auto-expands failed and error output while keeping the acknowledgement anomaly visible', async () => {
    render(<RconCommandRun run={makeRun([
      result('1:11', 'Alpha', {
        state: 'failed', content: 'one\ntwo\nthree\nfour\nfive\nsix', anomaly: true,
      }),
      result('2:22', 'Bravo', {
        lines: [{ type: 'error', content: 'bad\nnews\nfrom\nthe\nserver\nnow', timestamp: 'then' }],
      }),
    ])} />);
    expect(screen.getByRole('button', { name: 'Alpha, 6 lines' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Bravo, 6 lines' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/Failed: connection lost/)).toBeInTheDocument();
    expect(screen.getByText(/Dispatch rejected after output was received/)).toBeInTheDocument();
  });

  it('lets collapse all and the individual header override terminal auto-expansion', () => {
    render(<RconCommandRun run={makeRun([
      result('1:11', 'Alpha', {
        state: 'failed', content: 'one\ntwo\nthree\nfour\nfive\nsix',
      }),
      result('2:22', 'Bravo', {
        lines: [{ type: 'error', content: 'bad\nnews\nfrom\nthe\nserver\nnow', timestamp: 'then' }],
      }),
    ])} />);
    const failedHeader = screen.getByRole('button', { name: 'Alpha, 6 lines' });
    const errorHeader = screen.getByRole('button', { name: 'Bravo, 6 lines' });
    expect(failedHeader).toHaveAttribute('aria-expanded', 'true');
    expect(errorHeader).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Collapse all target output' }));
    expect(failedHeader).toHaveAttribute('aria-expanded', 'false');
    expect(errorHeader).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(failedHeader);
    expect(failedHeader).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(failedHeader);
    expect(failedHeader).toHaveAttribute('aria-expanded', 'false');
  });

  it('auto-expands newly terminal output only when its key has no explicit override', () => {
    const long = 'one\ntwo\nthree\nfour\nfive\nsix';
    const initial = makeRun([result('1:11', 'Alpha', { content: long })]);
    const { rerender } = render(<RconCommandRun run={initial} />);
    fireEvent.click(screen.getByRole('button', { name: 'Expand all target output' }));
    fireEvent.click(screen.getByRole('button', { name: 'Collapse all target output' }));

    rerender(<RconCommandRun run={makeRun([
      result('1:11', 'Alpha', { state: 'failed', content: long }),
      result('2:22', 'Bravo', { state: 'failed', content: long }),
    ])} />);
    expect(screen.getByRole('button', { name: 'Alpha, 6 lines' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'Bravo, 6 lines' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('offers run-level expand/collapse controls for every expandable target block', async () => {
    render(<RconCommandRun run={makeRun([
      result('1:11', 'Alpha', { content: '1\n2\n3\n4\n5\n6' }),
      result('2:22', 'Bravo', { content: 'a\nb\nc\nd\ne\nf' }),
    ])} />);
    fireEvent.click(screen.getByRole('button', { name: 'Expand all target output' }));
    expect(screen.getByRole('button', { name: 'Alpha, 6 lines' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Bravo, 6 lines' })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Collapse all target output' }));
    expect(screen.getByRole('button', { name: 'Alpha, 6 lines' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'Bravo, 6 lines' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('copies exact multiline target content and safely absorbs clipboard rejection', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    const lines = [
      { type: 'response', content: 'one\ntwo', timestamp: 'a' },
      { type: 'error', content: 'three', timestamp: 'b' },
    ];
    render(<RconCommandRun run={makeRun([result('1:11', 'Alpha', { lines })])} />);
    await user.click(screen.getByRole('button', { name: 'Copy output for Alpha' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('one\ntwo\nthree');
    navigator.clipboard.writeText.mockRejectedValueOnce(new Error('denied'));
    await expect(user.click(screen.getByRole('button', { name: 'Copy output for Alpha' }))).resolves.toBeUndefined();
  });

  it('activates the target raw filter by clicking the visible target label', () => {
    const onFilterChange = vi.fn();
    render(<RconCommandRun run={makeRun()} onFilterChange={onFilterChange} />);
    const label = screen.getByRole('button', { name: 'Show raw output for Alpha' });
    expect(label).toHaveTextContent('Alpha');
    fireEvent.click(screen.getByText('Alpha'));
    expect(onFilterChange).toHaveBeenCalledWith('1:11');
  });

  it('honestly labels recoverable no-response and late receiving updates', () => {
    const { rerender } = render(<RconCommandRun run={makeRun([
      result('1:11', 'Alpha', { state: 'no_response', lines: [] }),
    ])} />);
    expect(screen.getByText('No response yet')).toBeInTheDocument();
    rerender(<RconCommandRun run={makeRun([result('1:11', 'Alpha', { state: 'receiving', content: 'late' })])} />);
    expect(screen.getByText('Receiving')).toBeInTheDocument();
  });
});
