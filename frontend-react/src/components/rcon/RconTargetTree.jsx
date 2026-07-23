import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, ChevronUp, Search, Server, Square, SquareCheck, SquareChevronRight } from 'lucide-react';
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

// Tailwind's animate-pulse runs a 2s loop from each dot's own mount time, so
// instances that went ready at different real moments drift out of phase —
// one dim while another is bright. Anchoring a negative delay to Date.now()
// snaps every dot onto the same shared 2s grid (since renderTime - (renderTime
// % PULSE_MS) always lands on a multiple of PULSE_MS since epoch), so they
// stay visually in sync regardless of when each one started pulsing.
const PULSE_MS = 2000;

// Same green/amber/red vocabulary as StatusIndicator's running-badge dot, just
// without the pill/text since a row of targets needs a scannable single line.
function RuntimeDot({ value }) {
  const syncedDelay = useMemo(() => `-${(Date.now() % PULSE_MS) / 1000}s`, []);
  if (!value) return null;
  const raw = typeof value === 'string' ? value : value.state ?? value.status;
  if (!raw) return null;
  const state = String(raw).toLowerCase();
  const label = state.charAt(0).toUpperCase() + state.slice(1);
  const reason = typeof value === 'object' ? value.reason : null;
  const color = state === 'ready' ? 'bg-emerald-500 dark:bg-emerald-400 animate-pulse'
    : state === 'failed' ? 'bg-red-500 dark:bg-red-400' : 'bg-amber-500 dark:bg-amber-400 animate-pulse';
  const text = `${label}${reason ? `: ${reason}` : ''}`;
  return <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${color}`}
    style={{ animationDelay: syncedDelay }} role="status" aria-label={text} title={text} />;
}

// Same "current/max" shape as the Servers page row and the Live Status drawer.
function PlayerCount({ status }) {
  if (!status) return <span className="flex-none text-xs text-theme-muted">—</span>;
  return (
    <span className="flex-none font-mono text-xs tabular-nums text-theme-muted">
      {status.players?.length ?? 0}/{status.maxplayers ?? '?'}
    </span>
  );
}

function InstanceRow({ hostLabel, instance, selectedKeys, setTargetChecked, runtimeStates, serverStatuses }) {
  const runtime = runtimeValue(runtimeStates, instance.key);
  return (
    <li className="flex min-w-0 items-start gap-2 py-1.5 pl-14 pr-2 hover:bg-theme-elevated/50">
      <input type="checkbox" aria-label={`Select ${instance.label} on ${hostLabel}`} checked={selectedKeys.has(instance.key)}
        disabled={!instance.eligible} onChange={(event) => setTargetChecked(instance.key, event.target.checked)}
        className="mt-0.5 h-4 w-4 flex-none rounded border-theme accent-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-50" />
      <SquareChevronRight size={15} className="mt-0.5 flex-none text-sky-500 dark:text-sky-400" aria-hidden="true" />
      <RuntimeDot value={runtime} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-theme-primary" title={instance.label}>{instance.label}</span>
        {!instance.eligible && <span className="block truncate text-xs text-theme-muted">{instance.reason}</span>}
      </span>
      <PlayerCount status={serverStatuses[String(instance.id)]} />
    </li>
  );
}

function HostRow({ host, expanded, selectedKeys, runtimeStates, serverStatuses, setHostChecked, setTargetChecked, toggleHostExpanded }) {
  const eligibleKeys = new Set(host.instances.filter((item) => item.eligible).map((item) => item.key));
  const state = selectionState(eligibleKeys, selectedKeys);
  return (
    <li className="border-t border-theme first:border-t-0">
      <div className="flex items-center gap-1.5 py-1.5 pl-2 pr-2 hover:bg-theme-elevated/60">
        <button type="button" aria-label={`${expanded ? 'Collapse' : 'Expand'} ${host.label}`}
          onClick={() => toggleHostExpanded(host.id)}
          className="flex h-5 w-5 flex-none items-center justify-center rounded text-theme-secondary hover:bg-black/10 dark:hover:bg-white/10">
          <ChevronRight size={14} className={`transition-transform duration-150 ${expanded ? 'rotate-90' : ''}`} aria-hidden="true" />
        </button>
        <TriStateCheckbox label={`Select ${host.label}`} state={state} disabled={!eligibleKeys.size}
          onChange={(checked) => setHostChecked(eligibleKeys, checked)} />
        <Server size={16} className="flex-none text-amber-500 dark:text-amber-400" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-theme-primary">{host.label}</span>
        <span className="flex-none text-xs text-theme-muted">{eligibleKeys.size} available</span>
      </div>
      {/* Always mounted, revealed via max-height so expand/collapse animates
          instead of snapping — same technique as .server-card .instances-section
          on the Servers page. */}
      <div className={`overflow-hidden transition-[max-height] ${expanded
        ? 'max-h-[800px] duration-[450ms] ease-in' : 'max-h-0 duration-300 ease-out'}`}>
        {host.instances.length ? (
          <ul>{host.instances.map((instance) => <InstanceRow key={instance.key} hostLabel={host.label} instance={instance}
            selectedKeys={selectedKeys} runtimeStates={runtimeStates} serverStatuses={serverStatuses}
            setTargetChecked={setTargetChecked} />)}</ul>
        ) : <p className="py-1.5 pl-14 pr-2 text-xs text-theme-muted">No instances</p>}
      </div>
    </li>
  );
}

function filterHosts(hosts, term) {
  if (!term) return hosts;
  return hosts.reduce((acc, host) => {
    const hostMatches = host.label.toLowerCase().includes(term);
    const instances = hostMatches ? host.instances
      : host.instances.filter((instance) => instance.label.toLowerCase().includes(term));
    if (hostMatches || instances.length) acc.push({ ...host, instances });
    return acc;
  }, []);
}

export default function RconTargetTree({
  hosts = [], selectedKeys = new Set(), expandedHostIds = new Set(), runtimeStates = new Map(), serverStatuses = {},
  setTargetChecked, setHostChecked, selectAllEligible, selectNone, toggleHostExpanded, setAllHostsExpanded,
}) {
  const [filterText, setFilterText] = useState('');
  const filteredHosts = useMemo(
    () => filterHosts(hosts, filterText.trim().toLowerCase()),
    [hosts, filterText],
  );
  const allExpanded = filteredHosts.length > 0 && filteredHosts.every((host) => expandedHostIds.has(host.id));

  return (
    <section aria-label="RCON targets" className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" aria-hidden="true" />
        <input type="text" aria-label="Filter servers" placeholder="Filter servers..." value={filterText}
          onChange={(event) => setFilterText(event.target.value)}
          className="w-full rounded border border-[var(--surface-border)] bg-[var(--surface-elevated)] py-1.5 pl-8 pr-3 text-sm text-[var(--text-secondary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--surface-border-strong)]" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={selectAllEligible}
          className="flex items-center justify-center gap-1 rounded bg-[var(--surface-elevated)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]/80">
          <SquareCheck className="h-3.5 w-3.5" aria-hidden="true" /> Select All
        </button>
        <button type="button" onClick={selectNone}
          className="flex items-center justify-center gap-1 rounded bg-[var(--surface-elevated)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]/80">
          <Square className="h-3.5 w-3.5" aria-hidden="true" /> Select None
        </button>
      </div>
      <button type="button" onClick={() => setAllHostsExpanded(!allExpanded)}
        aria-label={allExpanded ? 'Collapse all hosts' : 'Expand all hosts'}
        className="flex w-full items-center justify-center gap-1 rounded bg-[var(--surface-elevated)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]/80">
        {allExpanded ? <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
        {allExpanded ? 'Collapse All' : 'Expand All'}
      </button>
      <ul className="overflow-hidden rounded border border-theme bg-theme-base">{filteredHosts.map((host) => <HostRow key={host.id} host={host}
        expanded={expandedHostIds.has(host.id)} selectedKeys={selectedKeys} runtimeStates={runtimeStates} serverStatuses={serverStatuses}
        setHostChecked={setHostChecked} setTargetChecked={setTargetChecked} toggleHostExpanded={toggleHostExpanded} />)}</ul>
      {!hosts.length && <p className="py-4 text-center text-sm text-theme-muted">No hosts</p>}
      {!!hosts.length && !filteredHosts.length && <p className="py-4 text-center text-sm text-theme-muted">No servers match &quot;{filterText.trim()}&quot;</p>}
    </section>
  );
}
