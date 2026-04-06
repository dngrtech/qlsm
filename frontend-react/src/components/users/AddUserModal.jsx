import React, { Fragment, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, UserPlus, AlertTriangle, LoaderCircle } from 'lucide-react';

const USERNAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

function AddUserModal({ isOpen, onClose, onSubmit }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const resetForm = () => {
    setUsername('');
    setPassword('');
    setConfirmPassword('');
    setError(null);
    setLoading(false);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const validateForm = () => {
    const trimmedUsername = username.trim();

    if (!trimmedUsername) {
      return 'Username is required.';
    }
    if (trimmedUsername.length < 2) {
      return 'Username must be at least 2 characters.';
    }
    if (trimmedUsername.length > 80) {
      return 'Username must be at most 80 characters.';
    }
    if (!USERNAME_PATTERN.test(trimmedUsername)) {
      return 'Username can only contain letters, numbers, hyphens, and underscores.';
    }
    if (!password) {
      return 'Password is required.';
    }
    if (password.length < 8) {
      return 'Password must be at least 8 characters.';
    }
    if (password.length > 128) {
      return 'Password must be at most 128 characters.';
    }
    if (password !== confirmPassword) {
      return 'Passwords do not match.';
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
      await onSubmit({ username: username.trim(), password });
      handleClose();
    } catch (err) {
      const errorMessage = err.error?.message || err.message || 'Failed to create user.';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
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
          <div className="modal-backdrop fixed inset-0" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 scale-95"
              enterTo="opacity-100 translate-y-0 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="modal-panel w-full max-w-md transform p-6 text-left align-middle transition-all">
                {/* Accent line decoration */}
                <div className="accent-line-top" />

                {/* Header */}
                <div className="relative z-10 flex items-center justify-between mb-6">
                  <Dialog.Title as="h3" className="flex items-center gap-3">
                    <span className="status-pulse status-pulse-active" />
                    <span className="font-display text-xl font-semibold tracking-wider uppercase text-theme-primary">
                      Add New User
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
                  {/* Username field */}
                  <div>
                    <label
                      htmlFor="new-username"
                      className="block text-sm font-medium text-slate-300 mb-1.5"
                    >
                      Username
                    </label>
                    <input
                      id="new-username"
                      type="text"
                      autoComplete="off"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="input-base"
                      placeholder="Enter username"
                    />
                  </div>

                  {/* Password field */}
                  <div>
                    <label
                      htmlFor="new-password"
                      className="block text-sm font-medium text-slate-300 mb-1.5"
                    >
                      Password
                    </label>
                    <input
                      id="new-password"
                      type="password"
                      autoComplete="new-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="input-base"
                      placeholder="Enter password"
                    />
                  </div>

                  {/* Confirm Password field */}
                  <div>
                    <label
                      htmlFor="confirm-password"
                      className="block text-sm font-medium text-slate-300 mb-1.5"
                    >
                      Confirm Password
                    </label>
                    <input
                      id="confirm-password"
                      type="password"
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="input-base"
                      placeholder="Confirm password"
                    />
                  </div>

                  {/* Error message */}
                  {error && (
                    <div className="alert-error flex items-start gap-3">
                      <AlertTriangle className="w-5 h-5 text-red-500 dark:text-[#FF3366] flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex justify-end gap-3 pt-4 border-t border-slate-700/50">
                    <button
                      type="button"
                      onClick={handleClose}
                      className="px-4 py-2 text-sm font-medium rounded-lg border border-slate-600 text-slate-300 bg-slate-800 hover:bg-slate-700 hover:border-slate-500 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading}
                      className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-2"
                    >
                      {loading ? (
                        <>
                          <LoaderCircle className="w-4 h-4 animate-spin" />
                          Creating...
                        </>
                      ) : (
                        <>
                          <UserPlus className="w-4 h-4" />
                          Create User
                        </>
                      )}
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

export default AddUserModal;
