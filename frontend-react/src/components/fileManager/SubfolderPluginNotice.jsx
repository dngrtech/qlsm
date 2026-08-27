import { AlertTriangle, X } from 'lucide-react';

/**
 * Shown when loading an instance or preset that had plugins ticked which can't
 * actually be enabled (subfolder files, __init__.py, abstract base modules like
 * iouonegirl.py). Those entries are dropped from the checked set; this explains
 * why so the change isn't silent.
 *
 * @param {number}   count     - How many entries were dropped. 0 renders nothing.
 * @param {Function} onDismiss - Clears the notice. Parent owns the state.
 */
function SubfolderPluginNotice({ count, onDismiss }) {
  if (!count) return null;

  const noun = count === 1 ? 'plugin' : 'plugins';
  const verb = count === 1 ? 'was' : 'were';

  return (
    <div role="status" className="alert-warning mb-3 flex items-start gap-2 text-sm">
      <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: 'var(--accent-warning)' }} />
      <span className="flex-1 min-w-0 text-[var(--text-secondary)]">
        {`${count} ${noun} that can't be enabled ${verb} deselected. `}
        These files are libraries referenced by plugins in the root folder, not plugins enabled on their own.
      </span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="flex-shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

export default SubfolderPluginNotice;
