import { AlertTriangle, CircleAlert } from 'lucide-react';

// Errors first -- those are the findings that make plugin or addon data
// disappear the next time qlsm fetches this file.
const bySeverity = (a, b) => {
  if (a.severity === b.severity) return 0;
  return a.severity === 'error' ? -1 : 1;
};

/**
 * The validator's own messages, listed under the editor.
 *
 * The per-row dots and the footer counts can't stand in for this: a dot says
 * only that something is wrong, while the message says what qlsm will do
 * with the entry -- which is the part the operator needs before committing
 * the export over the repository's real file. An issue that carries no
 * `index` belongs to no single row and can't be drawn as a dot at all, so
 * this list is the only place it can appear.
 */
function PluginManifestIssues({ issues, onSelect }) {
  if (!issues.length) return null;

  return (
    <div className="relative z-10 mt-3 flex-shrink-0 border border-[var(--surface-border)] rounded-lg max-h-28 overflow-y-auto scrollbar-thin">
      <ul className="divide-y divide-[var(--surface-border)]">
        {[...issues].sort(bySeverity).map((iss, i) => {
          const isError = iss.severity === 'error';
          const Icon = isError ? AlertTriangle : CircleAlert;
          const body = (
            <>
              <Icon
                size={13}
                className={`flex-shrink-0 mt-0.5 ${isError ? 'text-red-500 dark:text-[#FF3366]' : 'text-amber-500'}`}
              />
              <span className="min-w-0 flex-1">{iss.message}</span>
            </>
          );

          return (
            // Index keys are fine here: the list is rebuilt from scratch on
            // every draft change and holds no state of its own.
            <li key={i} className="text-xs text-[var(--text-secondary)]">
              {iss.index === undefined ? (
                <span className="flex items-start gap-2 px-3 py-1.5">{body}</span>
              ) : (
                <button
                  type="button"
                  onClick={() => onSelect(iss)}
                  className="w-full flex items-start gap-2 px-3 py-1.5 text-left hover:bg-black/[0.03] dark:hover:bg-white/[0.03]"
                >
                  {body}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default PluginManifestIssues;
