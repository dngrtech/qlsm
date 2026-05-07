import React, { useState, useEffect, useCallback } from 'react';
import { Dialog } from '@headlessui/react';
import { X, Save, AlertTriangle } from 'lucide-react';
import CodeMirrorEditor from '../CodeMirrorEditor';
import ConfirmationModal from '../ConfirmationModal';

const FullScreenConfigEditorModal = ({
  isOpen,
  onClose,
  onSave,
  fileName,
  initialContent,
  language,
  linterSource,
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
    setIsDirty(false);
  }, [currentContent, onSave]);

  return (
    <>
      <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleAttemptClose}>
        <Dialog.Backdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-2 sm:p-4">
                <Dialog.Panel transition className="modal-panel flex flex-col w-[95vw] h-[95vh] transform overflow-hidden text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:scale-95">
                  <div className="accent-line-top" />

                  <div className="relative z-10 flex items-center justify-between p-4 border-b border-[var(--surface-border)]">
                    <Dialog.Title
                      as="h3"
                      className="font-display text-lg font-semibold tracking-wider uppercase text-theme-primary"
                    >
                      Editing: {fileName}
                    </Dialog.Title>
                    <button
                      type="button"
                      className="logs-modal-close-btn"
                      onClick={handleAttemptClose}
                      aria-label="Close editor"
                    >
                      <X size={16} />
                    </button>
                  </div>

                  <div className="relative z-10 flex-grow overflow-hidden min-h-0 bg-[var(--surface-base)]">
                    <CodeMirrorEditor
                      value={currentContent}
                      onChange={handleContentChange}
                      language={language}
                      linterSource={linterSource}
                      height="100%"
                    />
                  </div>

                  <div className="relative z-10 flex justify-end items-center p-4 border-t border-[var(--surface-border)] gap-3">
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={handleAttemptClose}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary inline-flex items-center"
                      onClick={handleSave}
                    >
                      <Save size={16} className="mr-2" />
                      Save Changes
                    </button>
                  </div>
                </Dialog.Panel>
            </div>
          </div>
      </Dialog>

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
          zIndexClass="z-[60]"
        />
      )}
    </>
  );
};

export default FullScreenConfigEditorModal;
