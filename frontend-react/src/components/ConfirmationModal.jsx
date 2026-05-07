import React from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { AlertTriangle } from 'lucide-react';
import { classNames } from '../utils/uiUtils';

function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmButtonText = 'Confirm',
  cancelButtonText = 'Cancel',
  confirmButtonVariant = 'danger',
  zIndexClass = 'z-10'
}) {
  const getConfirmButtonClasses = () => {
    const base = 'btn';
    switch (confirmButtonVariant) {
      case 'danger':
      case 'red':
        return `${base} btn-danger`;
      case 'primary':
        return `${base} btn-primary`;
      case 'amber':
      case 'warning':
        return `${base} bg-amber-500 dark:bg-[#FFB800] text-white dark:text-black font-semibold hover:bg-amber-600 dark:hover:bg-[#CC9300]`;
      case 'orange':
        return `${base} bg-orange-500 text-white font-semibold hover:bg-orange-600`;
      default:
        return `${base} btn-secondary`;
    }
  };

  const isDangerVariant = confirmButtonVariant === 'danger' || confirmButtonVariant === 'red';

  return (
    <Dialog open={isOpen} as="div" className={classNames("relative", zIndexClass)} onClose={onClose}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Dialog.Panel transition className="modal-panel w-full max-w-md transform overflow-hidden p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
                {/* Accent line (dark mode only) */}
                <div className="accent-line-top" />

                {/* Icon and Title */}
                <div className="flex items-start gap-4">
                  {isDangerVariant && (
                    <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 dark:bg-[#FF3366]/10 border border-red-200 dark:border-[#FF3366]/30 flex items-center justify-center">
                      <AlertTriangle className="w-5 h-5 text-red-600 dark:text-[#FF3366]" />
                    </div>
                  )}

                  <div className="flex-1">
                    <Dialog.Title
                      as="h3"
                      className="font-display text-lg font-semibold tracking-wide text-theme-primary"
                    >
                      {title}
                    </Dialog.Title>
                    <div className="mt-2">
                      <p className="text-sm text-theme-secondary">
                        {message}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="mt-6 flex justify-end gap-3">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={onClose}
                  >
                    {cancelButtonText}
                  </button>
                  <button
                    type="button"
                    className={getConfirmButtonClasses()}
                    onClick={() => {
                      onConfirm();
                      onClose();
                    }}
                  >
                    {confirmButtonText}
                  </button>
                </div>
              </Dialog.Panel>
          </div>
        </div>
    </Dialog>
  );
}

export default ConfirmationModal;
