import React, { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { AlertTriangle, FolderOpen } from 'lucide-react';
import { runtimeLabel } from '../../constants/runtimes';
import { strippedWithReplacements } from '../../utils/presetCompatibility';

// The operator-facing half of the compat gate: the backend has already
// decided what gets stripped and what can be swapped in instead; this dialog
// just shows the list and lets the operator opt out of individual
// replacements before the load actually happens.

function PresetCompatibilityDialog({ isOpen, compatibility, onCancel, onConfirm }) {
  const stripped = compatibility?.stripped || [];
  const replaceablePaths = useMemo(
    () => strippedWithReplacements({ compatibility }).map((entry) => entry.path),
    [compatibility]
  );
  const [acceptedPaths, setAcceptedPaths] = useState(() => new Set(replaceablePaths));

  useEffect(() => {
    if (isOpen) setAcceptedPaths(new Set(replaceablePaths));
    // Only reset when the dialog (re)opens -- not on every replaceablePaths
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
            {/* The list below is what this preset LOSES. It is not the whole
                story of what the instance ends up with: a cross-runtime load
                seeds the target runtime's own default plugins first and lays
                the preset over them, so the operator will meet plugins that
                this preset never contained. Saying only "these won't be
                installed" would leave them to discover that on the next
                screen. */}
            <p className="mt-2 text-sm text-theme-secondary">
              This preset was saved from a {presetRuntime} host. The rest of the config loads as-is,
              but the plugins below won&apos;t be installed on this instance. Each one either uses
              an API that {targetRuntime} doesn&apos;t have, or can&apos;t be confirmed to run
              there — the reason is shown for each. The instance still starts from
              {' '}{targetRuntime}&apos;s own standard plugins, so the plugin list you end up with
              is not simply this preset&apos;s minus what is listed here.
            </p>

            <ul className="mt-4 max-h-64 space-y-2 overflow-y-auto pr-1 scrollbar-thin">
              {stripped.map((entry) => (
                <li
                  key={entry.path}
                  className="rounded-md border border-[var(--accent-warning)]/35 bg-[var(--accent-warning)]/8 px-3 py-2.5 text-xs"
                >
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--accent-warning)]" />
                    <div className="min-w-0 flex-1 text-left">
                      <div className="text-sm font-semibold text-theme-primary">{entry.path}</div>
                      {entry.verdict === 'unknown' ? (
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
                        <label className="mt-2 flex items-center gap-2 text-theme-primary">
                          <input
                            type="checkbox"
                            checked={acceptedPaths.has(entry.path)}
                            onChange={() => toggleAccepted(entry.path)}
                          />
                          <span>Use the {targetRuntime} replacement instead</span>
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
