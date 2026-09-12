import React from 'react';
import { UserPlus, X } from 'lucide-react';

const STATE_LABELS = {
  managed: 'Managed',
  // The live level is unknown (unreachable host, nothing deployed): say nothing
  // rather than assert a state the app cannot know. No-badge is this state's
  // unique signature -- 'managed' must always show something, or the two
  // become indistinguishable again.
  unknown: null,
  pending: 'Not applied yet',
  'live-only': 'Set in-game',
  // In the managed-admins set with no stored row, so the next save resets it to 0.
  'will-be-revoked': 'Will be revoked on save',
};

// Rows the server has but QLSM does not store. Remove would filter the stored
// list, which these are not in, so the button is left off: adopt, then remove.
const SERVER_ONLY_STATES = new Set(['live-only', 'will-be-revoked']);

// One admin in the Owner & Admins list. `row` comes from useInstanceAdmins:
// {steamId, level, state}. The directory only supplies a display name -- a
// SteamID missing from it is shown as itself, never as "Unknown operator".
//
// The row carries a data-testid of `admin-row-<steamId>` so a sibling test can
// target it directly instead of matching text fragmented across the name and
// SteamID spans (e.g. `getByTestId('admin-row-76561198012345678')`).
function AdminRow({ row, operator, onRemove, onAdopt, onAddToDirectory }) {
  const stateLabel = STATE_LABELS[row.state];
  const serverOnly = SERVER_ONLY_STATES.has(row.state);
  return (
    <li
      data-testid={`admin-row-${row.steamId}`}
      className="flex items-center justify-between gap-2 rounded-md bg-[var(--surface-base)] px-2.5 py-1.5 text-sm"
    >
      <span className="min-w-0 truncate text-[var(--text-primary)]">
        {/* The name gets its own span so getByText('Vex') can match it -- as a
            bare text node it normalizes to "Vex76561198012345678lvl 3". */}
        {operator ? <span>{operator.name}</span> : <span className="font-mono">{row.steamId}</span>}
        {operator && <span className="ml-2 font-mono text-xs text-[var(--text-muted)]">{row.steamId}</span>}
        <span className="ml-2 text-xs text-[var(--text-muted)]">lvl {row.level}</span>
        {stateLabel && (
          <span className="ml-2 rounded bg-[var(--surface-elevated)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
            {stateLabel}
          </span>
        )}
      </span>
      <span className="flex flex-shrink-0 items-center gap-2">
        {!operator && onAddToDirectory && (
          <button type="button" onClick={() => onAddToDirectory(row.steamId)}
                  className="flex items-center gap-1 text-xs text-[var(--accent-primary)] hover:underline">
            <UserPlus size={12} /> Add to operators
          </button>
        )}
        {serverOnly && onAdopt && (
          <button type="button" onClick={() => onAdopt(row.steamId)}
                  className="text-xs text-[var(--accent-primary)] hover:underline">
            Adopt
          </button>
        )}
        {!serverOnly && onRemove && (
          <button type="button" onClick={() => onRemove(row.steamId)} title="Remove admin"
                  aria-label="Remove admin"
                  className="text-[var(--text-muted)] hover:text-[var(--accent-danger)]">
            <X size={14} />
          </button>
        )}
      </span>
    </li>
  );
}

export default AdminRow;
