import React from 'react';
// "N servers on M hosts will restart" before an action that restarts
// running servers; null when it restarts none.
export function restartSummary(servers) {
    const hosts = new Set(servers.map(s => s.hostId));
    if (servers.length === 0) return null;
    const n = servers.length;
    const m = hosts.size;
    return `${n} server${n === 1 ? '' : 's'} on ${m} host${m === 1 ? '' : 's'} will restart.`;
}

export function ConfirmRestart({ text, onConfirm, onCancel }) {
    return (
        <div role="alertdialog" aria-label="Confirm restart" className="flex flex-wrap items-center gap-2 w-full text-xs text-amber-500">
            <span className="mr-auto">{text}</span>
            <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
            <button type="button" className="btn btn-primary" onClick={onConfirm}>Restart and apply</button>
        </div>
    );
}
