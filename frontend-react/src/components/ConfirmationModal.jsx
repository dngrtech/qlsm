import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
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
          <div className="modal-backdrop fixed inset-0" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95 translate-y-4"
              enterTo="opacity-100 scale-100 translate-y-0"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="modal-panel w-full max-w-md transform overflow-hidden p-6 text-left align-middle transition-all">
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
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

export default ConfirmationModal;
