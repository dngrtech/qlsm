/* eslint-disable react-refresh/only-export-components -- shared safe Quake render primitives are tested together. */
import { Fragment } from 'react';

import { QUAKE_COLORS } from '../../utils/quakeColors';

const QUAKE_CODE = /\^([0-9])/g;

export function parseQuakeColorSpans(value) {
  const text = String(value ?? '');
  const spans = [];
  let color = null;
  let cursor = 0;
  let match;

  QUAKE_CODE.lastIndex = 0;
  while ((match = QUAKE_CODE.exec(text)) !== null) {
    if (match.index > cursor) spans.push({ text: text.slice(cursor, match.index), color });
    color = match[1];
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) spans.push({ text: text.slice(cursor), color });
  return spans;
}

export function QuakeColorSpans({ text, error = false }) {
  return parseQuakeColorSpans(text).map((span, index) => (
    <span
      // Position is stable for a fixed output string and avoids incorporating untrusted text into keys.
      key={index}
      className={span.color == null && error ? 'text-red-500' : undefined}
      style={span.color == null ? undefined : { color: QUAKE_COLORS[span.color] }}
    >
      {span.text}
    </span>
  ));
}

export function QuakeEventText({ events }) {
  return events.map((event, index) => (
    <Fragment key={index}>
      {index > 0 ? '\n' : null}
      <QuakeColorSpans text={event.content} error={event.type === 'error'} />
    </Fragment>
  ));
}

export default function QuakeColoredText({ text, error = false, className = '' }) {
  return (
    <pre className={`whitespace-pre-wrap break-words font-mono text-sm text-theme-primary ${className}`}>
      <QuakeColorSpans text={text} error={error} />
    </pre>
  );
}
