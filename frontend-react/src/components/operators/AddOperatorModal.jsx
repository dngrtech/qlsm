import React, { useEffect, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { X, UserPlus, AlertTriangle, LoaderCircle } from 'lucide-react';
import { STEAMID64_RE } from '../../utils/operatorConfigSync';

// initialSteamId / initialLevel prefill the form each time it opens -- used by
// the Owner & Admins tab to name an admin that is not in the directory yet.
function AddOperatorModal({ isOpen, onClose, onSubmit, initialSteamId = '', initialLevel = null }) {
  const [name, setName] = useState('');
  const [steamId64, setSteamId64] = useState('');
  const [defaultLevel, setDefaultLevel] = useState('5');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    if (initialSteamId) setSteamId64(initialSteamId);
    if (initialLevel != null) setDefaultLevel(String(initialLevel));
  }, [isOpen, initialSteamId, initialLevel]);

  const resetForm = () => {
    setName('');
    setSteamId64('');
    setDefaultLevel('5');
    setError(null);
    setLoading(false);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const validateForm = () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      return 'Name is required.';
    }
    if (trimmedName.length > 128) {
      return 'Name must be at most 128 characters.';
    }
    if (!STEAMID64_RE.test(steamId64.trim())) {
      return 'SteamID64 must be a 17-digit Steam64 ID starting with 7656119.';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    // React bubbles portal events through the component tree: without this, a
    // submit here also fires the Edit Configuration / Add Instance form it sits in.
    e.stopPropagation();
    setError(null);

    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    try {
      await onSubmit({
        name: name.trim(),
        steam_id64: steamId64.trim(),
        default_level: Number(defaultLevel),
      });
      handleClose();
    } catch (err) {
      const errorMessage = err.error?.message || err.message || 'Failed to add operator.';
      setError(errorMessage);
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
                  Add Operator
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
                <label htmlFor="operator-name" className="block text-sm font-medium text-slate-300 mb-1.5">
                  Name
                </label>
                <input
                  id="operator-name"
                  type="text"
                  autoComplete="off"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input-base"
                  placeholder="Operator display name"
                />
              </div>

              <div>
                <label htmlFor="operator-steamid" className="block text-sm font-medium text-slate-300 mb-1.5">
                  SteamID64
                </label>
                <input
                  id="operator-steamid"
                  type="text"
                  autoComplete="off"
                  value={steamId64}
                  onChange={(e) => setSteamId64(e.target.value.trim())}
                  className="input-base font-mono"
                  placeholder="765611980000000000"
                />
              </div>

              <div>
                <label htmlFor="operator-level" className="block text-sm font-medium text-slate-300 mb-1.5">
                  Default admin level
                </label>
                <select
                  id="operator-level"
                  value={defaultLevel}
                  onChange={(e) => setDefaultLevel(e.target.value)}
                  className="input-base"
                >
                  {[0, 1, 2, 3, 4, 5].map((lvl) => (
                    <option key={lvl} value={lvl}>{lvl}</option>
                  ))}
                </select>
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
                      <UserPlus className="w-4 h-4" />
                      Add Operator
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

export default AddOperatorModal;
