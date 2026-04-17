import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import CodeMirrorEditor from './CodeMirrorEditor';
import { X } from 'lucide-react';

function ExpandedEditorModal({
  isOpen,
  onClose,
  fileName,
  fileContent,
  onContentChange,
  language,
  linterSource,
}) {
  const handleContentChangeInternal = (newContent) => {
    onContentChange(newContent);
  };

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-[70]" onClose={onClose}>
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
              <Dialog.Panel className="modal-panel flex flex-col w-[95vw] h-[95vh] transform overflow-hidden text-left align-middle transition-all">
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
                    onClick={onClose}
                    aria-label="Close editor"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="relative z-10 flex-grow overflow-hidden min-h-0 p-1">
                  <CodeMirrorEditor
                    value={fileContent}
                    onChange={handleContentChangeInternal}
                    language={language}
                    linterSource={linterSource}
                    isActiveTab={true}
                    height="100%"
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
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

export default ExpandedEditorModal;
