import { useRef, useState } from 'react';

import QuakeColoredText, { QuakeEventText } from './QuakeColoredText';
import RconRawOutputViewer from './RconRawOutputViewer';
import useIncrementalViewerReplay from './useIncrementalViewerReplay';

const LABELS = {
  pending_dispatch: 'Dispatching',
  queued: 'Queued',
  receiving: 'Receiving',
  quiet: 'Quiet',
  no_response: 'No response yet',
  skipped: 'Skipped',
  rejected: 'Rejected',
  failed: 'Failed',
};

function physicalLines(lines = []) {
  return lines.flatMap((line) => String(line.content ?? '').split('\n'));
}

function statusText(result) {
  const label = LABELS[result.state] ?? result.state;
  return result.reason ? `${label}: ${result.reason}` : label;
}

function OutputViewer({ events, lineCount, resultKey }) {
  const viewerRef = useRef(null);
  useIncrementalViewerReplay(viewerRef, events, resultKey);

  const height = Math.min(360, Math.max(96, lineCount * 22 + 48));
  return (
    <div className="mt-2" style={{ height }}>
      <RconRawOutputViewer ref={viewerRef} showMetadata={false} />
    </div>
  );
}

function copyOutput(lines) {
  try {
    const pending = navigator.clipboard?.writeText(
      physicalLines(lines).join('\n'),
    );
    Promise.resolve(pending).catch(() => {});
  } catch {
    // Clipboard access may be unavailable or denied.
  }
}

function ResultOutput({ result, expanded, onExpandedChange, onFilterChange }) {
  const [searching, setSearching] = useState(false);
  const lines = result.lines ?? [];
  const flattened = physicalLines(lines);
  const count = flattened.length;
  const defaultExpanded = result.state === 'failed' || lines.some((line) => line.type === 'error');
  const expandable = count > 5;
  const showAll = !expandable || (expanded ?? defaultExpanded);
  const tone = ['failed', 'rejected'].includes(result.state) ? 'border-red-500/40 bg-red-500/5'
    : result.state === 'skipped' ? 'border-amber-500/40 bg-amber-500/5'
      : 'border-theme bg-theme-elevated';
  const countLabel = `${count} ${count === 1 ? 'line' : 'lines'}`;

  return (
    <section className={`rounded-md border p-3 ${tone}`} aria-label={`${result.name} output`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-left text-sm">
          {onFilterChange ? (
            <button
              type="button"
              aria-label={`Show raw output for ${result.name}`}
              onClick={() => onFilterChange(result.key)}
              className="font-medium text-theme-primary underline"
            >
              {result.name}
            </button>
          ) : <span className="font-medium text-theme-primary">{result.name}</span>}
          <button
            type="button"
            aria-label={`${result.name}, ${countLabel}`}
            aria-expanded={showAll}
            onClick={() => expandable && onExpandedChange(!showAll)}
            className="text-xs text-theme-muted"
          >
            {countLabel}
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-theme-muted" role="status">{statusText(result)}</span>
          {!expandable && count > 0 && (searching ? (
            <button type="button" aria-label={`Close output search for ${result.name}`}
              onClick={() => setSearching(false)} className="text-xs text-theme-secondary underline">
              Close search
            </button>
          ) : (
            <button type="button" aria-label={`Search output for ${result.name}`}
              onClick={() => setSearching(true)} className="text-xs text-theme-secondary underline">
              Search
            </button>
          ))}
          <button type="button" aria-label={`Copy output for ${result.name}`}
            onClick={() => copyOutput(lines)} className="text-xs text-theme-secondary underline">
            Copy
          </button>
        </div>
      </div>
      {count > 0 && (expandable ? (showAll
        ? <OutputViewer events={lines} lineCount={count} resultKey={result.key} />
        : <QuakeColoredText
            text={String(lines[0]?.content ?? '').split('\n')[0]}
            error={lines[0]?.type === 'error'}
            className="mt-2"
          />) : (searching
        ? <OutputViewer events={lines} lineCount={count} resultKey={result.key} />
        : <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-sm text-theme-primary">
            <QuakeEventText events={lines} />
          </pre>))}
      {result.ack_anomaly && (
        <p className="mt-2 text-xs font-medium text-amber-600 dark:text-amber-400">
          Dispatch rejected after output was received.
        </p>
      )}
    </section>
  );
}

export default function RconCommandRun({ run, onFilterChange }) {
  const [expandedByKey, setExpandedByKey] = useState({});
  const results = run.results ?? [];
  const expandableResults = results.filter((result) => physicalLines(result.lines).length > 5);
  const setExpanded = (key, expanded) => {
    setExpandedByKey((current) => ({ ...current, [key]: expanded }));
  };
  const setAllExpanded = (expanded) => {
    setExpandedByKey((current) => {
      const next = { ...current };
      for (const result of expandableResults) next[result.key] = expanded;
      return next;
    });
  };
  const targetCount = results.length;

  return (
    <article className="rounded-lg border border-theme bg-theme-base p-4">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-mono font-semibold text-theme-primary">&gt; {run.command}</h3>
        <span className="text-xs text-theme-muted">
          {run.timestamp} · {targetCount} {targetCount === 1 ? 'target' : 'targets'}
        </span>
      </header>
      {expandableResults.length > 0 && (
        <div className="mb-2 flex justify-end gap-3">
          <button type="button" aria-label="Expand all target output" onClick={() => setAllExpanded(true)}
            className="text-xs text-theme-secondary underline">Expand all</button>
          <button type="button" aria-label="Collapse all target output" onClick={() => setAllExpanded(false)}
            className="text-xs text-theme-secondary underline">Collapse all</button>
        </div>
      )}
      <div className="space-y-2">
        {results.map((result) => (
          <ResultOutput
            key={result.key}
            result={result}
            expanded={expandedByKey[result.key]}
            onExpandedChange={(expanded) => setExpanded(result.key, expanded)}
            onFilterChange={onFilterChange}
          />
        ))}
      </div>
    </article>
  );
}
