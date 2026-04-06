import React, { useState, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { DownloadCloud, X } from 'lucide-react';

function ForceUpdateWorkshopModal({ isOpen, onClose, onSubmit, host }) {
    const [workshopId, setWorkshopId] = useState('');
    const [selectedInstances, setSelectedInstances] = useState({});

    if (!host) return null;

    const validInstances = host.instances?.filter(instance => {
        const s = instance.status?.toLowerCase();
        return s !== 'deleting' && s !== 'error' && s !== 'deploying' && s !== 'configuring' && s !== 'restarting';
    }) || [];

    const handleToggle = (instanceId) => {
        setSelectedInstances(prev => ({
            ...prev,
            [instanceId]: !prev[instanceId]
        }));
    };

    const handleClose = () => {
        setWorkshopId('');
        setSelectedInstances({});
        onClose();
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!workshopId.trim()) return;

        // Get list of instance IDs that were toggled on
        const restartInstanceIds = Object.entries(selectedInstances)
            .filter(([_, isSelected]) => isSelected)
            .map(([id]) => parseInt(id, 10));

        onSubmit(workshopId.trim(), restartInstanceIds);
        handleClose();
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
                    <div className="modal-backdrop fixed inset-0" aria-hidden="true" />
                </Transition.Child>

                <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
                    <div className="flex min-h-full items-center justify-center p-4">
                        <Transition.Child
                            as={Fragment}
                            enter="ease-out duration-300"
                            enterFrom="opacity-0 translate-y-4 scale-95"
                            enterTo="opacity-100 translate-y-0 scale-100"
                            leave="ease-in duration-200"
                            leaveFrom="opacity-100 scale-100"
                            leaveTo="opacity-0 scale-95"
                        >
                            <Dialog.Panel className="modal-panel w-full max-w-md transform p-6 text-left align-middle transition-all">
                                {/* Accent line decoration (dark mode only) */}
                                <div className="accent-line-top" />

                                {/* Header */}
                                <Dialog.Title
                                    as="h3"
                                    className="relative z-10 flex items-center gap-3 mb-6"
                                >
                                    <span className="status-pulse status-pulse-active" />
                                    <DownloadCloud size={18} className="text-[var(--accent-primary)]" />
                                    <span className="font-display text-base font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                                        Force Update Workshop Item
                                    </span>
                                    <button
                                        type="button"
                                        onClick={handleClose}
                                        className="ml-auto logs-modal-close-btn"
                                    >
                                        <X size={18} />
                                    </button>
                                </Dialog.Title>

                                <form onSubmit={handleSubmit}>
                                    <div className="space-y-6">
                                        <div>
                                            <label htmlFor="workshopId" className="label-tech mb-1.5 block">
                                                Workshop Item ID <span className="text-[var(--accent-danger)]">*</span>
                                            </label>
                                            <input
                                                type="text"
                                                inputMode="numeric"
                                                pattern="\d+"
                                                id="workshopId"
                                                value={workshopId}
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    if (val === '' || /^\d+$/.test(val)) {
                                                        setWorkshopId(val);
                                                    }
                                                }}
                                                onPaste={(e) => {
                                                    const pasted = e.clipboardData.getData('text').trim();
                                                    if (!/^\d+$/.test(pasted)) {
                                                        e.preventDefault();
                                                    }
                                                }}
                                                className="input-base w-full font-mono"
                                                placeholder="e.g., 3510277557"
                                                required
                                            />
                                        </div>

                                        {validInstances.length > 0 && (
                                            <div>
                                                <label className="label-tech mb-1.5 block">
                                                    Auto-Restart Instances
                                                </label>
                                                <p className="text-xs text-[var(--text-muted)] mb-3">
                                                    Select instances to automatically restart after the workshop is updated.
                                                </p>
                                                <div className="space-y-2 max-h-72 overflow-y-auto scrollbar-thin pr-2">
                                                    {validInstances.map(instance => {
                                                        const isStopped = instance.status?.toLowerCase() === 'stopped';
                                                        const isSelected = !!selectedInstances[instance.id];
                                                        return (
                                                            <div
                                                                key={instance.id}
                                                                className={`flex items-center justify-between p-3 rounded-lg border transition-all ${isSelected
                                                                    ? 'border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/5'
                                                                    : 'border-[var(--surface-border)] bg-[var(--surface-raised)]'
                                                                    } ${isStopped ? 'opacity-45 grayscale' : ''}`}
                                                                title={isStopped ? "Instance is stopped" : ""}
                                                            >
                                                                <div className="flex flex-col">
                                                                    <span className="text-sm font-medium text-[var(--text-primary)]">{instance.name}</span>
                                                                    <span className="text-xs font-mono text-[var(--text-muted)]">Port {instance.port}</span>
                                                                </div>

                                                                <button
                                                                    type="button"
                                                                    onClick={() => handleToggle(instance.id)}
                                                                    disabled={isStopped}
                                                                    className="neu-toggle neu-toggle--sm"
                                                                    aria-pressed={isSelected}
                                                                >
                                                                    <span className="sr-only">Toggle restart for {instance.name}</span>
                                                                    <span className={`neu-toggle__track ${isSelected ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                                                        <span className={`neu-toggle__knob ${isSelected ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                                                                    </span>
                                                                </button>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {/* Footer */}
                                    <div className="flex justify-end items-center gap-3 mt-6 pt-4 border-t border-[var(--surface-border)]">
                                        <span className="font-mono text-xs text-[var(--text-muted)] tracking-wide mr-auto hidden sm:inline-flex items-center gap-1.5">
                                            <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-elevated)] border border-[var(--surface-border)] text-[10px] font-bold">Esc</kbd>
                                            to close
                                        </span>
                                        <button
                                            type="button"
                                            onClick={handleClose}
                                            className="btn btn-secondary"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            type="submit"
                                            disabled={!workshopId.trim()}
                                            className="btn btn-primary"
                                        >
                                            Update Workshop
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

export default ForceUpdateWorkshopModal;
