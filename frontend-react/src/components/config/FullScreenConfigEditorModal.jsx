import React, { useState, useEffect, Fragment, useCallback } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, Save, AlertTriangle } from 'lucide-react';
import CodeMirrorEditor from '../CodeMirrorEditor'; // Assuming this path is correct
import ConfirmationModal from '../ConfirmationModal'; // Assuming this path is correct
import { classNames } from '../../utils/uiUtils'; // Assuming this path is correct

const FullScreenConfigEditorModal = ({
  isOpen,
  onClose,
  onSave,
  fileName,
  initialContent,
  language,
  linterSource, // Optional: for CodeMirror linting
}) => {
  const [currentContent, setCurrentContent] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const [showCloseConfirmModal, setShowCloseConfirmModal] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setCurrentContent(initialContent || '');
      setIsDirty(false);
    }
  }, [isOpen, initialContent]);

  const handleContentChange = useCallback((value) => {
    setCurrentContent(value);
    if (!isDirty && value !== initialContent) {
      setIsDirty(true);
    } else if (isDirty && value === initialContent) {
      setIsDirty(false);
    }
  }, [initialContent, isDirty]);

  const handleAttemptClose = useCallback(() => {
    if (isDirty) {
      setShowCloseConfirmModal(true);
    } else {
      onClose();
    }
  }, [isDirty, onClose]);

  const handleConfirmClose = useCallback(() => {
    setShowCloseConfirmModal(false);
    onClose();
  }, [onClose]);

  const handleCancelCloseConfirm = useCallback(() => {
    setShowCloseConfirmModal(false);
  }, []);

  const handleSave = useCallback(() => {
    onSave(currentContent);
    setIsDirty(false); // Assuming save implies modal will close or content is now "clean"
  // onClose(); // Typically onSave would also close the modal, handled by parent
  }, [currentContent, onSave]);

  // Removed: if (!isOpen) return null; 
  // The Transition component's `show` prop will handle visibility and animation.

  return (
    <>
      <Transition appear show={isOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50" onClose={handleAttemptClose}> {/* Removed open={isOpen} to match AddInstanceModal */}
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/70 dark:bg-neutral-900/80" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-2 sm:p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="flex flex-col w-[95vw] h-[95vh] transform overflow-hidden rounded-lg bg-white dark:bg-neutral-800 text-left align-middle shadow-xl transition-all">
                  <div className="flex items-center justify-between p-4 border-b border-neutral-200 dark:border-neutral-700">
                    <Dialog.Title
                      as="h3"
                      className="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100"
                    >
                      Editing: {fileName}
                    </Dialog.Title>
                    <button
                      type="button"
                      className="p-1 rounded-md text-neutral-400 hover:text-neutral-500 dark:text-neutral-500 dark:hover:text-neutral-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-600"
                      onClick={handleAttemptClose}
                    >
                      <X size={24} />
                    </button>
                  </div>

                  <div className="flex-grow overflow-hidden min-h-0"> {/* Added min-h-0 */}
                    {/* Ensure CodeMirrorEditor can handle dynamic height or is styled to fill */}
                    <CodeMirrorEditor
                      value={currentContent}
                      onChange={handleContentChange}
                      language={language}
                      linterSource={linterSource}
                      height="100%" // Set to 100% to fill flex-grow parent
                      // Ensure dark mode is handled by CodeMirrorEditor itself or via theme prop
                    />
                  </div>

                  <div className="flex justify-end items-center p-4 border-t border-neutral-200 dark:border-neutral-700 space-x-3">
                    <button
                      type="button"
                      className={classNames(
                        "px-4 py-2 text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-neutral-800",
                        "text-white bg-red-600 hover:bg-red-700 dark:text-white dark:bg-red-600 dark:hover:bg-red-700 focus:ring-red-500"
                      )}
                      onClick={handleAttemptClose}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className={classNames(
                        "inline-flex items-center px-4 py-2 text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-neutral-800",
                        "text-white bg-indigo-600 hover:bg-indigo-700 focus:ring-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-600"
                        // isDirty ? "bg-indigo-600 hover:bg-indigo-700" : "bg-neutral-400 cursor-not-allowed",
                        // "dark:text-white",
                        // isDirty ? "dark:bg-indigo-500 dark:hover:bg-indigo-600" : "dark:bg-neutral-600"
                      )}
                      onClick={handleSave}
                      // disabled={!isDirty} // Optionally disable if not dirty
                    >
                      <Save size={16} className="mr-2" />
                      Save Changes
                    </button>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>

      {showCloseConfirmModal && (
        <ConfirmationModal
          isOpen={showCloseConfirmModal}
          onClose={handleCancelCloseConfirm}
          onConfirm={handleConfirmClose}
          title="Discard Unsaved Changes?"
          message={`You have unsaved changes in ${fileName}. Are you sure you want to discard them and close?`}
          confirmButtonText="Discard Changes"
          cancelButtonText="Keep Editing"
          icon={<AlertTriangle size={24} className="text-yellow-500" />}
          zIndexClass="z-[60]" // Ensure this is higher than the main modal's z-index
        />
      )}
    </>
  );
};

export default FullScreenConfigEditorModal;
