import React, { Fragment, useState, useEffect } from 'react';
import { Dialog, Transition, Listbox, Portal } from '@headlessui/react';
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/react-dom';
import { LoaderCircle, FolderOpen, X, Check, ChevronDown, AlertTriangle, Trash2 } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';
import { deletePreset } from '../../services/api';

function LoadPresetModal({
  isOpen,
  onClose,
  onLoad,
  presets = [],
  isLoading = false,
  zIndexClass = 'z-50',
  onPresetDeleted
}) {
  const [selectedPreset, setSelectedPreset] = useState(null);
  const [showConfirmation, setShowConfirmation] = useState(false);

  // Delete confirmation state
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  // Floating UI for dropdown positioning
  const { x, y, strategy, refs } = useFloating({
    placement: 'bottom-start',
    middleware: [offset(4), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedPreset(null);
      setShowConfirmation(false);
      setShowDeleteConfirmation(false);
      setDeleteError(null);
    }
  }, [isOpen]);

  const handleLoadClick = () => {
    if (!selectedPreset) return;
    setShowConfirmation(true);
  };

  const handleConfirmLoad = () => {
    if (selectedPreset) {
      onLoad(selectedPreset.id);
    }
  };

  const handleCancelConfirmation = () => {
    setShowConfirmation(false);
  };

  const handleDeleteClick = () => {
    if (!selectedPreset) return;
    setDeleteError(null);
    setShowDeleteConfirmation(true);
  };

  const handleConfirmDelete = async () => {
    if (!selectedPreset) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deletePreset(selectedPreset.id);
      setShowDeleteConfirmation(false);
      setSelectedPreset(null);
      if (onPresetDeleted) {
        onPresetDeleted(selectedPreset.id);
      }
    } catch (err) {
      setDeleteError(err.error?.message || err.message || 'Failed to delete preset.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCancelDelete = () => {
    setShowDeleteConfirmation(false);
    setDeleteError(null);
  };

  // If showing delete confirmation, render the delete confirmation view
  if (showDeleteConfirmation) {
    return (
      <Transition appear show={isOpen} as={Fragment}>
        <Dialog as="div" className={classNames("relative", zIndexClass)} onClose={handleCancelDelete}>
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
                    <AlertTriangle className="w-5 h-5 text-[var(--accent-danger)]" />
                    <span className="font-display text-lg font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                      Delete Preset
                    </span>
                  </Dialog.Title>

                  <div className="relative z-10 mt-4">
                    <p className="text-sm text-[var(--text-secondary)]">
                      Are you sure you want to delete the preset <span className="font-semibold text-[var(--text-primary)]">"{selectedPreset?.name}"</span>?
                    </p>
                    <p className="mt-2 text-sm text-[var(--text-muted)]">
                      This action cannot be undone.
                    </p>
                  </div>

                  {deleteError && (
                    <div className="relative z-10 alert-error mt-4">
                      <p className="text-sm">{deleteError}</p>
                    </div>
                  )}

                  <div className="relative z-10 mt-6 flex justify-end space-x-3">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleCancelDelete}
                      disabled={isDeleting}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={handleConfirmDelete}
                      disabled={isDeleting}
                    >
                      {isDeleting ? (
                        <>
                          <LoaderCircle className="w-4 h-4 mr-1 animate-spin" />
                          Deleting...
                        </>
                      ) : (
                        <>
                          <Trash2 className="w-4 h-4 mr-1" />
                          Delete
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

  // If showing confirmation, render the confirmation view
  if (showConfirmation) {
    return (
      <Transition appear show={isOpen} as={Fragment}>
        <Dialog as="div" className={classNames("relative", zIndexClass)} onClose={handleCancelConfirmation}>
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
                    <AlertTriangle className="w-5 h-5 text-[var(--accent-warning)]" />
                    <span className="font-display text-lg font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                      Confirm Load Preset
                    </span>
                  </Dialog.Title>

                  <div className="relative z-10 mt-4">
                    <p className="text-sm text-[var(--text-secondary)]">
                      Loading the preset <span className="font-semibold text-[var(--text-primary)]">"{selectedPreset?.name}"</span> will overwrite your current configuration changes.
                    </p>
                    <p className="mt-2 text-sm text-[var(--text-muted)]">
                      Are you sure you want to continue?
                    </p>
                  </div>

                  <div className="relative z-10 mt-6 flex justify-end space-x-3">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleCancelConfirmation}
                      disabled={isLoading}
                    >
                      Keep Editing
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleConfirmLoad}
                      disabled={isLoading}
                    >
                      {isLoading ? (
                        <>
                          <LoaderCircle className="w-4 h-4 mr-1 animate-spin" />
                          Loading...
                        </>
                      ) : (
                        <>
                          <FolderOpen className="w-4 h-4 mr-1" />
                          Load Preset
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

  // Main preset selection view
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
                  <FolderOpen className="w-5 h-5 text-[var(--accent-primary)]" />
                  <span className="font-display text-lg font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                    Load Preset
                  </span>
                </Dialog.Title>

                <div className="relative z-10 mt-4">
                  <label className="label-tech mb-1.5 block">
                    Select a Preset
                  </label>

                  {presets.length === 0 ? (
                    <p className="text-sm text-[var(--text-muted)] italic">
                      No presets available.
                    </p>
                  ) : (
                    <Listbox value={selectedPreset} onChange={setSelectedPreset}>
                      {({ open }) => (
                        <div className="relative">
                          <Listbox.Button
                            ref={refs.setReference}
                            className="relative w-full cursor-pointer rounded-md border border-[var(--surface-border)] bg-[var(--surface-raised)] py-2 pl-3 pr-10 text-left text-sm focus:outline-none focus:border-[var(--accent-primary)] transition-colors"
                          >
                            <span className={classNames(
                              "block truncate",
                              selectedPreset ? "text-[var(--text-primary)]" : "text-[var(--text-muted)]"
                            )}>
                              {selectedPreset ? selectedPreset.name : 'Choose a preset...'}
                            </span>
                            <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                              <ChevronDown className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
                            </span>
                          </Listbox.Button>

                          {open && (
                            <Portal>
                              <Transition
                                as={Fragment}
                                show={open}
                                enter="transition ease-out duration-100"
                                enterFrom="transform opacity-0 scale-95"
                                enterTo="transform opacity-100 scale-100"
                                leave="transition ease-in duration-100"
                                leaveFrom="transform opacity-100 scale-100"
                                leaveTo="transform opacity-0 scale-95"
                              >
                                <Listbox.Options
                                  ref={refs.setFloating}
                                  style={{
                                    position: strategy,
                                    top: y ?? 0,
                                    left: x ?? 0,
                                    width: refs.reference.current?.offsetWidth,
                                    zIndex: 9999,
                                  }}
                                  className="max-h-60 overflow-auto rounded-md bg-[var(--surface-overlay)] border border-[var(--surface-border)] py-1 text-sm shadow-xl focus:outline-none scrollbar-thin"
                                >
                                  {presets.map((preset) => (
                                    <Listbox.Option
                                      key={preset.id}
                                      value={preset}
                                      className={({ active }) =>
                                        classNames(
                                          active ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]' : 'text-[var(--text-primary)]',
                                          'relative cursor-pointer select-none py-2 pl-10 pr-4'
                                        )
                                      }
                                    >
                                      {({ selected, active }) => (
                                        <>
                                          <span className={classNames(selected ? 'font-medium' : 'font-normal', 'block truncate')}>
                                            {preset.name}
                                          </span>
                                          {preset.description && (
                                            <span className={classNames(
                                              active ? 'text-[var(--accent-primary)]/70' : 'text-[var(--text-muted)]',
                                              'block truncate text-xs'
                                            )}>
                                              {preset.description}
                                            </span>
                                          )}
                                          {selected && (
                                            <span className={classNames(
                                              'text-[var(--accent-primary)]',
                                              'absolute inset-y-0 left-0 flex items-center pl-3'
                                            )}>
                                              <Check className="h-4 w-4" aria-hidden="true" />
                                            </span>
                                          )}
                                        </>
                                      )}
                                    </Listbox.Option>
                                  ))}
                                </Listbox.Options>
                              </Transition>
                            </Portal>
                          )}
                        </div>
                      )}
                    </Listbox>
                  )}
                </div>

                <div className="relative z-10 mt-6 flex justify-between items-center">
                  {/* Left side - Delete button */}
                  <div>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={handleDeleteClick}
                      disabled={!selectedPreset || selectedPreset.name === 'default'}
                      title={selectedPreset?.name === 'default' ? 'Cannot delete the default preset' : 'Delete selected preset'}
                    >
                      <Trash2 className="w-4 h-4 mr-1" />
                      Delete
                    </button>
                  </div>

                  {/* Right side - Cancel and Load buttons */}
                  <div className="flex space-x-3">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={onClose}
                    >
                      <X className="w-4 h-4 mr-1" />
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleLoadClick}
                      disabled={!selectedPreset}
                    >
                      <FolderOpen className="w-4 h-4 mr-1" />
                      Load Preset
                    </button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

export default LoadPresetModal;
