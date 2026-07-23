import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  MAX_RAW_LINES,
  MAX_RUNS,
  NO_RESPONSE_AFTER_MS,
  QUIET_AFTER_MS,
  countPhysicalLines,
  useRconCommandRuns,
} from '../useRconCommandRuns';

const one = { key: '1:11', name: 'Alpha', host_id: 1, instance_id: 11 };
const two = { name: 'Bravo', host_id: 2, instance_id: 22 };
const resultFor = (hook, runId, key = '1:11') => hook.result.current.runs
  .find((run) => run.id === runId).results.find((result) => result.key === key);

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function start(hook, id = 'run-1', command = 'status', readyTargets = [one], skippedTargets = []) {
  act(() => hook.result.current.startRun({ id, command, readyTargets, skippedTargets, timestamp: '12:00:00' }));
}

describe('useRconCommandRuns snapshots and bounded raw evidence', () => {
  it('exports the exact plan timing and retention constants', () => {
    expect(QUIET_AFTER_MS).toBe(1500);
    expect(NO_RESPONSE_AFTER_MS).toBe(5000);
    expect(MAX_RUNS).toBe(50);
    expect(MAX_RAW_LINES).toBe(1000);
  });

  it.each([
    ['', 1],
    ['one', 1],
    ['one\ntwo\nthree', 3],
    ['one\n', 2],
  ])('counts physical content lines in %j as %i', (content, count) => {
    expect(countPhysicalLines(content)).toBe(count);
  });

  it('starts immutable ready/skipped snapshots and marks only attempted targets raw', () => {
    const hook = renderHook(() => useRconCommandRuns());
    const ready = { ...one };
    const skipped = { ...two, reason: 'not ready' };
    start(hook, 'run-1', 'status', [ready], [skipped]);
    ready.name = 'Changed';
    skipped.name = 'Changed too';

    expect(hook.result.current.runs[0]).toMatchObject({ id: 'run-1', command: 'status', timestamp: '12:00:00' });
    expect(hook.result.current.runs[0].results).toEqual([
      expect.objectContaining({
        key: '1:11', name: 'Alpha', display_name: 'Alpha',
        state: 'pending_dispatch', lines: [],
      }),
      expect.objectContaining({
        key: '2:22', name: 'Bravo', display_name: 'Bravo',
        state: 'skipped', reason: 'not ready', lines: [],
      }),
    ]);
    expect(hook.result.current.rawStreams.get('1:11')).toEqual([
      { type: 'command', content: 'status', attempted: true, timestamp: '12:00:00' },
    ]);
    expect(hook.result.current.rawStreams.has('2:22')).toBe(false);
  });

  it('keeps 50 newest runs and 1000 oldest-first events per target', () => {
    const hook = renderHook(() => useRconCommandRuns());
    act(() => {
      for (let index = 0; index < 51; index += 1) {
        hook.result.current.startRun({ id: `r${index}`, command: `${index}`, readyTargets: [one] });
      }
      for (let index = 0; index < 950; index += 1) {
        hook.result.current.appendMessage({ host_id: 1, instance_id: 11, content: `line-${index}`, timestamp: `${index}` });
      }
    });
    expect(hook.result.current.runs).toHaveLength(50);
    expect(hook.result.current.runs[0].id).toBe('r50');
    expect(hook.result.current.runs.at(-1).id).toBe('r1');
    const raw = hook.result.current.rawStreams.get('1:11');
    expect(raw).toHaveLength(1000);
    expect(raw[0]).toMatchObject({ type: 'command', content: '1', attempted: true });
    expect(raw.at(-1)).toMatchObject({ type: 'response', content: 'line-949' });
  });

  it('drops whole oldest events before trimming inside the oldest remaining event', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1', 'first\nsecond', [one]);
    act(() => hook.result.current.appendMessage({
      ...one,
      content: Array.from({ length: 1000 }, (_, index) => `line-${index}`).join('\n'),
      timestamp: 'later',
    }));
    const raw = hook.result.current.rawStreams.get('1:11');
    expect(raw).toHaveLength(1);
    expect(raw[0].content.split('\n')).toHaveLength(1000);
    expect(raw[0].content).toMatch(/^line-0/);
  });

  it.each([1000, 1001])('retains exactly the newest 1000 of %i lines without a leading newline', (count) => {
    const hook = renderHook(() => useRconCommandRuns());
    act(() => hook.result.current.appendMessage({
      ...one,
      content: Array.from({ length: count }, (_, index) => `line-${index}`).join('\n'),
    }));
    const event = hook.result.current.rawStreams.get('1:11')[0];
    expect(event.content.split('\n')).toHaveLength(Math.min(count, 1000));
    expect(event.content.startsWith('\n')).toBe(false);
    expect(event.content.split('\n')[0]).toBe(`line-${Math.max(0, count - 1000)}`);
  });

  it('trims an oversized event and continues appending within the same physical-line bound', () => {
    const hook = renderHook(() => useRconCommandRuns());
    act(() => {
      hook.result.current.appendMessage({
        ...one,
        content: Array.from({ length: 1002 }, (_, index) => `line-${index}`).join('\n'),
      });
      hook.result.current.appendMessage({ ...one, content: 'next-a\nnext-b' });
    });
    const raw = hook.result.current.rawStreams.get('1:11');
    expect(raw.reduce((sum, event) => sum + countPhysicalLines(event.content), 0)).toBe(1000);
    expect(raw[0].content.split('\n')[0]).toBe('line-4');
    expect(raw.at(-1).content).toBe('next-a\nnext-b');
  });

  it.each([1000, 1001])('bounds active grouped output at the newest 1000 of %i physical lines', (count) => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => hook.result.current.appendMessage({
      ...one,
      content: Array.from({ length: count }, (_, index) => `group-${index}`).join('\n'),
      timestamp: 'grouped',
    }));

    const lines = resultFor(hook, 'run-1').lines;
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({ type: 'response', timestamp: 'grouped' });
    expect(lines[0].content.split('\n')).toHaveLength(Math.min(count, MAX_RAW_LINES));
    expect(lines[0].content.split('\n')[0]).toBe(`group-${Math.max(0, count - MAX_RAW_LINES)}`);
  });

  it('preserves newest grouped-event metadata when whole and partial oldest events are trimmed', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => {
      hook.result.current.appendMessage({ ...one, content: 'drop-a\ndrop-b', timestamp: 'old' });
      hook.result.current.appendMessage({
        ...one,
        type: 'error',
        content: Array.from({ length: 999 }, (_, index) => `keep-${index}`).join('\n'),
        timestamp: 'new',
      });
    });

    const lines = resultFor(hook, 'run-1').lines;
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ type: 'response', content: 'drop-b', timestamp: 'old' });
    expect(lines[1]).toMatchObject({ type: 'error', timestamp: 'new' });
    expect(lines.reduce((sum, event) => sum + countPhysicalLines(event.content), 0)).toBe(MAX_RAW_LINES);
  });

  it('keeps 50 noisy grouped runs bounded while their independent quiet timers still settle', () => {
    const hook = renderHook(() => useRconCommandRuns());
    act(() => {
      for (let index = 0; index < MAX_RUNS; index += 1) {
        hook.result.current.startRun({ id: `noisy-${index}`, command: 'status', readyTargets: [one] });
        hook.result.current.appendMessage({
          ...one,
          content: Array.from({ length: 1001 }, (_, line) => `${index}-${line}`).join('\n'),
        });
      }
    });

    expect(hook.result.current.runs).toHaveLength(MAX_RUNS);
    expect(hook.result.current.runs.every((run) => (
      run.results[0].lines.reduce((sum, event) => sum + countPhysicalLines(event.content), 0)
      <= MAX_RAW_LINES
    ))).toBe(true);
    expect(vi.getTimerCount()).toBe(MAX_RUNS);
    act(() => vi.advanceTimersByTime(QUIET_AFTER_MS));
    expect(hook.result.current.runs.every((run) => run.results[0].state === 'quiet')).toBe(true);
  });

  it('keeps the attempted command marker when the backend rejects the command', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'denied' }],
    }));
    expect(hook.result.current.rawStreams.get('1:11')[0]).toEqual({
      type: 'command', content: 'status', attempted: true, timestamp: '12:00:00',
    });
  });
});

