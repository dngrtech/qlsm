import React, { useState, useEffect, useCallback } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { PackageCheck, X, Loader2, AlertTriangle } from 'lucide-react';
import { checkPresetPluginUpdates, applyPresetPluginUpdates } from '../../services/api';

const STATUS_LABEL = { outdated: 'update available', current: 'up to date', local: 'not in plugin pool' };

// Check for Updates for one user preset: the plugin copies saved in the
// preset vs the plugin pool for the preset's runtime. Same look as the host
// CheckForUpdatesModal; applying is a synchronous file copy, so the list is
// simply re-checked afterwards.
function PresetPluginUpdatesModal({ isOpen, onClose, preset, onApplied }) {
    const [checking, setChecking] = useState(false);
    const [applying, setApplying] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [message, setMessage] = useState(null);
    const [selected, setSelected] = useState(new Set());

    const presetId = preset?.id;

    const runCheck = useCallback(async () => {
        if (presetId == null) return;
        setChecking(true);
        setError(null);
        try {
            const data = await checkPresetPluginUpdates(presetId);
            setResult(data);
            setSelected(new Set((data.plugin_changes || []).map(c => c.name)));
        } catch (err) {
            setError(err.error?.message || err.message || 'Failed to check plugin updates.');
        } finally {
            setChecking(false);
        }
    }, [presetId]);

    useEffect(() => {
        if (isOpen) {
            setResult(null);
            setMessage(null);
            runCheck();
        }
    }, [isOpen, runCheck]);

    const toggle = (name) => {
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(name)) next.delete(name); else next.add(name);
            return next;
        });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setApplying(true);
        setError(null);
        try {
            const response = await applyPresetPluginUpdates(presetId, { files: Array.from(selected) });
            setMessage(response.message || 'Plugins updated.');
            if (onApplied) onApplied(response.data);
            await runCheck();
        } catch (err) {
            setError(err.error?.message || err.message || 'Failed to apply plugin updates.');
        } finally {
            setApplying(false);
        }
    };

    const plugins = result?.plugins || [];
    const outdatedCount = (result?.plugin_changes || []).length;

    return (
        <Dialog open={isOpen} as="div" className="relative z-50" onClose={onClose}>
            <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

            <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
                <div className="flex min-h-full items-center justify-center p-4">
                    <Dialog.Panel transition className="modal-panel w-full max-w-lg transform p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
                        <div className="accent-line-top" />

                        <Dialog.Title as="h3" className="relative z-10 flex items-center gap-3 mb-6">
                            <span className="status-pulse status-pulse-active" />
                            <PackageCheck size={18} className="text-[var(--accent-primary)]" />
                            <span className="font-display text-base font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                                Preset Plugin Updates
                            </span>
                            <button type="button" onClick={onClose} className="ml-auto logs-modal-close-btn" aria-label="Close">
                                <X size={18} />
                            </button>
                        </Dialog.Title>

                        <form onSubmit={handleSubmit}>
                            <div className="space-y-4 max-h-[60vh] overflow-y-auto scrollbar-thin pr-2">
                                {result && (
                                    <p className="text-xs text-[var(--text-muted)]">
                                        {result.name} ({result.runtime}): plugin files saved in the preset, compared with the plugin pool.
                                    </p>
                                )}

                                {checking && !result && (
                                    <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] py-6 justify-center">
                                        <Loader2 size={16} className="animate-spin" /> Checking {preset?.name} against the plugin pool...
                                    </div>
                                )}

                                {error && (
                                    <div className="flex items-start gap-2 text-xs text-red-500 p-3 rounded-lg border border-red-500/30 bg-red-500/5">
                                        <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                                        {error}
                                    </div>
                                )}

                                {message && (
                                    <p className="text-xs text-green-600 dark:text-green-400">{message}</p>
                                )}

                                {result && plugins.length === 0 && (
                                    <p className="text-xs text-[var(--text-muted)] py-6 text-center">
                                        This preset holds no plugin files of its own.
                                    </p>
                                )}

                                {result && plugins.length > 0 && outdatedCount === 0 && (
                                    <p className="text-xs text-[var(--text-muted)] text-center">
                                        Every plugin in this preset already matches the plugin pool.
                                    </p>
                                )}

                                {plugins.length > 0 && (
                                    <ul className="space-y-1">
                                        {plugins.map(p => (
                                            <li key={p.name}>
                                                <label className={`flex items-center gap-2 text-xs font-mono ${p.status === 'outdated' ? 'cursor-pointer' : ''}`}>
                                                    <input
                                                        type="checkbox"
                                                        checked={selected.has(p.name)}
                                                        disabled={p.status !== 'outdated'}
                                                        onChange={() => toggle(p.name)}
                                                    />
                                                    <span className="text-[var(--text-primary)]">{p.name}</span>
                                                    <span className="text-[var(--text-muted)] opacity-60">({STATUS_LABEL[p.status] || p.status})</span>
                                                </label>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>

                            <div className="flex justify-end items-center gap-3 mt-6 pt-4 border-t border-[var(--surface-border)]">
                                <button type="button" onClick={onClose} className="btn btn-secondary">
                                    Close
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={checking || applying || selected.size === 0}>
                                    {applying ? 'Updating...' : 'Update Selected'}
                                </button>
                            </div>
                        </form>
                    </Dialog.Panel>
                </div>
            </div>
        </Dialog>
    );
}

export default PresetPluginUpdatesModal;
