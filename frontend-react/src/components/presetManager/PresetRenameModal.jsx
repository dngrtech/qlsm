import { useEffect, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { LoaderCircle, Pencil, X } from 'lucide-react';

export default function PresetRenameModal({
  isOpen,
  onClose,
  onRename,
  currentName,
  existingNames = [],
  isSaving = false,
  error = null,
}) {
  const [name, setName] = useState(currentName || '');
  const [localError, setLocalError] = useState(null);

  useEffect(() => {
    if (isOpen) {
      setName(currentName || '');
      setLocalError(null);
    }
  }, [isOpen, currentName]);

  const handleRename = () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setLocalError('Name is required');
      return;
    }
    if (trimmed === currentName) {
      onClose();
      return;
    }
    if (existingNames.filter((n) => n !== currentName).includes(trimmed)) {
      setLocalError('A preset with this name already exists');
      return;
    }
    onRename(trimmed);
  };

  return (
    <Dialog open={isOpen} as="div" className="relative z-[70]" onClose={onClose}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4">
          <Dialog.Panel transition className="modal-panel w-full max-w-md p-6 transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0 data-[closed]:scale-95">
            <Dialog.Title className="text-lg font-display font-semibold uppercase tracking-wider text-[var(--text-primary)] mb-4 flex items-center justify-between">
              Rename Preset
              <button type="button" onClick={onClose} className="logs-modal-close-btn">
                <X size={16} />
              </button>
            </Dialog.Title>
            <div className="space-y-3">
              <div>
                <label className="label-tech mb-1.5 block">New name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setLocalError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !isSaving) handleRename();
                  }}
                  autoFocus
                  className="input-base"
                />
              </div>
              {(localError || error) && (
                <p className="text-sm text-[var(--accent-danger)]">{localError || error}</p>
              )}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={onClose} className="btn btn-secondary">
                <X className="w-4 h-4 mr-1" />
                Cancel
              </button>
              <button type="button" onClick={handleRename} disabled={isSaving} className="btn btn-primary">
                {isSaving
                  ? <><LoaderCircle className="w-4 h-4 mr-1 animate-spin" />Renaming...</>
                  : <><Pencil className="w-4 h-4 mr-1" />Rename</>}
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}
