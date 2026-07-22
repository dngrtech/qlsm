import { useEffect, useRef } from 'react';
import { selectionState } from '../../utils/rconTargets';

function TriStateCheckbox({ label, state, disabled, onChange }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = state === 'some'; }, [state]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={state === 'all'} disabled={disabled}
    onChange={() => onChange(state !== 'all')}
    className="h-4 w-4 rounded border-theme accent-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-50" />;
}

function runtimeValue(states, key) {
  return states instanceof Map ? states.get(key) : states?.[key];
}

function RuntimeIndicator({ value }) {
  if (!value) return null;
  const raw = typeof value === 'string' ? value : value.state ?? value.status;
  if (!raw) return null;
  const state = String(raw).toLowerCase();
  const label = state.charAt(0).toUpperCase() + state.slice(1);
  const reason = typeof value === 'object' ? value.reason : null;
  const color = state === 'ready' ? 'text-emerald-600 dark:text-emerald-400'
    : state === 'failed' ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400';
  const text = `${label}${reason ? `: ${reason}` : ''}`;
  return <span className={`block truncate text-xs ${color}`} role="status" title={text}>{text}</span>;
}

function InstanceRow({ hostLabel, instance, selectedKeys, setTargetChecked, runtimeStates }) {
  const runtime = runtimeValue(runtimeStates, instance.key);
  // Status sits under the name: in an 18rem pane a long reason would otherwise
  // squeeze the name down to "Thund…", making targets indistinguishable.
  return (
    <li className="flex min-w-0 items-start gap-2 border-t border-theme px-3 py-2 pl-10">
      <input type="checkbox" aria-label={`Select ${instance.label} on ${hostLabel}`} checked={selectedKeys.has(instance.key)}
        disabled={!instance.eligible} onChange={(event) => setTargetChecked(instance.key, event.target.checked)}
        className="mt-0.5 h-4 w-4 flex-none rounded border-theme accent-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-50" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-theme-primary" title={instance.label}>{instance.label}</span>
        {!instance.eligible && <span className="block truncate text-xs text-theme-muted">{instance.reason}</span>}
        <RuntimeIndicator value={runtime} />
      </span>
    </li>
  );
}

function HostRow({ host, expanded, selectedKeys, runtimeStates, setHostChecked, setTargetChecked, toggleHostExpanded }) {
  const eligibleKeys = new Set(host.instances.filter((item) => item.eligible).map((item) => item.key));
  const state = selectionState(eligibleKeys, selectedKeys);
  return (
    <li className="overflow-hidden rounded-md border border-theme bg-theme-elevated">
      <div className="flex items-center gap-2 px-3 py-2.5">
        <button type="button" aria-label={`${expanded ? 'Collapse' : 'Expand'} ${host.label}`}
          onClick={() => toggleHostExpanded(host.id)}
          className="inline-flex h-6 w-6 items-center justify-center rounded text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5">
          <span aria-hidden="true">{expanded ? '▾' : '▸'}</span>
        </button>
        <TriStateCheckbox label={`Select ${host.label}`} state={state} disabled={!eligibleKeys.size}
          onChange={(checked) => setHostChecked(eligibleKeys, checked)} />
        <span className="min-w-0 flex-1 break-words text-sm font-medium text-theme-primary">{host.label}</span>
        <span className="flex-none text-xs text-theme-muted">{eligibleKeys.size} available</span>
      </div>
      {expanded && (host.instances.length ? (
        <ul>{host.instances.map((instance) => <InstanceRow key={instance.key} hostLabel={host.label} instance={instance}
          selectedKeys={selectedKeys} runtimeStates={runtimeStates} setTargetChecked={setTargetChecked} />)}</ul>
      ) : <p className="border-t border-theme px-3 py-2 pl-10 text-xs text-theme-muted">No instances</p>)}
    </li>
  );
}

export default function RconTargetTree({
  hosts = [], selectedKeys = new Set(), expandedHostIds = new Set(), runtimeStates = new Map(),
  setTargetChecked, setHostChecked, selectAllEligible, selectNone, toggleHostExpanded,
}) {
  return (
    <section aria-label="RCON targets" className="space-y-3">
      <div className="flex items-center justify-end gap-2">
        <button type="button" onClick={selectAllEligible} className="btn btn-secondary px-3 py-1.5 text-xs">Select All</button>
        <button type="button" onClick={selectNone} className="btn btn-secondary px-3 py-1.5 text-xs">Select None</button>
      </div>
      <ul className="space-y-2">{hosts.map((host) => <HostRow key={host.id} host={host}
        expanded={expandedHostIds.has(host.id)} selectedKeys={selectedKeys} runtimeStates={runtimeStates}
        setHostChecked={setHostChecked} setTargetChecked={setTargetChecked} toggleHostExpanded={toggleHostExpanded} />)}</ul>
      {!hosts.length && <p className="py-4 text-center text-sm text-theme-muted">No hosts</p>}
    </section>
  );
}
