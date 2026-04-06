import React, { useState, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, FilePlus } from 'lucide-react';

/**
 * Modal for creating a new Python script file.
 */
function NewScriptModal({
  isOpen,
  onClose,
  onCreate,
  existingFolders = []
}) {
  const [filename, setFilename] = useState('');
  const [selectedFolder, setSelectedFolder] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    // Validate filename
    let name = filename.trim();
    if (!name) {
      setError('Filename is required');
      return;
    }

    // Add .py extension if no recognized extension present
    if (!name.endsWith('.py') && !name.endsWith('.txt')) {
      name = name + '.py';
    }

    // Check for invalid characters
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*\.(py|txt)$/.test(name)) {
      setError('Invalid filename. Use only letters, numbers, and underscores. Must end with .py or .txt.');
      return;
    }

    // Build full path
    const path = selectedFolder ? `${selectedFolder}/${name}` : name;

    onCreate(path);
    handleClose();
  };

  const handleClose = () => {
    setFilename('');
    setSelectedFolder('');
    setError('');
    onClose();
  };

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="modal-backdrop fixed inset-0" aria-hidden="true" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="modal-panel w-full max-w-md transform p-6 text-left align-middle transition-all">
                <div className="accent-line-top" />
                <Dialog.Title
                  as="h3"
                  className="relative z-10 flex items-center gap-3 mb-4"
                >
                  <FilePlus className="w-5 h-5 text-[var(--accent-primary)]" />
                  <span className="font-display text-lg font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                    New Script
                  </span>
                </Dialog.Title>

                <form onSubmit={handleSubmit}>
                  <div className="relative z-10 space-y-4">
                    {/* Filename Input */}
                    <div>
                      <label htmlFor="filename" className="label-tech mb-1.5 block">
                        Filename
                      </label>
                      <input
                        type="text"
                        id="filename"
                        value={filename}
                        onChange={(e) => setFilename(e.target.value)}
                        placeholder="my_plugin.py or notes.txt"
                        className="input-base"
                        autoFocus
                      />
                      <p className="mt-1 text-xs text-[var(--text-muted)]">
                        .py extension will be added if no .py or .txt extension is provided
                      </p>
                    </div>

                    {/* Folder Selection */}
                    {existingFolders.length > 0 && (
                      <div>
                        <label htmlFor="folder" className="label-tech mb-1.5 block">
                          Location <span className="text-[var(--text-muted)] font-normal normal-case tracking-normal">(optional)</span>
                        </label>
                        <select
                          id="folder"
                          value={selectedFolder}
                          onChange={(e) => setSelectedFolder(e.target.value)}
                          className="input-base"
                        >
                          <option value="">Root folder</option>
                          {existingFolders.map((folder) => (
                            <option key={folder} value={folder}>
                              {folder}/
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {/* Error Display */}
                    {error && (
                      <p className="text-sm text-[var(--accent-danger)]">{error}</p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="relative z-10 flex justify-end gap-3 mt-6">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleClose}
                    >
                      <X className="w-4 h-4 mr-1" />
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary"
                    >
                      <FilePlus className="w-4 h-4 mr-1" />
                      Create
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

export default NewScriptModal;
