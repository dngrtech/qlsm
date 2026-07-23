import { useMemo } from 'react';

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
// Tabs mirror the current tree selection only — a target that scrolls out of
// selection (unchecked in the Targets tree) drops out here too, even if its
// output is still visible under "ALL" or was retained in a raw stream.
// eslint-disable-next-line react-refresh/only-export-components
export function deriveRconOutputTargets({ selectedTargets = [] } = {}) {
  const targets = new Map();
  for (const target of Array.isArray(selectedTargets) ? selectedTargets : []) {
    const key = targetKey(target);
    if (!key || targets.has(key)) continue;
    targets.set(key, { ...(typeof target === 'object' ? target : {}), key, name: targetName(target, key) });
  }
  return [...targets.values()];
}

// Same tab treatment as the Configuration Files / Plugins / Factories / Hooks
// strip in EditInstanceConfigModal: bottom-border underline + tint on the
// active tab only; inactive tabs stay transparent so just the selected one
// shows the accent line.
const TAB_CLASSES = 'border-b-2 border-r border-r-[var(--surface-border)] px-4 py-2.5 text-[12px] font-display font-semibold uppercase tracking-wide transition-all duration-200';

function Tab({ tabKey, label, activeFilter, onFilterChange }) {
  const active = activeFilter === tabKey;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => onFilterChange(tabKey)}
      className={`${TAB_CLASSES} ${active
        ? 'border-b-[var(--accent-primary)] bg-[var(--accent-primary)]/5 text-[var(--accent-primary)]'
        : 'border-b-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-base)]/50 hover:text-[var(--text-primary)]'}`}
    >
      {label}
    </button>
  );
}

export default function RconOutputFilters({
  activeFilter,
  onFilterChange,
  selectedTargets = [],
  // Alternate prop spellings accepted so this stays drop-in for callers that
  // pass a precomputed target list or the shorter handler names.
  activeKey,
  onChange,
  targets,
}) {
  const active = activeFilter ?? activeKey ?? 'all';
  const change = onFilterChange ?? onChange ?? (() => {});
  const union = useMemo(() => targets ?? deriveRconOutputTargets({ selectedTargets }),
    [selectedTargets, targets]);

  return (
    // overflow-hidden clips each tab's square corners against the rounded frame.
    <div className="overflow-hidden rounded-t-xl border border-[var(--surface-border)] bg-[var(--surface-elevated)]">
      <div role="tablist" aria-label="RCON output filters" className="flex flex-wrap">
        <Tab tabKey="all" label="ALL" activeFilter={active} onFilterChange={change} />
        {union.map((target) => (
          <Tab key={target.key} tabKey={target.key} label={target.name}
            activeFilter={active} onFilterChange={change} />
        ))}
      </div>
    </div>
  );
}
