import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import { EditorState, Prec } from '@codemirror/state';
import { defaultKeymap } from '@codemirror/commands';
import { search, searchKeymap } from '@codemirror/search';
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
} from '@codemirror/view';
import { oneDark } from '@codemirror/theme-one-dark';

import { quakeColorPlugin } from '../../utils/quakeColorExtension';
import { rconTheme } from '../../utils/rconTheme';

const MAX_LINES = 1000;

function formatEvent({ type, content, timestamp }, showMetadata) {
  const prefix = showMetadata ? `[${timestamp}] ` : '';
  if (type === 'command') return `${prefix}> ${content}`;
  if (type === 'error') return `${prefix}^1ERROR: ${content}`;
  if (type === 'stats') return `${prefix}^8${content}`;
  return `${prefix}${content}`;
}

const RconRawOutputViewer = forwardRef(function RconRawOutputViewer({ showMetadata = true }, ref) {
  const containerRef = useRef(null);
  const viewRef = useRef(null);
  const extensions = useMemo(() => [
    lineNumbers(),
    highlightActiveLine(),
    highlightActiveLineGutter(),
    drawSelection(),
    search(),
    Prec.highest(keymap.of([...searchKeymap, ...defaultKeymap])),
    oneDark,
    rconTheme,
    quakeColorPlugin,
    EditorState.readOnly.of(true),
    EditorView.editable.of(true),
  ], []);

  useEffect(() => {
    const view = new EditorView({
      state: EditorState.create({ doc: '', extensions }),
      parent: containerRef.current,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [extensions]);

  useImperativeHandle(ref, () => ({
    append(event) {
      const view = viewRef.current;
      if (!view) return;
      const eventLines = formatEvent(event, showMetadata).split('\n').slice(-MAX_LINES);
      const formatted = eventLines.join('\n');
      const doc = view.state.doc;
      const currentLines = doc.length ? doc.lines : 0;
      const overflow = Math.max(0, currentLines + eventLines.length - MAX_LINES);
      let changes;

      if (!doc.length) {
        changes = { from: 0, insert: formatted };
      } else if (overflow >= currentLines) {
        changes = { from: 0, to: doc.length, insert: formatted };
      } else {
        const append = { from: doc.length, insert: `\n${formatted}` };
        changes = overflow
          ? [{ from: 0, to: doc.line(overflow + 1).from }, append]
          : append;
      }
      view.dispatch({ changes });
      requestAnimationFrame(() => {
        if (viewRef.current === view) view.scrollDOM.scrollTop = view.scrollDOM.scrollHeight;
      });
    },
    clear() {
      const view = viewRef.current;
      if (view?.state.doc.length) {
        view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: '' } });
      }
    },
    getText() {
      return viewRef.current?.state.doc.toString() || '';
    },
  }), [showMetadata]);

  return (
    <div
      ref={containerRef}
      className="h-full rounded-lg border-2 border-theme-strong overflow-hidden [&_.cm-editor]:h-full"
      style={{ background: 'rgba(0,0,0,0.4)' }}
    />
  );
});

export default RconRawOutputViewer;
