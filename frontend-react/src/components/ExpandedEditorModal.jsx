import React, { Fragment } from 'react'; // Removed useState, useEffect
import { Dialog, Transition } from '@headlessui/react';
import CodeMirrorEditor from './CodeMirrorEditor';
// ConfirmationModal no longer needed here
import { X } from 'lucide-react';

function ExpandedEditorModal({
  isOpen,
  onClose, // This will now be called directly
  fileName,
  fileContent,
  onContentChange, // Content changes are propagated up
  language,
  linterSource,
}) {
  // Unsaved changes logic (isDirty, showCloseConfirmExpanded, initialContent, related functions) removed.
  // The parent modal (EditInstanceConfigModal) will handle unsaved changes for the overall configuration.

  // When CodeMirror content changes, just propagate it.
  const handleContentChangeInternal = (newContent) => {
    onContentChange(newContent);
  };

  // All close actions (backdrop, Esc, X button, Done button) will directly call the onClose prop.
  return (
    <>
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
            <div className="fixed inset-0 bg-black/30 dark:bg-black/50" />
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
                {/* Changed sizing and structure to match FullScreenConfigEditorModal */}
                <Dialog.Panel className="flex flex-col w-[95vw] h-[95vh] transform overflow-hidden rounded-lg bg-white dark:bg-slate-800 text-left align-middle shadow-xl transition-all">
                  <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-slate-700">
                    <Dialog.Title
                      as="h3"
                      className="text-lg font-medium leading-6 text-gray-900 dark:text-slate-100"
                    >
                      Editing: {fileName}
                    </Dialog.Title>
                    <button
                      type="button"
                      className="p-1 rounded-md text-gray-400 hover:text-gray-500 dark:text-slate-400 dark:hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-600"
                      onClick={onClose} // Directly call onClose
                      aria-label="Close editor"
                    >
                      <X size={24} />
                    </button>
                  </div>

                  {/* Editor takes remaining space */}
                  <div className="flex-grow overflow-hidden min-h-0 p-1"> {/* Added p-1 for slight padding around editor */}
                    <CodeMirrorEditor
                      value={fileContent}
                      onChange={handleContentChangeInternal}
                      language={language}
                      linterSource={linterSource}
                      isActiveTab={true}
                      height="100%" // Ensure CodeMirror takes full height of this div
                    />
                  </div>

                  {/* Footer with Done button */}
                  <div className="flex justify-end items-center p-4 border-t border-gray-200 dark:border-slate-700">
                    <button
                      type="button"
                      className="inline-flex justify-center rounded-md border border-transparent bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 dark:bg-indigo-500 dark:hover:bg-indigo-600"
                      onClick={onClose} // Directly call onClose
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
      {/* ConfirmationModal removed from here */}
    </>
  );
}

export default ExpandedEditorModal;
