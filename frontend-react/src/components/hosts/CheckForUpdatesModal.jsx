import React, { useState, useEffect } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { PackageCheck, X, Loader2, AlertTriangle } from 'lucide-react';

const CHANGE_LABEL = { added: 'new', modified: 'updated', removed: 'removed upstream' };

function CheckForUpdatesModal({ isOpen, onClose, onSubmit, host, isChecking, checkResult, checkError }) {
    const [updateCommonPool, setUpdateCommonPool] = useState(false);
    const [selectedFiles, setSelectedFiles] = useState({}); // { [instanceId]: Set<filename> }
    const [restartInstances, setRestartInstances] = useState({}); // { [instanceId]: bool }

    // Default the common pool to selected (when it has changes) and each
    // instance's already-stale files to pre-ticked once a check comes back
    // — newly-added files start unticked, since the operator should opt in
    // to those explicitly (see the preTicked filter below).
    useEffect(() => {
        if (!checkResult) return;
        setUpdateCommonPool((checkResult.common_pool_changes || []).length > 0 && !checkResult.common_pool_error);
        const files = {};
        const restarts = {};
        (checkResult.instances || []).forEach(inst => {
            const changed = (inst.selected_plugin_changes || []).filter(c => c.change !== 'removed');
            // Pre-tick only files this instance already has a stale copy of.
            // Pre-ticking every "added" file too means one click on an
            // 8-instance host copies every new pool plugin to all 8 and
            // restarts them — the operator opts into those explicitly.
            const preTicked = changed.filter(c => c.change === 'modified');
            if (changed.length > 0) {
                files[inst.id] = new Set(preTicked.map(c => c.name));
                restarts[inst.id] = inst.status !== 'STOPPED';
            }
        });
        setSelectedFiles(files);
        setRestartInstances(restarts);
    }, [checkResult]);

    const handleClose = () => {
        setUpdateCommonPool(false);
        setSelectedFiles({});
        setRestartInstances({});
        onClose();
    };

    const toggleFile = (instanceId, name) => {
        setSelectedFiles(prev => {
            const current = new Set(prev[instanceId] || []);
            if (current.has(name)) current.delete(name); else current.add(name);
            return { ...prev, [instanceId]: current };
        });
    };

    const toggleRestart = (instanceId) => {
        setRestartInstances(prev => ({ ...prev, [instanceId]: !prev[instanceId] }));
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        const instances = {};
        Object.entries(selectedFiles).forEach(([id, set]) => {
            if (set.size > 0) instances[id] = Array.from(set);
        });
        const restart_instances = Object.entries(restartInstances)
            .filter(([id, on]) => on && instances[id])
            .map(([id]) => parseInt(id, 10));

        onSubmit({ update_common_pool: updateCommonPool, instances, restart_instances });
    };

    const instancesWithChanges = (checkResult?.instances || []).filter(
        inst => (inst.selected_plugin_changes || []).some(c => c.change !== 'removed')
    );
    const commonPoolChanges = (checkResult?.common_pool_changes || []).filter(c => c.change !== 'removed');
    const hasAnySelection = updateCommonPool || Object.values(selectedFiles).some(s => s && s.size > 0);
    const nothingToUpdate = checkResult && !checkError && commonPoolChanges.length === 0 && instancesWithChanges.length === 0;

    return (
        <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleClose}>
            <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

                <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
                    <div className="flex min-h-full items-center justify-center p-4">
                            <Dialog.Panel transition className="modal-panel w-full max-w-lg transform p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
                                <div className="accent-line-top" />

                                <Dialog.Title
                                    as="h3"
                                    className="relative z-10 flex items-center gap-3 mb-6"
                                >
                                    <span className="status-pulse status-pulse-active" />
                                    <PackageCheck size={18} className="text-[var(--accent-primary)]" />
                                    <span className="font-display text-base font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                                        Check for Updates
                                    </span>
                                    <button type="button" onClick={handleClose} className="ml-auto logs-modal-close-btn">
                                        <X size={18} />
                                    </button>
                                </Dialog.Title>

                                <form onSubmit={handleSubmit}>
                                    <div className="space-y-5 max-h-[60vh] overflow-y-auto scrollbar-thin pr-2">
                                        {isChecking && (
                                            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] py-6 justify-center">
                                                <Loader2 size={16} className="animate-spin" /> Checking ql-assets against {host?.name}...
                                            </div>
                                        )}

                                        {checkError && (
                                            <div className="flex items-start gap-2 text-xs text-red-500 p-3 rounded-lg border border-red-500/30 bg-red-500/5">
                                                <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                                                {checkError}
                                            </div>
                                        )}

                                        {checkResult?.common_pool_error && (
                                            <div className="flex items-start gap-2 text-xs text-amber-500 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
                                                <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                                                Common pool check failed: {checkResult.common_pool_error}
                                            </div>
                                        )}

                                        {nothingToUpdate && (
                                            <p className="text-xs text-[var(--text-muted)] py-6 text-center">
                                                Everything already matches ql-assets — no updates available.
                                            </p>
                                        )}

                                        {commonPoolChanges.length > 0 && (
                                            <div>
                                                <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)] cursor-pointer">
                                                    <input type="checkbox" checked={updateCommonPool} onChange={(e) => setUpdateCommonPool(e.target.checked)} />
                                                    Common plugin pool ({commonPoolChanges.length} changed)
                                                </label>
                                                <ul className="mt-1.5 ml-6 space-y-0.5">
                                                    {commonPoolChanges.map(c => (
                                                        <li key={c.name} className="text-xs font-mono text-[var(--text-muted)]">
                                                            {c.name} <span className="opacity-60">({CHANGE_LABEL[c.change] || c.change})</span>
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}

                                        {instancesWithChanges.map(inst => {
                                            const changed = (inst.selected_plugin_changes || []).filter(c => c.change !== 'removed');
                                            const sel = selectedFiles[inst.id] || new Set();
                                            return (
                                                <div key={inst.id} className="p-3 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-raised)]">
                                                    <div className="flex items-center justify-between mb-2">
                                                        <span className="text-sm font-medium text-[var(--text-primary)]">{inst.name} <span className="text-xs font-mono text-[var(--text-muted)]">:{inst.port}</span></span>
                                                        <label className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] cursor-pointer">
                                                            <input
                                                                type="checkbox"
                                                                checked={!!restartInstances[inst.id]}
                                                                disabled={inst.status === 'STOPPED'}
                                                                onChange={() => toggleRestart(inst.id)}
                                                            />
                                                            restart to apply
                                                        </label>
                                                    </div>
                                                    <ul className="space-y-1">
                                                        {changed.map(c => (
                                                            <li key={c.name}>
                                                                <label className="flex items-center gap-2 text-xs font-mono cursor-pointer">
                                                                    <input type="checkbox" checked={sel.has(c.name)} onChange={() => toggleFile(inst.id, c.name)} />
                                                                    <span className="text-[var(--text-primary)]">{c.name}</span>
                                                                    <span className="text-[var(--text-muted)] opacity-60">({CHANGE_LABEL[c.change] || c.change})</span>
                                                                </label>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            );
                                        })}
                                    </div>

                                    <div className="flex justify-end items-center gap-3 mt-6 pt-4 border-t border-[var(--surface-border)]">
                                        <span className="font-mono text-xs text-[var(--text-muted)] tracking-wide mr-auto hidden sm:inline-flex items-center gap-1.5">
                                            <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-elevated)] border border-[var(--surface-border)] text-[10px] font-bold">Esc</kbd>
                                            to close
                                        </span>
                                        <button type="button" onClick={handleClose} className="btn btn-secondary">
                                            Cancel
                                        </button>
                                        <button type="submit" className="btn btn-primary" disabled={isChecking || !hasAnySelection}>
                                            Update Selected
                                        </button>
                                    </div>
                                </form>
                            </Dialog.Panel>
                    </div>
                </div>
        </Dialog>
    );
}

export default CheckForUpdatesModal;
