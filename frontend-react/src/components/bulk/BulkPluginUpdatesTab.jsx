import React, { useState, useEffect, useRef } from 'react';
import { Loader2, AlertTriangle } from 'lucide-react';
import {
    checkPluginUpdates,
    applyPluginUpdates,
    getDeferRestartsSetting,
} from '../../services/api';
import runLimited from './runLimited';

const CONCURRENCY = 4;
const CHANGE_LABEL = { added: 'new', modified: 'updated', removed: 'removed upstream' };

// The API sends InstanceStatus values lowercase ("stopped").
const isStopped = (inst) => inst.status?.toLowerCase() === 'stopped';
const errorText = (err, fallback) => err?.error?.message || err?.message || fallback;

const changedFiles = (inst) => (inst.selected_plugin_changes || []).filter(c => c.change !== 'removed');
const poolChanges = (result) => (result.common_pool_changes || []).filter(c => c.change !== 'removed');

// Default selection for a host check: everything outdated ticked; restart
// ticked unless the instance is stopped or Settings > Defer restarts is on.
function defaultHostSelection(result, deferRestarts) {
    const files = {};
    const restart = {};
    (result.instances || []).forEach(inst => {
        const changed = changedFiles(inst);
        if (changed.length > 0) {
            files[inst.id] = new Set(changed.map(c => c.name));
            restart[inst.id] = !isStopped(inst) && !deferRestarts;
        }
    });
    return { pool: poolChanges(result).length > 0 && !result.common_pool_error, files, restart };
}

