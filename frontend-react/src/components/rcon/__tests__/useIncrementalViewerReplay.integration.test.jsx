import { createRef, forwardRef, StrictMode, useImperativeHandle, useRef } from 'react';
import { render, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';

import RconRawOutputViewer from '../RconRawOutputViewer';
import useIncrementalViewerReplay from '../useIncrementalViewerReplay';

beforeAll(() => {
  const rect = { bottom: 0, height: 0, left: 0, right: 0, top: 0, width: 0, x: 0, y: 0, toJSON: () => ({}) };
  Range.prototype.getBoundingClientRect = () => rect;
  Range.prototype.getClientRects = () => [];
});

const ReplayHarness = forwardRef(function ReplayHarness({ events }, ref) {
  const viewerRef = useRef(null);
  useIncrementalViewerReplay(viewerRef, events, 'retained-target');
  useImperativeHandle(ref, () => ({
    getText: () => viewerRef.current?.getText() || '',
  }), []);

  return <RconRawOutputViewer ref={viewerRef} />;
});

describe('useIncrementalViewerReplay with RconRawOutputViewer', () => {
  it('replays retained history after StrictMode recreates CodeMirror and incrementally appends a suffix', async () => {
    const retained = [
      { type: 'command', content: 'status', timestamp: '10:00:00' },
      { type: 'response', content: 'first response', timestamp: '10:00:01' },
    ];
    const suffix = { type: 'response', content: 'second response', timestamp: '10:00:02' };
    const ref = createRef();
    const { rerender } = render(
      <StrictMode><ReplayHarness ref={ref} events={retained} /></StrictMode>
    );

    await waitFor(() => expect(ref.current.getText()).toBe(
      '[10:00:00] > status\n[10:00:01] first response'
    ));

    rerender(<StrictMode><ReplayHarness ref={ref} events={[...retained, suffix]} /></StrictMode>);

    await waitFor(() => expect(ref.current.getText()).toBe(
      '[10:00:00] > status\n[10:00:01] first response\n[10:00:02] second response'
    ));
  });
});
