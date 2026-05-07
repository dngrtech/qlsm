import { useEffect, useState } from 'react';
import { Dialog } from '@headlessui/react';
import { Pencil, X } from 'lucide-react';

function getExtension(name) {
  const dotIndex = name.lastIndexOf('.');
  return dotIndex === -1 ? '' : name.slice(dotIndex).toLowerCase();
}

export default function RenameFileModal({
  isOpen,
  onClose,
  onRename,
  currentName,
  allowedExtensions,
  existingNames = [],
}) {
  const [name, setName] = useState(currentName || '');
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen) {
      setName(currentName || '');
      setError(null);
    }
  }, [isOpen, currentName]);

  const handleRename = () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Name is required');
      return;
    }
    if (trimmed === currentName) {
      onClose();
      return;
    }
    if (trimmed.includes('/') || trimmed.includes('\\') || trimmed.includes('..')) {
      setError('Invalid name');
      return;
    }
    const ext = getExtension(trimmed);
    if (!allowedExtensions.includes(ext)) {
      setError(`Allowed extensions: ${allowedExtensions.join(', ')}`);
      return;
    }
    if (existingNames.filter(existing => existing !== currentName).includes(trimmed)) {
      setError('File already exists');
      return;
    }
    onRename(trimmed);
  };

  return (
    <Dialog open={isOpen} as="div" className="relative z-[60]" onClose={onClose}>
      <Dialog.Backdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0" />
        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
              <Dialog.Panel transition className="modal-panel w-full max-w-md p-6 transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0 data-[closed]:scale-95">
                <Dialog.Title className="text-lg font-display font-semibold uppercase tracking-wider text-[var(--text-primary)] mb-4 flex items-center justify-between">
                  Rename File
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
                        setError(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRename();
                      }}
                      autoFocus
                      className="input-base"
                    />
                  </div>
                  {error && <p className="text-sm text-[var(--accent-danger)]">{error}</p>}
                </div>
                <div className="mt-5 flex justify-end gap-2">
                  <button type="button" onClick={onClose} className="btn btn-secondary">
                    <X className="w-4 h-4 mr-1" />
                    Cancel
                  </button>
                  <button type="button" onClick={handleRename} className="btn btn-primary">
                    <Pencil className="w-4 h-4 mr-1" />
                    Rename
                  </button>
                </div>
              </Dialog.Panel>
          </div>
        </div>
    </Dialog>
  );
}
