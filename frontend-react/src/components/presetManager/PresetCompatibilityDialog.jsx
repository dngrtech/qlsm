import React, { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { AlertTriangle, FolderOpen, RefreshCw } from 'lucide-react';
import { runtimeLabel } from '../../constants/runtimes';
import { strippedWithReplacements } from '../../utils/presetCompatibility';

// The operator-facing half of the compat gate. The backend has already swapped
// every untouched stock plugin for the target runtime's own copy without asking
// -- those never appear here. What is listed is only what is genuinely at
// stake: files this preset customised, and files the target has no version of.
//
// Ticking a row means "take the target runtime's file". It does NOT mean
// "enable this plugin" -- the preset's own selection decides that.

function PresetCompatibilityDialog({ isOpen, compatibility, onCancel, onConfirm }) {
  const stripped = compatibility?.stripped || [];
  // Replacing a customised file loses the edits, but declining loses the file
  // outright -- the preset's copy cannot run on the target either way. Taking
  // the working version is the better default, and it is safe to default now
  // that a tick no longer switches the plugin on.
  const defaultAcceptedPaths = useMemo(
    () => strippedWithReplacements({ compatibility }).map((entry) => entry.path),
    [compatibility]
  );
  const [acceptedPaths, setAcceptedPaths] = useState(() => new Set(defaultAcceptedPaths));

  useEffect(() => {
    if (isOpen) setAcceptedPaths(new Set(defaultAcceptedPaths));
    // Only reset when the dialog (re)opens -- not on every defaultAcceptedPaths
    // identity change, so a mid-session tick/untick isn't clobbered.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!compatibility) return null;

  const targetRuntime = runtimeLabel(compatibility.target_runtime);
  const presetRuntime = runtimeLabel(compatibility.preset_runtime);

  const toggleAccepted = (path) => {
    setAcceptedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const handleConfirm = () => {
    const accepted = stripped
      .filter((entry) => entry.replacement && acceptedPaths.has(entry.path))
      .map((entry) => entry.path);
    onConfirm(accepted);
  };

  return (
    <Dialog open={isOpen} as="div" className="relative z-[70]" onClose={onCancel}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4 text-center">
          <Dialog.Panel transition className="modal-panel w-full max-w-lg transform overflow-hidden p-6 text-left align-middle transition-all data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
            <div className="accent-line-top" />

            <Dialog.Title as="h3" className="font-display text-lg font-semibold tracking-wide text-theme-primary">
              Some plugins won&apos;t carry over
            </Dialog.Title>
            {/* Only actionable strips reach this list. Every standard plugin
                the preset carried unmodified has already been swapped for
                {targetRuntime}'s own copy of the same file, silently, keeping
                whatever enabled/disabled state the preset recorded for it --
                so this list is short by design. */}
            <p className="mt-2 text-sm text-theme-secondary">
              This preset was saved from a {presetRuntime} host. Its config, and every standard
              plugin it carried unmodified, load as usual — those are swapped for
              {' '}{targetRuntime}&apos;s own version of the same plugin automatically, and keep the
              enabled/disabled state this preset saved. Only the files below need your decision,
              because this preset&apos;s own copy of each one can&apos;t run on {targetRuntime}.
              Whatever you choose here, plugins are enabled exactly as this preset had them —
              nothing is switched on that wasn&apos;t.
            </p>

            <ul className="mt-4 max-h-64 space-y-2 overflow-y-auto pr-1 scrollbar-thin">
              {stripped.map((entry) => (
                <li
                  key={entry.path}
                  className={
                    entry.auto_replaced
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
                      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--accent-warning)]" />
                    )}
                    <div className="min-w-0 flex-1 text-left">
                      <div className="text-sm font-semibold text-theme-primary">{entry.path}</div>
                      {/* Why this file is here at all, in the operator's terms.
                          `from_catalog` is the difference between "you edited a
                          standard plugin" and "this is a plugin of your own" --
                          the same strip, but not the same news. Only the lead-in
                          differs: for a plugin of the operator's own we cannot
                          claim their file is a modified version of the target's,
                          so nothing here says "modified" or "your changes". */}
                      <p className="mt-1 text-theme-secondary">
                        {entry.from_catalog
                          ? `A standard ${presetRuntime} plugin that this preset modified.`
                          : `Not a standard ${presetRuntime} plugin — this one was added to the preset.`}
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
                          preset made to it are not carried over.
                        </p>
                      ) : entry.verdict === 'unknown' ? (
                        <p className="mt-1 text-[var(--accent-warning)]">
                          Not part of the {targetRuntime} baseline; QLSM can&apos;t confirm this plugin will run.
                        </p>
                      ) : (
                        <ul className="mt-1 space-y-0.5 text-[var(--accent-warning)]">
                          {entry.reasons.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      )}
                      {entry.replacement && (
                        <label className="mt-2 flex items-start gap-2 text-theme-primary">
                          <input
                            type="checkbox"
                            className="mt-0.5"
                            aria-label={`Use the ${targetRuntime} version of ${entry.path} instead`}
                            checked={acceptedPaths.has(entry.path)}
                            onChange={() => toggleAccepted(entry.path)}
                          />
                          {/* "this preset's version is not carried over" holds for
                              both a modified standard plugin and a plugin of the
                              operator's own. "your changes are lost" only held for
                              the first, and read as nonsense on the second. */}
                          <span>
                            Use {targetRuntime}&apos;s own {entry.path} instead &mdash; this
                            preset&apos;s version of the file is not carried over. Untick and the
                            plugin is dropped entirely.
                          </span>
                        </label>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>

            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="btn btn-secondary" onClick={onCancel}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary" onClick={handleConfirm}>
                <FolderOpen className="mr-1 h-4 w-4" />
                Load Preset
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}

export default PresetCompatibilityDialog;
