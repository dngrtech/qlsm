import React, { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { FolderOpen } from 'lucide-react';
import CompatibilityRow from './CompatibilityRow';
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
              enabled/disabled state this preset saved. Listed below is only what that leaves:
              files whose copy in this preset can&apos;t run on {targetRuntime} and isn&apos;t the
              standard one, so QLSM won&apos;t decide for you. Whatever you choose here, plugins are
              enabled exactly as this preset had them — nothing is switched on that wasn&apos;t.
            </p>

            <ul className="mt-4 max-h-64 space-y-2 overflow-y-auto pr-1 scrollbar-thin">
              {stripped.map((entry) => (
                <CompatibilityRow
                  key={entry.path}
                  entry={entry}
                  sourceRuntime={presetRuntime}
                  targetRuntime={targetRuntime}
                  checked={acceptedPaths.has(entry.path)}
                  onToggle={() => toggleAccepted(entry.path)}
                />
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
