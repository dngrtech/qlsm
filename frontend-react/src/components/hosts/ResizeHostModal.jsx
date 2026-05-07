import React, { useEffect, useState } from 'react';
import { Dialog } from '@headlessui/react';
import { AlertTriangle, ArrowUpCircle, X } from 'lucide-react';
import { getPlan, getUpgradeOptions } from '../../utils/providerData';
import FloatingListbox from '../common/FloatingListbox';

function ResizeHostModal({ isOpen, onClose, onSubmit, host, error, isSubmitting = false }) {
    const [selectedPlan, setSelectedPlan] = useState('');

    useEffect(() => {
        if (!isOpen) setSelectedPlan('');
    }, [isOpen]);

    if (!host) return null;

    const currentPlanId = host.machine_size;
    const currentPlan = getPlan('vultr', currentPlanId);
    const upgradeOptions = getUpgradeOptions('vultr', currentPlanId, host.region);
    const noUpgrades = upgradeOptions.length === 0;

    const handleClose = () => {
        setSelectedPlan('');
        onClose();
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!selectedPlan || isSubmitting) return;
        onSubmit(selectedPlan);
    };

    return (
        <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleClose}>
            <Dialog.Backdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

                <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
                    <div className="flex min-h-full items-center justify-center p-4">
                            <Dialog.Panel transition className="modal-panel w-full max-w-md transform p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
                                <div className="accent-line-top" />

                                <Dialog.Title as="h3" className="relative z-10 flex items-center gap-3 mb-6">
                                    <span className="status-pulse status-pulse-active" />
                                    <ArrowUpCircle size={18} className="text-[var(--accent-primary)]" />
                                    <span className="font-display text-base font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                                        Resize Host
                                    </span>
                                    <button
                                        type="button"
                                        onClick={handleClose}
                                        className="ml-auto logs-modal-close-btn"
                                        aria-label="Close"
                                    >
                                        <X size={18} />
                                    </button>
                                </Dialog.Title>

                                <form onSubmit={handleSubmit} className="space-y-5">
                                    <div>
                                        <label className="label-tech mb-1.5 block">Host</label>
                                        <p className="text-sm font-mono text-[var(--text-primary)]">{host.name}</p>
                                    </div>

                                    <div>
                                        <label className="label-tech mb-1.5 block">Current Plan</label>
                                        <p className="text-sm text-[var(--text-secondary)]">
                                            {currentPlan ? currentPlan.name : currentPlanId}
                                        </p>
                                    </div>

                                    <div>
                                        <label htmlFor="resize-new-plan" className="label-tech mb-1.5 block">
                                            New Plan
                                        </label>
                                        {noUpgrades ? (
                                            <p className="text-sm italic text-[var(--text-muted)]">
                                                No upgrades available for this plan family.
                                            </p>
                                        ) : (
                                            <FloatingListbox
                                                value={selectedPlan}
                                                onChange={setSelectedPlan}
                                                options={upgradeOptions}
                                                disabled={isSubmitting}
                                                getOptionKey={(opt) => opt.id}
                                                getOptionDisplay={(opt) => opt.name}
                                                getSelectedDisplay={(val, opts) => {
                                                    const found = opts.find(o => o.id === val);
                                                    return found ? found.name : 'Select a plan...';
                                                }}
                                                placeholder="Select a plan..."
                                                noOptionsMessage="No upgrade plans available."
                                            />
                                        )}
                                    </div>

                                    <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
                                        <AlertTriangle size={16} className="mt-0.5 flex-shrink-0 text-amber-500" />
                                        <p className="text-xs leading-5 text-[var(--text-secondary)]">
                                            The host will reboot during the resize. Quake Live instances will restart automatically.
                                            Note: downgrading is not supported by Vultr.
                                        </p>
                                    </div>

                                    {error && (
                                        <div className="alert-error">
                                            <p className="text-sm">{error}</p>
                                        </div>
                                    )}

                                    <div className="flex justify-end items-center gap-3 pt-4 border-t border-[var(--surface-border)]">
                                        <button type="button" onClick={handleClose} className="btn btn-secondary">
                                            Cancel
                                        </button>
                                        <button
                                            type="submit"
                                            disabled={!selectedPlan || noUpgrades || isSubmitting}
                                            className="btn btn-primary"
                                        >
                                            {isSubmitting ? 'Resizing...' : 'Resize'}
                                        </button>
                                    </div>
                                </form>
                            </Dialog.Panel>
                    </div>
                </div>
        </Dialog>
    );
}

export default ResizeHostModal;