function ApplyResult({ id, result }) {
    if (!result) return null;
    return (
        <span
            data-testid={`apply-result-${id}`}
            className={`text-xs ${result.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}
        >
            {result.text}
        </span>
    );
}

// Update plugins on every ACTIVE host in one place. Presets are updated on
// the Presets page. Each host is independent: a failure is shown on its row only.
function BulkPluginUpdatesTab({ isOpen, hosts, onClose }) {
    const [loading, setLoading] = useState(false);
    const [hostRows, setHostRows] = useState({}); // { [hostId]: { phase, reason, result } }
    const [hostSel, setHostSel] = useState({}); // { [hostId]: { pool, files, restart } }
    const [applying, setApplying] = useState(false);
    const [applyResults, setApplyResults] = useState({}); // { 'host-1': { ok, text } }

    // The checks run on the Check button only (each is an Ansible run), on the
    // hosts as they were then: the Servers page polls and replaces its host
    // list, which must not wipe the ticks.
    const hostsRef = useRef(hosts);
    hostsRef.current = hosts;
    const openRef = useRef(0); // bumped on close: the running checks stop

    const runChecks = async (isCancelled) => {
        const list = hostsRef.current || [];
        const rows = {};
        const active = [];
        list.forEach(h => {
            if (String(h.status).toUpperCase() === 'ACTIVE') {
                rows[h.id] = { phase: 'checking' };
                active.push(h);
            } else {
                rows[h.id] = { phase: 'skipped', reason: `Host is ${h.status}, not checked` };
            }
        });
        setHostRows(rows);
        setHostSel({});
        setApplyResults({});
        setLoading(true);

        let deferRestarts = false;
        try {
            const setting = await getDeferRestartsSetting();
            deferRestarts = Boolean(setting?.enabled);
        } catch { /* keep the default */ }
        if (isCancelled()) return;

        await runLimited(active, CONCURRENCY, async (host) => {
            if (isCancelled()) return;
            try {
                const response = await checkPluginUpdates(host.id);
                if (isCancelled()) return;
                const result = response.data || {};
                setHostRows(prev => ({ ...prev, [host.id]: { phase: 'ready', result } }));
                setHostSel(prev => ({ ...prev, [host.id]: defaultHostSelection(result, deferRestarts) }));
            } catch (err) {
                if (isCancelled()) return;
                setHostRows(prev => ({ ...prev, [host.id]: { phase: 'error', reason: errorText(err, 'Failed to check for updates') } }));
            }
        });

        if (!isCancelled()) setLoading(false);
    };

    // Closing the dialog drops the results: they are stale by the next open.
    useEffect(() => {
        if (isOpen) return;
        openRef.current += 1;
        setHostRows({});
        setHostSel({});
        setApplyResults({});
        setLoading(false);
    }, [isOpen]);

    useEffect(() => () => { openRef.current += 1; }, []);

    const handleCheck = () => {
        const open = openRef.current;
        runChecks(() => openRef.current !== open);
    };

    // --- selection helpers ---

    const toggleHostFile = (hostId, instId, name) => {
        setHostSel(prev => {
            const cur = prev[hostId];
            const set = new Set(cur.files[instId] || []);
            if (set.has(name)) set.delete(name); else set.add(name);
            return { ...prev, [hostId]: { ...cur, files: { ...cur.files, [instId]: set } } };
        });
    };

    const toggleHostRestart = (hostId, instId) => {
        setHostSel(prev => {
            const cur = prev[hostId];
            return { ...prev, [hostId]: { ...cur, restart: { ...cur.restart, [instId]: !cur.restart[instId] } } };
        });
    };

    const toggleHostPool = (hostId) => {
        setHostSel(prev => ({ ...prev, [hostId]: { ...prev[hostId], pool: !prev[hostId].pool } }));
    };

    const hostIsAllSelected = (hostId) => {
        const row = hostRows[hostId];
        const sel = hostSel[hostId];
        if (!row?.result || !sel) return false;
        const poolOk = poolChanges(row.result).length === 0 || row.result.common_pool_error || sel.pool;
        const instOk = (row.result.instances || []).every(inst => {
            const changed = changedFiles(inst);
            return changed.every(c => sel.files[inst.id]?.has(c.name));
        });
        return Boolean(poolOk) && instOk;
    };

    const hostIsPartial = (hostId) => {
        const sel = hostSel[hostId];
        if (!sel || hostIsAllSelected(hostId)) return false;
        return sel.pool || Object.values(sel.files).some(set => set.size > 0);
    };

    const toggleHostAll = (hostId) => {
        const row = hostRows[hostId];
        if (hostIsAllSelected(hostId)) {
            setHostSel(prev => ({ ...prev, [hostId]: { ...prev[hostId], pool: false, files: {} } }));
            return;
        }
        setHostSel(prev => {
            const base = defaultHostSelection(row.result, false);
            return { ...prev, [hostId]: { pool: base.pool, files: base.files, restart: prev[hostId].restart } };
        });
    };

    const toggleInstanceAll = (hostId, inst) => {
        setHostSel(prev => {
            const cur = prev[hostId];
            const names = changedFiles(inst).map(c => c.name);
            const full = names.every(n => cur.files[inst.id]?.has(n));
            return { ...prev, [hostId]: { ...cur, files: { ...cur.files, [inst.id]: full ? new Set() : new Set(names) } } };
        });
    };

    // --- apply ---

    const buildHostPayload = (hostId) => {
        const sel = hostSel[hostId];
        if (!sel) return null;
        const instances = {};
        Object.entries(sel.files).forEach(([id, set]) => {
            if (set.size > 0) instances[id] = Array.from(set);
        });
        if (!sel.pool && Object.keys(instances).length === 0) return null;
        const restart_instances = Object.entries(sel.restart)
            .filter(([id, on]) => on && instances[id])
            .map(([id]) => parseInt(id, 10));
        return { update_common_pool: sel.pool, instances, restart_instances };
    };

    const hostJobs = (hosts || [])
        .filter(h => hostRows[h.id]?.phase === 'ready')
        .map(h => ({ host: h, payload: buildHostPayload(h.id) }))
        .filter(j => j.payload);

    const handleApply = async () => {
        setApplying(true);
        setApplyResults({});
        const put = (key, value) => setApplyResults(prev => ({ ...prev, [key]: value }));
        await runLimited(hostJobs, CONCURRENCY, async ({ host, payload }) => {
            try {
                await applyPluginUpdates(host.id, payload);
                put(`host-${host.id}`, { ok: true, text: 'queued' });
                // Done: untick so a second click never sends this host again.
                setHostSel(prev => ({ ...prev, [host.id]: { ...prev[host.id], pool: false, files: {} } }));
            } catch (err) {
                put(`host-${host.id}`, { ok: false, text: errorText(err, 'Failed to apply plugin updates') });
            }
        });
        setApplying(false);
    };

    // --- render ---

    const hostList = hosts || [];
    const checked = Object.keys(hostRows).length > 0;

    return (
        <div>
            <div className="space-y-4 max-h-[60vh] overflow-y-auto scrollbar-thin pr-2">
                {hostList.length === 0 && !loading && (
                    <p className="text-xs text-[var(--text-muted)] py-6 text-center">No hosts to check.</p>
                )}
                {hostList.length > 0 && !checked && (
                    <p className="text-xs text-[var(--text-muted)] py-6 text-center">
                        Check every Active host for plugin updates. Each check takes a few seconds per host.
                    </p>
                )}

                {hostList.map(host => {
                    const row = hostRows[host.id];
                    if (!row) return null;
                    const result = row.result;
                    const pool = result ? poolChanges(result) : [];
                    const instances = result ? (result.instances || []).filter(i => changedFiles(i).length > 0) : [];
                    const sel = hostSel[host.id];
                    const upToDate = row.phase === 'ready' && pool.length === 0 && instances.length === 0;
                    return (
                        <div key={host.id} className="p-3 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-raised)]">
                            <div className="flex items-center gap-2">
                                {row.phase === 'ready' && !upToDate && (
                                    <input
                                        type="checkbox"
                                        aria-label={`Select all for ${host.name}`}
                                        ref={(el) => { if (el) el.indeterminate = hostIsPartial(host.id); }}
                                        checked={hostIsAllSelected(host.id)}
                                        onChange={() => toggleHostAll(host.id)}
                                    />
                                )}
                                <span className="text-sm font-medium text-[var(--text-primary)]">{host.name}</span>
                                {row.phase === 'checking' && <Loader2 size={14} className="animate-spin text-[var(--text-muted)]" />}
                                {upToDate && <span className="text-xs text-[var(--text-muted)]">up to date</span>}
                                <span className="ml-auto"><ApplyResult id={`host-${host.id}`} result={applyResults[`host-${host.id}`]} /></span>
                            </div>

                            {(row.phase === 'skipped' || row.phase === 'error') && (
                                <div className={`flex items-start gap-2 text-xs mt-2 ${row.phase === 'error' ? 'text-red-500' : 'text-[var(--text-muted)]'}`}>
                                    <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                                    <span>{row.reason}</span>
                                </div>
                            )}

                            {result?.common_pool_error && (
                                <div className="flex items-start gap-2 text-xs text-amber-500 mt-2">
                                    <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                                    Common pool check failed: {result.common_pool_error}
                                </div>
                            )}

                            {sel && pool.length > 0 && (
                                <div className="mt-2">
                                    <label className="flex items-center gap-2 text-xs font-medium text-[var(--text-primary)] cursor-pointer">
                                        <input type="checkbox" checked={sel.pool} onChange={() => toggleHostPool(host.id)} />
                                        Common plugin pool ({pool.length} changed)
                                    </label>
                                    <ul className="mt-1 ml-6 space-y-0.5">
                                        {pool.map(c => (
                                            <li key={c.name} className="text-xs font-mono text-[var(--text-muted)]">
                                                {c.name} <span className="opacity-60">({CHANGE_LABEL[c.change] || c.change})</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {sel && instances.map(inst => (
                                <div key={inst.id} className="mt-2 ml-2">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="flex items-center gap-2 text-xs font-medium text-[var(--text-primary)]">
                                            <input
                                                type="checkbox"
                                                aria-label={`Select all for instance ${inst.name}`}
                                                ref={(el) => {
                                                    if (!el) return;
                                                    const n = changedFiles(inst).filter(c => sel.files[inst.id]?.has(c.name)).length;
                                                    el.indeterminate = n > 0 && n < changedFiles(inst).length;
                                                }}
                                                checked={changedFiles(inst).every(c => sel.files[inst.id]?.has(c.name))}
                                                onChange={() => toggleInstanceAll(host.id, inst)}
                                            />
                                            <span>{inst.name} <span className="font-mono text-[var(--text-muted)]">:{inst.port}</span></span>
                                        </span>
                                        <label className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] cursor-pointer" title="Unticked: the files are synced now and the instance shows Updated until its next restart">
                                            <input
                                                type="checkbox"
                                                checked={!!sel.restart[inst.id]}
                                                disabled={isStopped(inst)}
                                                onChange={() => toggleHostRestart(host.id, inst.id)}
                                            />
                                            restart to apply
                                        </label>
                                    </div>
                                    <ul className="space-y-1">
                                        {changedFiles(inst).map(c => (
                                            <li key={c.name}>
                                                <label className="flex items-center gap-2 text-xs font-mono cursor-pointer">
                                                    <input
                                                        type="checkbox"
                                                        checked={!!sel.files[inst.id]?.has(c.name)}
                                                        onChange={() => toggleHostFile(host.id, inst.id, c.name)}
                                                    />
                                                    <span className="text-[var(--text-primary)]">{c.name}</span>
                                                    <span className="text-[var(--text-muted)] opacity-60">({CHANGE_LABEL[c.change] || c.change})</span>
                                                </label>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    );
                })}

                {loading && (
                    <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] py-2 justify-center">
                        <Loader2 size={14} className="animate-spin" /> Checking hosts...
                    </div>
                )}
            </div>

            <div className="flex justify-end items-center gap-3 mt-6 pt-4 border-t border-[var(--surface-border)]">
                <button type="button" onClick={onClose} className="btn btn-secondary">
                    Close
                </button>
                <button type="button" onClick={handleCheck} className="btn btn-secondary" disabled={loading || applying || hostList.length === 0}>
                    {checked ? 'Check again' : 'Check for updates'}
                </button>
                <button type="button" onClick={handleApply} className="btn btn-primary" disabled={loading || applying || hostJobs.length === 0}>
                    {applying ? 'Updating...' : 'Update Selected'}
                </button>
            </div>
        </div>
    );
}

export default BulkPluginUpdatesTab;