describe('useRconCommandRuns acknowledgement and response state', () => {
  it('closes pending attribution on rejection so later output is raw-only', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);

    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'denied' }],
    }));
    act(() => hook.result.current.appendMessage({ ...one, content: 'unrelated output' }));

    expect(resultFor(hook, 'run-1')).toMatchObject({
      state: 'rejected', reason: 'denied', lines: [],
    });
    expect(hook.result.current.rawStreams.get('1:11').at(-1)).toMatchObject({
      type: 'response', content: 'unrelated output',
    });
  });

  it('closes attribution on rejection after output while preserving anomaly evidence', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => hook.result.current.appendMessage({ ...one, content: 'ack evidence' }));

    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'denied' }],
    }));
    act(() => hook.result.current.appendMessage({ ...one, content: 'unrelated output' }));

    expect(resultFor(hook, 'run-1')).toMatchObject({
      state: 'rejected',
      reason: 'denied',
      ack_anomaly: true,
      lines: [expect.objectContaining({ content: 'ack evidence' })],
    });
    expect(hook.result.current.rawStreams.get('1:11')).toEqual([
      expect.objectContaining({ type: 'command', content: 'status', attempted: true }),
      expect.objectContaining({ type: 'response', content: 'ack evidence' }),
      expect.objectContaining({ type: 'response', content: 'unrelated output' }),
    ]);
  });

  it('does not let a delayed rejection for a superseded run close newer attribution', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1');
    start(hook, 'run-2');

    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'late rejection' }],
    }));
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'duplicate rejection' }],
    }));
    act(() => hook.result.current.appendMessage({ ...one, content: 'run-2 output' }));

    expect(resultFor(hook, 'run-1')).toMatchObject({ state: 'rejected', lines: [] });
    expect(resultFor(hook, 'run-2')).toMatchObject({
      state: 'receiving',
      lines: [expect.objectContaining({ content: 'run-2 output' })],
    });
  });

  it.each([
    ['missing', { targets: [] }, 'Missing command acknowledgement'],
    ['malformed', { targets: 'not-an-array' }, 'Malformed command acknowledgement'],
    ['top-level error', { error: 'publish failed', targets: [] }, 'Command acknowledgement error'],
  ])('closes attribution on a %s terminal acknowledgement', (_label, ack, reason) => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);

    act(() => hook.result.current.applyDispatchAck('run-1', ack));
    act(() => hook.result.current.appendMessage({ ...one, content: 'unrelated output' }));

    expect(resultFor(hook, 'run-1')).toMatchObject({ state: 'rejected', reason, lines: [] });
    expect(hook.result.current.rawStreams.get('1:11').at(-1)).toMatchObject({
      content: 'unrelated output',
    });
  });

  it('starts no-response timing only at a queued acknowledgement', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => vi.advanceTimersByTime(10_000));
    expect(resultFor(hook, 'run-1').state).toBe('pending_dispatch');
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ host_id: 1, instance_id: 11, state: 'queued' }],
    }));
    act(() => vi.advanceTimersByTime(4_999));
    expect(resultFor(hook, 'run-1').state).toBe('queued');
    act(() => vi.advanceTimersByTime(1));
    expect(resultFor(hook, 'run-1').state).toBe('no_response');
  });

  it('retains response/failure before ack and makes duplicate or delayed queued ack harmless', () => {
    const responseHook = renderHook(() => useRconCommandRuns());
    start(responseHook);
    act(() => responseHook.result.current.appendMessage({ ...one, content: 'players\n2', timestamp: '12:00:01' }));
    act(() => responseHook.result.current.applyDispatchAck('run-1', { targets: [{ ...one, state: 'queued' }] }));
    act(() => responseHook.result.current.applyDispatchAck('run-1', { targets: [{ ...one, state: 'queued' }] }));
    act(() => vi.advanceTimersByTime(5_000));
    expect(resultFor(responseHook, 'run-1')).toMatchObject({ state: 'quiet', lines: [{ type: 'response', content: 'players\n2', timestamp: '12:00:01' }] });

    const failedHook = renderHook(() => useRconCommandRuns());
    start(failedHook);
    act(() => failedHook.result.current.applyTargetStatus({ ...one, state: 'failed', reason: 'lost' }));
    act(() => failedHook.result.current.applyDispatchAck('run-1', { targets: [{ ...one, state: 'queued' }] }));
    expect(resultFor(failedHook, 'run-1')).toMatchObject({ state: 'failed', reason: 'lost' });
  });

  it('normalizes missing/rejected acknowledgements and exposes reject-after-output anomaly', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => hook.result.current.appendMessage({ ...one, content: 'evidence' }));
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'denied' }],
    }));
    expect(resultFor(hook, 'run-1')).toMatchObject({ state: 'rejected', reason: 'denied', ack_anomaly: true });
    expect(resultFor(hook, 'run-1').lines).toHaveLength(1);

    start(hook, 'missing');
    act(() => hook.result.current.applyDispatchAck('missing', { targets: [] }));
    expect(resultFor(hook, 'missing')).toMatchObject({ state: 'rejected', reason: 'Missing command acknowledgement' });
  });

  it('applies only the first acknowledgement and ignores contradictory duplicate or late acks', () => {
    const queued = renderHook(() => useRconCommandRuns());
    start(queued);
    act(() => queued.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'queued' }],
    }));
    act(() => queued.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'late rejection' }],
    }));
    expect(resultFor(queued, 'run-1')).toMatchObject({ state: 'queued' });
    expect(resultFor(queued, 'run-1').reason).toBeUndefined();

    const rejected = renderHook(() => useRconCommandRuns());
    start(rejected);
    act(() => rejected.result.current.appendMessage({ ...one, content: 'evidence' }));
    act(() => rejected.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'first rejection' }],
    }));
    act(() => rejected.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'queued' }],
    }));
    expect(resultFor(rejected, 'run-1')).toMatchObject({
      state: 'rejected', reason: 'first rejection', ack_anomaly: true,
    });
  });
});

