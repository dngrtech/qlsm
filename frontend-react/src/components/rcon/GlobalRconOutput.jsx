import { useRef } from 'react';

import RconCommandRun from './RconCommandRun';
import RconOutputFilters from './RconOutputFilters';
import RconRawOutputViewer from './RconRawOutputViewer';
import useIncrementalViewerReplay from './useIncrementalViewerReplay';

const EMPTY_EVENTS = [];

function TargetOutput({ events, targetKey }) {
  const viewerRef = useRef(null);
  useIncrementalViewerReplay(viewerRef, events, targetKey);

  return <div className="h-full min-h-64"><RconRawOutputViewer ref={viewerRef} /></div>;
}

export default function GlobalRconOutput({
  activeFilter,
  onFilterChange,
  selectedTargets = [],
  runs = [],
  rawStreams = new Map(),
  activeKey,
}) {
  const active = activeFilter ?? activeKey ?? 'all';
  const events = active === 'all' ? EMPTY_EVENTS : rawStreams.get(active) ?? EMPTY_EVENTS;

  return (
    <div className="flex h-full flex-col gap-3">
      <RconOutputFilters
        activeFilter={active}
        onFilterChange={onFilterChange}
        selectedTargets={selectedTargets}
        runs={runs}
        rawStreams={rawStreams}
      />
      {active === 'all' ? (runs.length ? (
        <div className="space-y-3" role="tabpanel" aria-label="All command runs">
          {runs.map((run) => (
            <RconCommandRun key={run.id} run={run} onFilterChange={onFilterChange} />
          ))}
        </div>
      ) : (
        <p className="py-8 text-center text-sm text-theme-muted">No commands have been sent.</p>
      )) : (events.length ? (
        <div role="tabpanel" aria-label="Target raw output" className="min-h-0 flex-1">
          <TargetOutput events={events} targetKey={active} />
        </div>
      ) : (
        <p className="py-8 text-center text-sm text-theme-muted">No output for this target.</p>
      ))}
    </div>
  );
}
