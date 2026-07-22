import { useMemo, useState } from 'react';

function targetKey(target) {
  if (typeof target === 'string') return target;
  if (typeof target?.key === 'string' && target.key) return target.key;
  if (target?.host_id != null && target?.instance_id != null) {
    return `${target.host_id}:${target.instance_id}`;
  }
  return null;
}

function targetName(target, key) {
  for (const value of [target?.name, target?.display_name, target?.label]) {
    if (typeof value === 'string' && value.trim()) return value;
  }
  return key;
}

// Exported for deterministic union tests; this module otherwise renders the filter component.
// eslint-disable-next-line react-refresh/only-export-components
export function deriveRconOutputTargets({
  selectedTargets = [], runs = [], rawStreams = new Map(),
} = {}) {
  const targets = new Map();
  const add = (candidate) => {
    const key = targetKey(candidate);
    if (!key || targets.has(key)) return;
    targets.set(key, { ...(typeof candidate === 'object' ? candidate : {}), key, name: targetName(candidate, key) });
  };

  for (const target of Array.isArray(selectedTargets) ? selectedTargets : []) add(target);
  for (const run of Array.isArray(runs) ? runs : []) {
    for (const result of Array.isArray(run?.results) ? run.results : []) add(result);
  }
  const rawKeys = rawStreams instanceof Map ? rawStreams.keys() : Object.keys(rawStreams ?? {});
  for (const key of rawKeys) add(key);
  return [...targets.values()];
}

function Tab({ tabKey, label, activeFilter, onFilterChange }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={activeFilter === tabKey}
      onClick={() => onFilterChange(tabKey)}
      className={`rounded-md px-3 py-1.5 text-sm ${activeFilter === tabKey
        ? 'bg-[var(--accent-primary)] text-white'
        : 'text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5'}`}
    >
      {label}
    </button>
  );
}

export default function RconOutputFilters({
  activeFilter,
  onFilterChange,
  selectedTargets = [],
  runs = [],
  rawStreams = new Map(),
  directLimit = 8,
  // Alternate prop spellings accepted so this stays drop-in for callers that
  // pass a precomputed target list or the shorter handler names.
  activeKey,
  onChange,
  targets,
}) {
  const active = activeFilter ?? activeKey ?? 'all';
  const change = onFilterChange ?? onChange ?? (() => {});
  const union = useMemo(() => targets ?? deriveRconOutputTargets({
    selectedTargets, runs, rawStreams,
  }), [rawStreams, runs, selectedTargets, targets]);
  const limit = Math.max(0, Math.floor(Number.isFinite(directLimit) ? directLimit : 8));
  const direct = union.slice(0, limit);
  const activeTarget = union.find((target) => target.key === active);
  if (activeTarget && limit > 0 && !direct.some((target) => target.key === active)) {
    direct[Math.min(limit, direct.length) - 1] = activeTarget;
  }
  const directKeys = new Set(direct.map((target) => target.key));
  const overflow = union.filter((target) => !directKeys.has(target.key));
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const needle = query.trim().toLocaleLowerCase();
  const matches = overflow.filter((target) => !needle
    || target.name.toLocaleLowerCase().includes(needle)
    || target.key.toLocaleLowerCase().includes(needle));
  const activateOverflow = (key) => {
    change(key);
    setOpen(false);
    setQuery('');
  };

  return (
    <div className="relative">
      <div role="tablist" aria-label="RCON output filters" className="flex flex-wrap gap-1">
        <Tab tabKey="all" label="ALL" activeFilter={active} onFilterChange={change} />
        {direct.map((target) => (
          <Tab key={target.key} tabKey={target.key} label={target.name}
            activeFilter={active} onFilterChange={change} />
        ))}
        {overflow.length > 0 && (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
            className="rounded-md px-3 py-1.5 text-sm text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5"
          >
            + {overflow.length} more targets
          </button>
        )}
      </div>
      {open && (
        <div
          role="dialog"
          aria-label="More RCON output targets"
          className="absolute z-20 mt-2 w-72 rounded-md border border-theme bg-theme-base p-2 shadow-lg"
        >
          <input
            type="search"
            aria-label="Search targets"
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="mb-2 w-full rounded border border-theme bg-theme-elevated px-2 py-1 text-sm"
          />
          <div className="max-h-64 space-y-1 overflow-y-auto">
            {matches.map((target) => (
              <button
                type="button"
                key={target.key}
                onClick={() => activateOverflow(target.key)}
                className="block w-full rounded px-2 py-1 text-left text-sm text-theme-primary hover:bg-black/5 dark:hover:bg-white/5"
              >
                {target.name}
              </button>
            ))}
            {!matches.length && <p className="px-2 py-3 text-sm text-theme-muted">No matching targets.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
