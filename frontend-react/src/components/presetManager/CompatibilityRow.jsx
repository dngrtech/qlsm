import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

// One stripped-file row of the compat gate, shared by the preset-load dialog
// and the host runtime-upgrade dialog. `sourceNoun` is what the file came from
// ("preset" or "instance"), so the copy reads right in both places.
//
// Ticking a row means "take the target runtime's file". It does NOT mean
// "enable this plugin".
//
// `showEnablement` marks rows for plugins the source does not have enabled and
// tones them down: their loss cannot break anything that runs today. Only the
// runtime-upgrade dialog passes it. There `originally_checked` is exact (an
// instance with no qlx_plugins loads no user plugins). A legacy preset with no
// checked_plugins.json reports every row as not checked, so the preset dialog
// would mislabel all of them.

function CompatibilityRow({
  entry, sourceRuntime, targetRuntime, checked, onToggle, sourceNoun = 'preset', showEnablement = false,
}) {
  const replaceable = Boolean(entry.replacement) || entry.kind === 'replaceable';
  const reasons = entry.reasons || [];
  const notEnabled = showEnablement && !entry.originally_checked;
  const muted = entry.auto_replaced || notEnabled;
  const detailTone = notEnabled ? 'text-theme-secondary' : 'text-[var(--accent-warning)]';

  return (
    <li
      className={
        muted
          ? 'rounded-md border border-theme/60 bg-theme-secondary/40 px-3 py-2.5 text-xs'
          : 'rounded-md border border-[var(--accent-warning)]/35 bg-[var(--accent-warning)]/8 px-3 py-2.5 text-xs'
      }
    >
      <div className="flex items-start gap-2">
        {/* An auto-replaced helper is not a loss, and must not be dressed as
            one: the file is swapped for the target runtime's own copy of the
            same path, with no decision for the operator to make. Showing it
            under a warning triangle alongside genuinely unrecoverable files
            is what made the two look identical. */}
        {entry.auto_replaced ? (
          <RefreshCw className="mt-0.5 h-4 w-4 flex-shrink-0 text-theme-secondary" />
        ) : (
          <AlertTriangle className={`mt-0.5 h-4 w-4 flex-shrink-0 ${detailTone}`} />
        )}
        <div className="min-w-0 flex-1 text-left">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-theme-primary">{entry.path}</span>
            {notEnabled && (
              <span className="rounded border border-theme px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-theme-secondary">
                Not enabled
              </span>
            )}
          </div>
          {/* Why this file is here at all, in the operator's terms.
              `from_catalog` is the difference between "a standard plugin whose
              copy here differs" and "a plugin of your own". Deliberately does
              NOT say the operator modified anything: an older copy of QLSM's
              own file hashes exactly like an edit and is not one. */}
          <p className="mt-1 text-theme-secondary">
            {entry.from_catalog
              ? `A standard ${sourceRuntime} plugin, but this ${sourceNoun}'s copy differs `
                + 'from the standard one — either edited, or saved before the plugin '
                + 'was last updated.'
              : `Not a standard ${sourceRuntime} plugin — this one was added to the ${sourceNoun}.`}
            {entry.kind === 'unavailable'
              && ` ${targetRuntime} has no version of it, so it won't be installed`
                 + `${entry.originally_checked ? ' and will be switched off' : ''}.`}
            {entry.kind === 'replaceable' && !entry.from_catalog
              && ` ${targetRuntime} ships a plugin under this same name.`}
          </p>
          {entry.auto_replaced ? (
            <p className="mt-1 text-theme-secondary">
              Helper module. Replaced automatically with {targetRuntime}&apos;s own
              version of this file &mdash; nothing to choose, but any changes this
              {' '}{sourceNoun} made to it are not carried over.
            </p>
          ) : entry.verdict === 'unknown' ? (
            <p className={`mt-1 ${detailTone}`}>
              Not part of the {targetRuntime} baseline; QLSM can&apos;t confirm this plugin will run.
            </p>
          ) : (
            <ul className={`mt-1 space-y-0.5 ${detailTone}`}>
              {reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
          {replaceable && (
            <label className="mt-2 flex items-start gap-2 text-theme-primary">
              <input
                type="checkbox"
                className="mt-0.5"
                aria-label={`Use the ${targetRuntime} version of ${entry.path} instead`}
                checked={checked}
                onChange={onToggle}
              />
              <span>
                Use {targetRuntime}&apos;s own {entry.path} instead &mdash; this
                {' '}{sourceNoun}&apos;s version of the file is not carried over. Untick and the
                plugin is dropped entirely.
              </span>
            </label>
          )}
        </div>
      </div>
    </li>
  );
}

export default CompatibilityRow;
