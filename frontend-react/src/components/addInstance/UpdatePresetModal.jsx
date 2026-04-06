import React, { Fragment, useState, useEffect } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { LoaderCircle, RefreshCw, X } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';

function UpdatePresetModal({
  isOpen,
  onClose,
  onConfirm,
  presetName,
  initialDescription = '',
  isUpdating = false,
  zIndexClass = 'z-50'
}) {
  const [description, setDescription] = useState('');

  // Reset description when modal opens
  useEffect(() => {
    if (isOpen) {
      setDescription(initialDescription || '');
    }
  }, [isOpen, initialDescription]);

  const handleConfirm = () => {
    onConfirm(description.trim() || null);
  };

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className={classNames("relative", zIndexClass)} onClose={onClose}>
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
                  <RefreshCw className="w-5 h-5 text-[var(--accent-primary)]" />
                  <span className="font-display text-lg font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                    Update Preset
                  </span>
                </Dialog.Title>

                <div className="relative z-10 mt-4">
                  <p className="text-sm text-[var(--text-secondary)]">
                    Updating: <span className="font-semibold text-[var(--text-primary)]">"{presetName}"</span>
                  </p>
                </div>

                <div className="relative z-10 mt-4">
                  <label htmlFor="updatePresetDescription" className="label-tech mb-1.5 block">
                    Description <span className="text-[var(--text-muted)] font-normal normal-case tracking-normal">(optional)</span>
                  </label>
                  <textarea
                    id="updatePresetDescription"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="e.g., Standard duel settings with competitive mappool"
                    rows={2}
                    className="input-base resize-none"
                    disabled={isUpdating}
                  />
                </div>

                <p className="relative z-10 mt-3 text-sm text-[var(--text-muted)]">
                  This will overwrite the saved configuration with your current changes.
                </p>

                <div className="relative z-10 mt-6 flex justify-end space-x-3">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={onClose}
                    disabled={isUpdating}
                  >
                    <X className="w-4 h-4 mr-1" />
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleConfirm}
                    disabled={isUpdating}
                  >
                    {isUpdating ? (
                      <>
                        <LoaderCircle className="w-4 h-4 mr-1 animate-spin" />
                        Updating...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4 mr-1" />
                        Update Preset
                      </>
                    )}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

export default UpdatePresetModal;
