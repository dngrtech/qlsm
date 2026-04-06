import React, { Fragment, useState, useEffect, useCallback } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { LoaderCircle, Save, X } from 'lucide-react';
import { validatePresetName } from '../../services/api';
import { classNames } from '../../utils/uiUtils';

// Valid preset name pattern (matches backend)
const PRESET_NAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

function SavePresetModal({
  isOpen,
  onClose,
  onSave,
  isSaving = false,
  zIndexClass = 'z-50',
  initialDescription = ''
}) {
  const [presetName, setPresetName] = useState('');
  const [description, setDescription] = useState('');
  const [validationError, setValidationError] = useState(null);
  const [isValidating, setIsValidating] = useState(false);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setPresetName('');
      setDescription(initialDescription || '');
      setValidationError(null);
      setIsValidating(false);
    }
  }, [isOpen, initialDescription]);

  // Client-side validation
  const validateNameLocally = useCallback((name) => {
    if (!name.trim()) {
      return 'Preset name is required.';
    }
    if (!PRESET_NAME_PATTERN.test(name)) {
      return 'Preset name can only contain letters, numbers, hyphens, and underscores.';
    }
    if (name.toLowerCase() === 'default') {
      return '"default" is a reserved preset name.';
    }
    return null;
  }, []);

  const handleNameChange = (e) => {
    const newName = e.target.value;
    setPresetName(newName);

    // Clear server validation error when user types
    if (validationError && !validateNameLocally(newName)) {
      setValidationError(null);
    } else {
      setValidationError(validateNameLocally(newName));
    }
  };

  const handleSave = async () => {
    // Client-side validation first
    const localError = validateNameLocally(presetName);
    if (localError) {
      setValidationError(localError);
      return;
    }

    // Server-side validation (check for duplicates)
    setIsValidating(true);
    try {
      const result = await validatePresetName(presetName.trim());
      if (!result.is_valid) {
        setValidationError(result.error);
        setIsValidating(false);
        return;
      }
    } catch (err) {
      setValidationError(err.error?.message || 'Failed to validate preset name.');
      setIsValidating(false);
      return;
    }
    setIsValidating(false);

    // Call parent save handler with name and description
    onSave({ name: presetName.trim(), description: description.trim() || null });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !isSaving && !isValidating && presetName.trim()) {
      handleSave();
    }
  };

  const isSubmitDisabled = isSaving || isValidating || !presetName.trim() || !!validateNameLocally(presetName);

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
                  <Save className="w-5 h-5 text-[var(--accent-primary)]" />
                  <span className="font-display text-lg font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                    Save as Preset
                  </span>
                </Dialog.Title>

                <div className="relative z-10 mt-4">
                  <label htmlFor="presetName" className="label-tech mb-1.5 block">
                    Preset Name
                  </label>
                  <input
                    type="text"
                    id="presetName"
                    value={presetName}
                    onChange={handleNameChange}
                    onKeyDown={handleKeyDown}
                    placeholder="e.g., duel-config, ffa-settings"
                    className={classNames(
                      "input-base",
                      validationError && "!border-[var(--accent-danger)]"
                    )}
                    disabled={isSaving}
                    autoFocus
                  />
                  {validationError && (
                    <p className="mt-1 text-sm text-[var(--accent-danger)]">
                      {validationError}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    Letters, numbers, hyphens, and underscores only.
                  </p>
                </div>

                <div className="relative z-10 mt-4">
                  <label htmlFor="presetDescription" className="label-tech mb-1.5 block">
                    Description <span className="text-[var(--text-muted)] font-normal normal-case tracking-normal">(optional)</span>
                  </label>
                  <textarea
                    id="presetDescription"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="e.g., Standard duel settings with competitive mappool"
                    rows={2}
                    className="input-base resize-none"
                    disabled={isSaving}
                  />
                </div>

                <div className="relative z-10 mt-6 flex justify-end space-x-3">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={onClose}
                    disabled={isSaving}
                  >
                    <X className="w-4 h-4 mr-1" />
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleSave}
                    disabled={isSubmitDisabled}
                  >
                    {(isSaving || isValidating) ? (
                      <>
                        <LoaderCircle className="w-4 h-4 mr-1 animate-spin" />
                        {isValidating ? 'Validating...' : 'Saving...'}
                      </>
                    ) : (
                      <>
                        <Save className="w-4 h-4 mr-1" />
                        Save Preset
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

export default SavePresetModal;
