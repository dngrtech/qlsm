import { useEffect, useId, useRef, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { FilePlus, FolderPlus, X } from 'lucide-react';

function getExtension(name) {
  const dotIndex = name.lastIndexOf('.');
  return dotIndex === -1 ? '' : name.slice(dotIndex).toLowerCase();
}

const FOLDER_NAME_RE = /^[A-Za-z0-9._-]+$/;

export default function NewFileModal({
  isOpen,
  onClose,
  onCreate,
  mode = 'file',
  allowedExtensions = [],
  existingNames = [],
  reservedNames = [],
}) {
  const [name, setName] = useState('');
  const [error, setError] = useState(null);
  const inputId = useId();
  const nameInputRef = useRef(null);
  const isFolder = mode === 'folder';

  useEffect(() => {
    if (isOpen) {
      setName('');
      setError(null);
    }
  }, [isOpen]);

  const handleCreate = () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Name is required');
      return;
    }
    if (trimmed.includes('/') || trimmed.includes('\\') || trimmed.includes('..')) {
      setError('Invalid name');
      return;
    }
    if (isFolder) {
      if (!FOLDER_NAME_RE.test(trimmed)) {
        setError('Letters, numbers, dot, dash, underscore only');
        return;
      }
      if (trimmed.length > 64) {
        setError('Folder name too long (max 64)');
        return;
      }
      if (reservedNames.map(n => n.toLowerCase()).includes(trimmed.toLowerCase())) {
        setError(`Reserved folder name: ${trimmed}`);
        return;
      }
    } else {
      const ext = getExtension(trimmed);
      if (!allowedExtensions.includes(ext)) {
        setError(`Allowed extensions: ${allowedExtensions.join(', ')}`);
        return;
      }
    }
    if (existingNames.includes(trimmed)) {
      setError(isFolder ? 'Folder already exists' : 'File already exists');
      return;
    }
    onCreate(trimmed);
  };

  const title = isFolder ? 'New Folder' : 'New File';
  const label = isFolder ? 'Folder Name' : 'Filename';
  const placeholder = isFolder ? 'custom_entities' : `example${allowedExtensions[0] || ''}`;
  const Icon = isFolder ? FolderPlus : FilePlus;

  return (
    <Dialog open={isOpen} as="div" className="relative z-[60]" onClose={onClose} initialFocus={nameInputRef}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0" />
        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
              <Dialog.Panel transition className="modal-panel w-full max-w-md p-6 transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0 data-[closed]:scale-95">
                <Dialog.Title className="text-lg font-display font-semibold uppercase tracking-wider text-[var(--text-primary)] mb-4 flex items-center justify-between">
                  {title}
                  <button type="button" onClick={onClose} className="logs-modal-close-btn">
                    <X size={16} />
                  </button>
                </Dialog.Title>
                <div className="space-y-3">
                  <div>
                    <label htmlFor={inputId} className="label-tech mb-1.5 block">{label}</label>
                    <input
                      ref={nameInputRef}
                      id={inputId}
                      type="text"
                      value={name}
                      onChange={(e) => {
                        setName(e.target.value);
                        setError(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleCreate();
                      }}
                      placeholder={placeholder}
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
                  <button type="button" onClick={handleCreate} className="btn btn-primary">
                    <Icon className="w-4 h-4 mr-1" />
                    Create
                  </button>
                </div>
              </Dialog.Panel>
          </div>
        </div>
    </Dialog>
  );
}
