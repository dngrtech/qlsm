import React, { useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { Layers, X } from 'lucide-react';
import BulkPluginUpdatesTab from './BulkPluginUpdatesTab';
import BulkPresetApplyTab from './BulkPresetApplyTab';

// One entry per bulk action tab: { id, label }. The active tab's body is shown by id below.
const TABS = [
    { id: 'plugins', label: 'Update plugins' },
    { id: 'preset', label: 'Apply preset' },
];

function BulkActionsModal({ isOpen, onClose, hosts }) {
    const [tab, setTab] = useState('plugins');

    return (
        <Dialog open={isOpen} as="div" className="relative z-50" onClose={onClose}>
            <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

            <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
                <div className="flex min-h-full items-center justify-center p-4">
                    <Dialog.Panel transition className="modal-panel w-full max-w-2xl transform p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
                        <div className="accent-line-top" />

                        <Dialog.Title as="h3" className="relative z-10 flex items-center gap-3 mb-4">
                            <span className="status-pulse status-pulse-active" />
                            <Layers size={18} className="text-[var(--accent-primary)]" />
                            <span className="font-display text-base font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                                Bulk actions
                            </span>
                            <button type="button" onClick={onClose} className="ml-auto logs-modal-close-btn" aria-label="Close">
                                <X size={18} />
                            </button>
                        </Dialog.Title>

                        <div role="tablist" className="flex gap-1 mb-4 border-b border-[var(--surface-border)]">
                            {TABS.map(t => (
                                <button
                                    key={t.id}
                                    type="button"
                                    role="tab"
                                    aria-selected={tab === t.id}
                                    onClick={() => setTab(t.id)}
                                    className={`px-3 py-2 text-xs font-semibold uppercase tracking-wider border-b-2 ${tab === t.id ? 'border-[var(--accent-primary)] text-[var(--text-primary)]' : 'border-transparent text-[var(--text-muted)]'}`}
                                >
                                    {t.label}
                                </button>
                            ))}
                        </div>

                        {/* Both tabs stay mounted and the inactive one is hidden: a
                            remount would drop the plugin check results and re-tick
                            what was already sent, and drop the preset previews.
                            The plugin checks run on their tab's Check button only. */}
                        <div role="tabpanel" hidden={tab !== 'plugins'}>
                            <BulkPluginUpdatesTab isOpen={isOpen} hosts={hosts} onClose={onClose} />
                        </div>
                        <div role="tabpanel" hidden={tab !== 'preset'}>
                            <BulkPresetApplyTab isOpen={isOpen} hosts={hosts} onClose={onClose} />
                        </div>
                    </Dialog.Panel>
                </div>
            </div>
        </Dialog>
    );
}

export default BulkActionsModal;