describe('useRconCommandRuns attribution, quiet timers, and statuses', () => {
  it('becomes quiet after 1.5s and late output reopens and rearms quiet', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => hook.result.current.appendMessage({ ...one, content: 'first' }));
    act(() => vi.advanceTimersByTime(1_499));
    expect(resultFor(hook, 'run-1').state).toBe('receiving');
    act(() => vi.advanceTimersByTime(1));
    expect(resultFor(hook, 'run-1').state).toBe('quiet');
    act(() => hook.result.current.appendMessage({ ...one, content: 'late' }));
    expect(resultFor(hook, 'run-1').state).toBe('receiving');
    act(() => vi.advanceTimersByTime(1_500));
    expect(resultFor(hook, 'run-1').state).toBe('quiet');
  });

  it('closes prior attribution on a newer command while the prior quiet timer still settles', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'old');
    act(() => hook.result.current.appendMessage({ ...one, content: 'old line' }));
    start(hook, 'new');
    act(() => {
      hook.result.current.appendMessage({ ...one, content: 'new line' });
      hook.result.current.appendMessage({ host_id: 9, instance_id: 99, content: 'unsolicited' });
      vi.advanceTimersByTime(1_500);
    });
    expect(resultFor(hook, 'old').state).toBe('quiet');
    expect(resultFor(hook, 'old').lines).toHaveLength(1);
    expect(resultFor(hook, 'new').state).toBe('quiet');
    expect(resultFor(hook, 'new').lines.map((line) => line.content)).toEqual(['new line']);
    expect(hook.result.current.rawStreams.get('9:99')).toHaveLength(1);
    expect(hook.result.current.runs.flatMap((run) => run.results).some((item) => item.key === '9:99')).toBe(false);
  });

  it('settles superseded receiving runs on their own schedule without deleting the newer timer', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1');
    act(() => hook.result.current.appendMessage({ ...one, content: 'first' }));
    act(() => vi.advanceTimersByTime(500));
    start(hook, 'run-2');
    act(() => hook.result.current.appendMessage({ ...one, content: 'second' }));

    act(() => vi.advanceTimersByTime(1_000));
    expect(resultFor(hook, 'run-1').state).toBe('quiet');
    expect(resultFor(hook, 'run-2').state).toBe('receiving');
    act(() => vi.advanceTimersByTime(500));
    expect(resultFor(hook, 'run-2').state).toBe('quiet');
  });

  it('settles a superseded queued run as no-response without changing the newer run', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1');
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'queued' }],
    }));
    act(() => vi.advanceTimersByTime(1_000));
    start(hook, 'run-2');

    act(() => vi.advanceTimersByTime(4_000));
    expect(resultFor(hook, 'run-1').state).toBe('no_response');
    expect(resultFor(hook, 'run-2').state).toBe('pending_dispatch');
  });

  it('also closes prior attribution when the newer click-time target is skipped', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'old');
    start(hook, 'skipped', 'status', [], [{ ...one, reason: 'not ready' }]);
    act(() => hook.result.current.appendMessage({ ...one, content: 'stray' }));
    expect(resultFor(hook, 'old').lines).toEqual([]);
    expect(resultFor(hook, 'skipped').lines).toEqual([]);
    expect(hook.result.current.rawStreams.get('1:11').at(-1)).toMatchObject({ content: 'stray' });
  });

  it('closes receiving attribution on terminal failure and keeps later events raw-only', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => hook.result.current.appendMessage({ ...one, content: 'before failure' }));
    act(() => {
      hook.result.current.applyTargetStatus({ host_id: 1, state: 'failed', reason: 'partial' });
      hook.result.current.applyTargetStatus({ ...two, state: 'failed', reason: 'wrong' });
      hook.result.current.applyTargetStatus({ ...one, state: 'disconnected', reason: 'gone' });
      hook.result.current.applyTargetStatus({ ...one, state: 'ready' });
      hook.result.current.appendMessage({ ...one, type: 'error', error: 'late evidence' });
      hook.result.current.applyDispatchAck('run-1', { targets: [{ ...one, state: 'queued' }] });
      vi.advanceTimersByTime(10_000);
    });

    expect(resultFor(hook, 'run-1')).toMatchObject({
      state: 'failed',
      reason: 'gone',
      lines: [{ type: 'response', content: 'before failure' }],
    });
    expect(hook.result.current.rawStreams.get('1:11').at(-1)).toMatchObject({
      type: 'error', content: 'late evidence',
    });

    start(hook, 'run-2');
    act(() => hook.result.current.appendMessage({ ...one, content: 'new run output' }));
    expect(resultFor(hook, 'run-2')).toMatchObject({
      state: 'receiving',
      lines: [expect.objectContaining({ content: 'new run output' })],
    });
    expect(resultFor(hook, 'run-1').lines).toHaveLength(1);
  });

  it.each([
    ['pending_dispatch', 'error'],
    ['queued', 'failed'],
    ['no_response', 'disconnected'],
  ])(
    'closes %s attribution on %s and prevents timer or delayed-ack revival',
    (initialState, terminalState) => {
      const hook = renderHook(() => useRconCommandRuns());
      start(hook);
      if (initialState !== 'pending_dispatch') {
        act(() => hook.result.current.applyDispatchAck('run-1', {
          targets: [{ ...one, state: 'queued' }],
        }));
      }
      if (initialState === 'no_response') act(() => vi.advanceTimersByTime(5_000));
      expect(resultFor(hook, 'run-1').state).toBe(initialState);

      act(() => {
        hook.result.current.applyTargetStatus({ ...one, state: terminalState, reason: 'lost' });
        hook.result.current.appendMessage({ ...one, content: 'too late' });
        hook.result.current.applyDispatchAck('run-1', { targets: [{ ...one, state: 'queued' }] });
        vi.advanceTimersByTime(10_000);
      });

      expect(resultFor(hook, 'run-1')).toMatchObject({ state: 'failed', reason: 'lost', lines: [] });
      expect(hook.result.current.rawStreams.get('1:11').at(-1)).toMatchObject({ content: 'too late' });
    },
  );

  it('a delayed historical rejection clears only that run-target timer', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1');
    act(() => hook.result.current.appendMessage({ ...one, content: 'old evidence' }));
    act(() => vi.advanceTimersByTime(500));
    start(hook, 'run-2');
    act(() => hook.result.current.appendMessage({ ...one, content: 'new evidence' }));
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'rejected', reason: 'late rejection' }],
    }));

    act(() => vi.advanceTimersByTime(1_500));
    expect(resultFor(hook, 'run-1')).toMatchObject({ state: 'rejected', ack_anomaly: true });
    expect(resultFor(hook, 'run-2').state).toBe('quiet');
  });

  it('cleans timers belonging to evicted runs', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1');
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'queued' }],
    }));
    expect(vi.getTimerCount()).toBe(1);
    act(() => {
      for (let index = 2; index <= 51; index += 1) {
        hook.result.current.startRun({ id: `run-${index}`, command: 'status', readyTargets: [one] });
      }
    });
    expect(hook.result.current.runs.some((run) => run.id === 'run-1')).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears every run-target timer when run history is cleared', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1');
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'queued' }],
    }));
    start(hook, 'run-2', 'status', [two]);
    act(() => hook.result.current.appendMessage({ ...two, content: 'evidence' }));
    expect(vi.getTimerCount()).toBe(2);
    act(() => hook.result.current.clearRuns());
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears every run-target timer on unmount', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook, 'run-1');
    act(() => hook.result.current.applyDispatchAck('run-1', {
      targets: [{ ...one, state: 'queued' }],
    }));
    expect(vi.getTimerCount()).toBe(1);
    hook.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('lets no-response attribution accept late output and supports precise clears', () => {
    const hook = renderHook(() => useRconCommandRuns());
    start(hook);
    act(() => hook.result.current.applyDispatchAck('run-1', { targets: [{ ...one, state: 'queued' }] }));
    act(() => vi.advanceTimersByTime(5_000));
    act(() => hook.result.current.appendMessage({ ...one, content: 'finally' }));
    expect(resultFor(hook, 'run-1').state).toBe('receiving');
    act(() => hook.result.current.clearRaw('1:11'));
    expect(hook.result.current.rawStreams.has('1:11')).toBe(false);
    act(() => hook.result.current.clearRuns());
    expect(hook.result.current.runs).toEqual([]);
  });
});
