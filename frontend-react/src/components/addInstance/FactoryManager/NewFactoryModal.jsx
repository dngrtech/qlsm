import React, { useState, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, FilePlus } from 'lucide-react';

/**
 * Modal for creating a new Factory file.
 */
function NewFactoryModal({
    isOpen,
    onClose,
    onCreate,
    existingFiles = []
}) {
    const [filename, setFilename] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        e.stopPropagation(); // Prevent bubbling to parent forms
        setError('');

        // Validate filename
        let name = filename.trim();
        if (!name) {
            setError('Filename is required');
            return;
        }

        // Add .factories extension if not present
        if (!name.endsWith('.factories')) {
            name = name + '.factories';
        }

        // Check for invalid characters
        // Only allow letters, numbers, underscores, hyphens, and the dot.
        if (!/^[a-zA-Z0-9_-]+\.factories$/.test(name)) {
            setError('Invalid filename. Use only letters, numbers, underscores, and hyphens.');
            return;
        }

        // Check uniqueness
        if (existingFiles.some(f => f.path === name || f.name === name)) {
            setError('A file with this name already exists.');
            return;
        }

        onCreate(name);
        handleClose();
    };

    const handleClose = () => {
        setFilename('');
        setError('');
        onClose();
    };

    return (
        <Transition appear show={isOpen} as={Fragment}>
            <Dialog as="div" className="relative z-50" onClose={handleClose}>
                <Transition.Child
                    as={Fragment}
                    enter="ease-out duration-300"
                    enterFrom="opacity-0"
                    enterTo="opacity-100"
                    leave="ease-in duration-200"
                    leaveFrom="opacity-100"
                    leaveTo="opacity-0"
                >
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" />
                </Transition.Child>

                <div className="fixed inset-0 overflow-y-auto">
                    <div className="flex min-h-full items-center justify-center p-4">
                        <Transition.Child
                            as={Fragment}
                            enter="ease-out duration-300"
                            enterFrom="opacity-0 scale-95"
                            enterTo="opacity-100 scale-100"
                            leave="ease-in duration-200"
                            leaveFrom="opacity-100 scale-100"
                            leaveTo="opacity-0 scale-95"
                        >
                            <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-slate-800 p-6 text-left align-middle shadow-xl transition-all border border-slate-700">
                                <Dialog.Title as="div" className="flex items-center justify-between mb-4">
                                    <div className="flex items-center gap-2">
                                        <FilePlus size={20} className="text-indigo-400" />
                                        <h3 className="text-lg font-semibold text-white">New Factory File</h3>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={handleClose}
                                        className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-700 transition-colors"
                                    >
                                        <X size={20} />
                                    </button>
                                </Dialog.Title>

                                <form onSubmit={handleSubmit}>
                                    <div className="space-y-4">
                                        {/* Filename Input */}
                                        <div>
                                            <label htmlFor="filename" className="block text-sm font-medium text-slate-300 mb-1">
                                                Filename
                                            </label>
                                            <input
                                                type="text"
                                                id="filename"
                                                value={filename}
                                                onChange={(e) => setFilename(e.target.value)}
                                                placeholder="my_custom.factories"
                                                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                                autoFocus
                                            />
                                            <p className="mt-1 text-xs text-slate-500">
                                                .factories extension will be added automatically
                                            </p>
                                        </div>

                                        {/* Error Display */}
                                        {error && (
                                            <p className="text-sm text-red-400">{error}</p>
                                        )}
                                    </div>

                                    {/* Actions */}
                                    <div className="flex justify-end gap-3 mt-6">
                                        <button
                                            type="button"
                                            onClick={handleClose}
                                            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm font-medium rounded-lg transition-colors"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            type="submit"
                                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
                                        >
                                            Create
                                        </button>
                                    </div>
                                </form>
                            </Dialog.Panel>
                        </Transition.Child>
                    </div>
                </div>
            </Dialog>
        </Transition>
    );
}

export default NewFactoryModal;
