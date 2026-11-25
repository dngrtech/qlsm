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
    // Which tabs are applying right now. While any is, no way of closing the
    // dialog works (Escape, the backdrop, X or a tab's Close): closing drops
    // the results the running apply is still filling in.
    const [applyingTabs, setApplyingTabs] = useState({});
    const applying = Object.values(applyingTabs).some(Boolean);
    const applyingFor = (id) => (value) => setApplyingTabs(prev => (
        Boolean(prev[id]) === Boolean(value) ? prev : { ...prev, [id]: Boolean(value) }
    ));
    const handleClose = () => { if (!applying) onClose(); };

    // Arrow keys move between tabs (WAI-ARIA tabs pattern).
    const onTabKeyDown = (e) => {
        const index = TABS.findIndex(t => t.id === tab);
        let next = null;
        if (e.key === 'ArrowRight') next = (index + 1) % TABS.length;
        if (e.key === 'ArrowLeft') next = (index - 1 + TABS.length) % TABS.length;
        if (e.key === 'Home') next = 0;
        if (e.key === 'End') next = TABS.length - 1;
        if (next === null) return;
        e.preventDefault();
        setTab(TABS[next].id);
        document.getElementById(`bulk-tab-${TABS[next].id}`)?.focus();
    };

    return (
        <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleClose}>
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
                            <button type="button" onClick={handleClose} disabled={applying} className="ml-auto logs-modal-close-btn" aria-label="Close">
                                <X size={18} />
                            </button>
                        </Dialog.Title>

                        <div role="tablist" aria-label="Bulk actions" onKeyDown={onTabKeyDown} className="flex gap-1 mb-4 border-b border-[var(--surface-border)]">
                            {TABS.map(t => (
                                <button
                                    key={t.id}
                                    id={`bulk-tab-${t.id}`}
                                    type="button"
                                    role="tab"
                                    aria-selected={tab === t.id}
                                    aria-controls={`bulk-panel-${t.id}`}
                                    tabIndex={tab === t.id ? 0 : -1}
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
                        <div role="tabpanel" id="bulk-panel-plugins" aria-labelledby="bulk-tab-plugins" hidden={tab !== 'plugins'}>
                            <BulkPluginUpdatesTab isOpen={isOpen} hosts={hosts} onClose={handleClose} onApplyingChange={applyingFor('plugins')} />
                        </div>
                        <div role="tabpanel" id="bulk-panel-preset" aria-labelledby="bulk-tab-preset" hidden={tab !== 'preset'}>
                            <BulkPresetApplyTab isOpen={isOpen} hosts={hosts} onClose={handleClose} onApplyingChange={applyingFor('preset')} />
                        </div>
                    </Dialog.Panel>
                </div>
            </div>
        </Dialog>
    );
}

export default BulkActionsModal;
