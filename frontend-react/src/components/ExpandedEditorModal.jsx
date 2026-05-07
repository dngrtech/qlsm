import React from 'react';
import { Dialog } from '@headlessui/react';
import CodeMirrorEditor from './CodeMirrorEditor';
import { X } from 'lucide-react';

function ExpandedEditorModal({
  isOpen,
  onClose,
  fileName,
  fileContent,
  onContentChange = () => {},
  language,
  linterSource,
  readOnly = false,
  titlePrefix = 'Editing:',
}) {
  return (
    <Dialog open={isOpen} as="div" className="relative z-[70]" onClose={onClose}>
      <Dialog.Backdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Dialog.Panel transition className="modal-panel flex flex-col w-[95vw] h-[95vh] transform overflow-hidden text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:scale-95">
                <div className="accent-line-top" />

                <div className="relative z-10 flex items-center justify-between p-4 border-b border-[var(--surface-border)]">
                  <Dialog.Title
                    as="h3"
                    className="font-display text-lg font-semibold tracking-wider uppercase text-theme-primary"
                  >
                    {titlePrefix} {fileName}
                  </Dialog.Title>
                  <button
                    type="button"
                    className="logs-modal-close-btn"
                    onClick={onClose}
                    aria-label="Close editor"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="relative z-10 flex-grow overflow-hidden min-h-0 bg-[var(--surface-base)] p-1">
                  <CodeMirrorEditor
                    value={fileContent}
                    onChange={onContentChange}
                    language={language}
                    linterSource={linterSource}
                    isActiveTab={true}
                    height="100%"
                    readOnly={readOnly}
                  />
                </div>

                <div className="relative z-10 flex justify-end items-center p-4 border-t border-[var(--surface-border)]">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={onClose}
                  >
                    Done
                  </button>
                </div>
              </Dialog.Panel>
          </div>
        </div>
    </Dialog>
  );
}

export default ExpandedEditorModal;
