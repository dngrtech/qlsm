import React, { useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { X, PackagePlus, AlertTriangle, LoaderCircle } from 'lucide-react';

function AddPluginRepositoryModal({ isOpen, onClose, onSubmit }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const resetForm = () => {
    setName('');
    setUrl('');
    setError(null);
    setLoading(false);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const validateForm = () => {
    const trimmedName = name.trim();
    if (!trimmedName) return 'Name is required.';
    if (trimmedName.length > 100) return 'Name must be at most 100 characters.';
    const trimmedUrl = url.trim();
    if (!trimmedUrl || !(trimmedUrl.startsWith('http://') || trimmedUrl.startsWith('https://'))) {
      return 'URL must start with http:// or https://.';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    try {
      await onSubmit({ name: name.trim(), url: url.trim() });
      handleClose();
    } catch (err) {
      setError(err.error?.message || err.message || 'Failed to add repository.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleClose}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4 text-center">
          <Dialog.Panel transition className="modal-panel w-full max-w-md transform p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
            <div className="accent-line-top" />

            <div className="relative z-10 flex items-center justify-between mb-6">
              <Dialog.Title as="h3" className="flex items-center gap-3">
                <span className="status-pulse status-pulse-active" />
                <span className="font-display text-xl font-semibold tracking-wider uppercase text-theme-primary">
                  Add Plugin Repository
                </span>
              </Dialog.Title>
              <button
                onClick={handleClose}
                className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="relative z-10 space-y-5">
              <div>
                <label htmlFor="repo-name" className="block text-sm font-medium text-slate-300 mb-1.5">
                  Name
                </label>
                <input
                  id="repo-name"
                  type="text"
                  autoComplete="off"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input-base"
                  placeholder="e.g. Community minqlx plugins"
                />
              </div>

              <div>
                <label htmlFor="repo-url" className="block text-sm font-medium text-slate-300 mb-1.5">
                  Repository URL
                </label>
                <input
                  id="repo-url"
                  type="text"
                  autoComplete="off"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="input-base font-mono"
                  placeholder="https://example.com/plugins"
                />
                <p className="text-xs text-[var(--text-muted)] mt-1.5">
                  Must serve <code>qlsm-plugins.json</code> at this URL's root.
                </p>
              </div>

              {error && (
                <div className="alert-error flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-500 dark:text-[#FF3366] flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-700/50">
                <button type="button" onClick={handleClose} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={loading} className="btn btn-primary">
                  {loading ? (
                    <>
                      <LoaderCircle className="w-4 h-4 animate-spin" />
                      Adding...
                    </>
                  ) : (
                    <>
                      <PackagePlus className="w-4 h-4" />
                      Add Repository
                    </>
                  )}
                </button>
              </div>
            </form>
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}

export default AddPluginRepositoryModal;
