import { createRef } from 'react';
import { EditorView } from '@codemirror/view';
import { act, render } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import RconRawOutputViewer from '../RconRawOutputViewer';

beforeAll(() => {
  const rect = { bottom: 0, height: 0, left: 0, right: 0, top: 0, width: 0, x: 0, y: 0, toJSON: () => ({}) };
  Range.prototype.getBoundingClientRect = () => rect;
  Range.prototype.getClientRects = () => [];
});

describe('RconRawOutputViewer', () => {
  afterEach(() => vi.restoreAllMocks());

  it('formats commands, responses, errors, stats, and multiline content', () => {
    const ref = createRef();
    render(<RconRawOutputViewer ref={ref} />);

    act(() => {
      ref.current.append({ type: 'command', content: 'status', timestamp: '12:00:00' });
      ref.current.append({ type: 'response', content: 'line one\nline two', timestamp: '12:00:01' });
      ref.current.append({ type: 'error', content: 'bad', timestamp: '12:00:02' });
      ref.current.append({ type: 'stats', content: 'MATCH_STARTED', timestamp: '12:00:03' });
    });

    expect(ref.current.getText()).toBe(
      '[12:00:00] > status\n[12:00:01] line one\nline two\n[12:00:02] ^1ERROR: bad\n[12:00:03] ^8MATCH_STARTED'
    );
  });

  it('appends repeated events at the document end without replacing existing text', () => {
    const dispatch = vi.spyOn(EditorView.prototype, 'dispatch');
    const ref = createRef();
    render(<RconRawOutputViewer ref={ref} />);

    act(() => {
      ref.current.append({ type: 'response', content: 'first', timestamp: 'one' });
      ref.current.append({ type: 'response', content: 'second', timestamp: 'two' });
    });

    expect(ref.current.getText()).toBe('[one] first\n[two] second');
    const secondAppend = dispatch.mock.calls.at(-1)[0].changes;
    expect(secondAppend).toEqual({
      from: '[one] first'.length,
      insert: '\n[two] second',
    });
  });

  it('deletes only the oldest overflow prefix while appending in the same dispatch', () => {
    const dispatch = vi.spyOn(EditorView.prototype, 'dispatch');
    const ref = createRef();
    render(<RconRawOutputViewer ref={ref} />);

    act(() => ref.current.append({
      type: 'response',
      content: Array.from({ length: 999 }, (_, i) => `line-${i}`).join('\n'),
      timestamp: 'now',
    }));
    const before = ref.current.getText();
    act(() => ref.current.append({ type: 'response', content: 'next-a\nnext-b', timestamp: 'later' }));

    const lines = ref.current.getText().split('\n');
    expect(lines).toHaveLength(1000);
    expect(lines[0]).toBe('line-1');
    expect(lines.at(-2)).toBe('[later] next-a');
    expect(lines.at(-1)).toBe('next-b');
    expect(dispatch.mock.calls.at(-1)[0].changes).toEqual([
      { from: 0, to: before.indexOf('\n') + 1 },
      { from: before.length, insert: '\n[later] next-a\nnext-b' },
    ]);
  });

  it('keeps the last 1000 lines of an oversized single event without a leading newline', () => {
    const ref = createRef();
    render(<RconRawOutputViewer ref={ref} />);

    act(() => ref.current.append({
      type: 'response',
      content: Array.from({ length: 1002 }, (_, i) => `line-${i}`).join('\n'),
      timestamp: 'now',
    }));

    const text = ref.current.getText();
    const lines = text.split('\n');
    expect(lines).toHaveLength(1000);
    expect(text.startsWith('\n')).toBe(false);
    expect(lines[0]).toBe('line-2');
    expect(lines.at(-1)).toBe('line-1001');
  });

  it('clears output and getText reports the empty document', () => {
    const ref = createRef();
    render(<RconRawOutputViewer ref={ref} />);

    act(() => ref.current.append({ type: 'response', content: 'temporary', timestamp: 'now' }));
    expect(ref.current.getText()).toBe('[now] temporary');

    act(() => ref.current.clear());
    expect(ref.current.getText()).toBe('');
  });
});
