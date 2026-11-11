import React, { useState, useEffect } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { ActivitySquare, X } from 'lucide-react';

const DEFAULTS = {
    interval: 10,
    recvq_threshold: 8192,
    strikes: 3,
    grace: 90,
    rate_max: 3,
    rate_window: 900,
    forensics: true,
    dryrun: false,
};

function HostWatchdogModal({ isOpen, onClose, onSubmit, host }) {
    const [enabled, setEnabled] = useState(false);
    const [config, setConfig] = useState(DEFAULTS);

    useEffect(() => {
        if (isOpen && host) {
            setEnabled(!!host.watchdog_enabled);
            let saved = {};
            if (host.watchdog_config) {
                try { saved = JSON.parse(host.watchdog_config); } catch { saved = {}; }
            }
            setConfig({ ...DEFAULTS, ...saved });
        }
    }, [isOpen, host]);

    const handleClose = () => onClose();

    const setField = (key, value) => setConfig((prev) => ({ ...prev, [key]: value }));

    const handleSubmit = (e) => {
        e.preventDefault();
        onSubmit(host?.id, enabled, config);
        handleClose();
    };

    const numberField = (key, label, min, max) => (
        <div>
            <label htmlFor={`watchdog-${key}`} className="label-tech mb-1.5 block">{label}</label>
            <input
                type="number"
                id={`watchdog-${key}`}
                min={min}
                max={max}
                value={config[key]}
                onChange={(e) => setField(key, parseInt(e.target.value, 10) || 0)}
                className="input-base w-full font-mono"
            />
        </div>
    );

    return (
        <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleClose}>
            <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

            <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
                <div className="flex min-h-full items-center justify-center p-4">
                    <Dialog.Panel transition className="modal-panel w-full max-w-[520px] transform p-6 text-left align-middle transition-all transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
                        <div className="accent-line-top" />

                        <Dialog.Title as="h3" className="relative z-10 flex items-center gap-3 mb-6">
                            <span className="status-pulse status-pulse-active" />
                            <ActivitySquare size={18} className="text-[var(--accent-primary)]" />
                            <span className="font-display text-base font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                                Configure ql-watchdog
                            </span>
                            <button type="button" onClick={handleClose} className="ml-auto logs-modal-close-btn">
                                <X size={18} />
                            </button>
                        </Dialog.Title>

                        <form onSubmit={handleSubmit}>
                            <div className="space-y-6">
                                <p className="text-sm text-[var(--text-muted)]">
                                    Detects an instance on <strong>{host?.name}</strong> whose game has frozen
                                    or crashed without exiting, and restarts only that instance via systemctl.
                                </p>

                                <div className="flex items-center justify-between p-3 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-raised)]">
                                    <span className="text-sm font-medium text-[var(--text-primary)]">Enabled</span>
                                    <button
                                        type="button"
                                        onClick={() => setEnabled((v) => !v)}
                                        className="neu-toggle"
                                        aria-pressed={enabled}
                                    >
                                        <span className="sr-only">Toggle ql-watchdog</span>
                                        <span className={`neu-toggle__track ${enabled ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                            <span className={`neu-toggle__knob ${enabled ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                                        </span>
                                    </button>
                                </div>

                                {enabled && (
                                    <div className="space-y-5 border-t border-[var(--surface-border)] pt-5">
                                        <div className="grid grid-cols-2 gap-4">
                                            {numberField('interval', 'Check Interval (s)', 2, 3600)}
                                            {numberField('recvq_threshold', 'Recv-Q Threshold (bytes)', 0, 10000000)}
                                            {numberField('strikes', 'Strikes Before Restart', 1, 100)}
                                            {numberField('grace', 'Boot Grace Period (s)', 30, 3600)}
                                            {numberField('rate_max', 'Max Restarts / Window', 1, 100)}
                                            {numberField('rate_window', 'Rate Limit Window (s)', 60, 86400)}
                                        </div>

                                        <div className="flex items-center justify-between">
                                            <span className="text-sm text-[var(--text-secondary)]">
                                                Capture gdb/py-spy forensics before restarting
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => setField('forensics', !config.forensics)}
                                                className="neu-toggle neu-toggle--sm"
                                                aria-pressed={config.forensics}
                                            >
                                                <span className="sr-only">Toggle forensics capture</span>
                                                <span className={`neu-toggle__track ${config.forensics ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                                    <span className={`neu-toggle__knob ${config.forensics ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                                                </span>
                                            </button>
                                        </div>

                                        <div className="flex items-center justify-between">
                                            <span className="text-sm text-[var(--text-secondary)]">
                                                Dry-run (detect + log only, never restart)
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => setField('dryrun', !config.dryrun)}
                                                className="neu-toggle neu-toggle--sm"
                                                aria-pressed={config.dryrun}
                                            >
                                                <span className="sr-only">Toggle dry-run</span>
                                                <span className={`neu-toggle__track ${config.dryrun ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                                    <span className={`neu-toggle__knob ${config.dryrun ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                                                </span>
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="flex justify-end items-center gap-3 mt-8 pt-4 border-t border-[var(--surface-border)]">
                                <button type="button" onClick={handleClose} className="btn btn-secondary">
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    Save
                                </button>
                            </div>
                        </form>
                    </Dialog.Panel>
                </div>
            </div>
        </Dialog>
    );
}

export default HostWatchdogModal;
