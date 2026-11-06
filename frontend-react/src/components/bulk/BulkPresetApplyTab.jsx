import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Loader2, AlertTriangle } from 'lucide-react';
import {
    getPresets,
    getPresetKeepCvars,
    previewPresetApply,
    applyPresetToInstance,
    getDeferRestartsSetting,
} from '../../services/api';
import { runtimeLabel } from '../../constants/runtimes';
import PresetCompatibilityDialog from '../presetManager/PresetCompatibilityDialog';
import { FileChange } from '../instances/PendingChangesModal';
import runLimited from './runLimited';

const CONCURRENCY = 4;
// apply-preset's 409 when the rebuilt target no longer matches the preview.
const STALE_HASH = 'Preset or server changed since the preview. Preview again.';
// The plugin selection is what a preset changes; it is never kept.
const NEVER_KEPT = 'qlx_plugins';

// The API sends InstanceStatus values lowercase ("stopped").
const isStopped = (inst) => inst.status?.toLowerCase() === 'stopped';
const isActive = (host) => String(host.status).toUpperCase() === 'ACTIVE';
const errorText = (err, fallback) => err?.error?.message || err?.message || fallback;

function applyErrorText(err) {
    if (err?.error?.message === STALE_HASH) return 'preview again';
    if (err?.status === 409) return 'busy';
    return errorText(err, 'Failed to apply preset');
}

// Items of `after` that are not in `before`.
const newIn = (before, after) => (after || []).filter(x => !(before || []).includes(x));

function BeforeAfter({ label, part }) {
    if (!part) return null;
    const on = newIn(part.before, part.after);
    const off = newIn(part.after, part.before);
    if (on.length === 0 && off.length === 0) return null;
    return (
        <div className="text-xs text-[var(--text-muted)]">
            {label}:
            {on.length > 0 && <span className="ml-1 font-mono text-[var(--accent-primary)]">+{on.join(', +')}</span>}
            {off.length > 0 && <span className="ml-1 font-mono text-[var(--accent-danger)]">-{off.join(', -')}</span>}
        </div>
    );
}

function ServerDiff({ diff }) {
    const admins = diff.admins;
    return (
        <div className="mt-2 ml-6 space-y-1 text-theme-secondary">
            <BeforeAfter label="Plugins" part={diff.plugins} />
            <BeforeAfter label="Hooks" part={diff.hooks} />
            {admins && (admins.add?.length > 0 || admins.remove?.length > 0) && (
                <div className="text-xs text-[var(--text-muted)]">
                    Admins: {admins.add?.length || 0} added, {admins.remove?.length || 0} removed
                </div>
            )}
            {diff.lan_rate && diff.lan_rate.before !== diff.lan_rate.after && (
                <div className="text-xs text-[var(--text-muted)]">
                    LAN rate: {diff.lan_rate.after ? 'on' : 'off'}
                </div>
            )}
            {(diff.files || []).map(file => <FileChange key={file.path} file={file} />)}
        </div>
    );
}

function RowStatus({ row }) {
    if (!row) return null;
    if (row.phase === 'previewing') return <Loader2 size={14} className="animate-spin text-[var(--text-muted)]" />;
    if (row.phase === 'error') return <span className="text-xs text-red-500">{row.reason}</span>;
    if (row.phase === 'blocked') return <span className="text-xs text-amber-500">{row.reason}</span>;
    if (row.awaiting || row.preview.needs_decision) return <span className="text-xs text-amber-500">needs decision</span>;
    if (row.preview.diff?.unchanged) return <span className="text-xs text-[var(--text-muted)]">no changes</span>;
    return null;
}

// Load one preset into many servers: preview each server's diff on the server
// side, ask the runtime compatibility question once per runtime, then apply
// what was previewed. Each server is independent: a failure stays on its row.
function BulkPresetApplyTab({ isOpen, hosts, onClose }) {
    const [hostList, setHostList] = useState([]);
    const [presets, setPresets] = useState([]);
    const [presetsError, setPresetsError] = useState(null);
    const [presetId, setPresetId] = useState('');
    const [ticked, setTicked] = useState(() => new Set());
    const [keepByServer, setKeepByServer] = useState({}); // { [instId]: { phase, entries, error } }
    const [unkept, setUnkept] = useState(() => new Set()); // lower-cased cvar names
    const [added, setAdded] = useState([]);
    const [addInput, setAddInput] = useState('');
    const [restart, setRestart] = useState(true);
    const [rows, setRows] = useState({}); // { [instId]: { phase, preview, body, reason } }
    const [questions, setQuestions] = useState([]); // [{ runtime, compatibility, servers }]
    const [pending, setPending] = useState(0);
    const [applying, setApplying] = useState(false);
    const [results, setResults] = useState({}); // { [instId]: { ok, text } }

    // The servers are the hosts as they were at open: the Servers page polls
    // and replaces its host list, which must not wipe the ticks.
    const hostsRef = useRef(hosts);
    hostsRef.current = hosts;
    const presetRef = useRef(presetId);

    useEffect(() => {
        if (!isOpen) return undefined;
        let cancelled = false;
        setHostList(hostsRef.current || []);
        getPresets()
            .then((list) => { if (!cancelled) setPresets(list || []); })
            .catch((err) => { if (!cancelled) setPresetsError(errorText(err, 'Failed to load presets.')); });
        getDeferRestartsSetting()
            .then((setting) => { if (!cancelled) setRestart(!setting?.enabled); })
            .catch(() => { /* keep the default */ });
        return () => { cancelled = true; };
    }, [isOpen]);

    const tickedServers = useMemo(() => hostList
        .filter(isActive)
        .flatMap(host => (host.instances || []).map(inst => ({ host, inst })))
        .filter(s => ticked.has(s.inst.id)), [hostList, ticked]);

    // keep_cvars of every ticked server, fetched once per server and preset.
    useEffect(() => {
        if (!presetId) return;
        const missing = tickedServers.map(s => s.inst.id).filter(id => !keepByServer[id]);
        if (missing.length === 0) return;
        setKeepByServer(prev => {
            const next = { ...prev };
            missing.forEach(id => { next[id] = { phase: 'loading' }; });
            return next;
        });
        const pid = presetId;
        runLimited(missing, CONCURRENCY, async (id) => {
            let entry;
            try {
                entry = { phase: 'ready', entries: (await getPresetKeepCvars(id, Number(pid))) || [] };
            } catch (err) {
                entry = { phase: 'error', error: errorText(err, 'Failed to load the cvars to keep') };
            }
            if (presetRef.current === pid) setKeepByServer(prev => ({ ...prev, [id]: entry }));
        });
    }, [presetId, tickedServers, keepByServer]);

    // Union over the ticked servers, deduplicated case-insensitively, each
    // entry with every source that named it; then the cvars added here.
    const keepList = useMemo(() => {
        const byName = new Map();
        tickedServers.forEach(({ inst }) => {
            (keepByServer[inst.id]?.entries || []).forEach(({ cvar, sources }) => {
                const key = cvar.toLowerCase();
                if (key === NEVER_KEPT) return;
                const entry = byName.get(key) || { cvar, sources: [] };
                (sources || []).forEach(src => { if (!entry.sources.includes(src)) entry.sources.push(src); });
                byName.set(key, entry);
            });
        });
        added.forEach(cvar => {
            if (!byName.has(cvar.toLowerCase())) byName.set(cvar.toLowerCase(), { cvar, sources: ['added here'] });
        });
        return Array.from(byName.values());
    }, [tickedServers, keepByServer, added]);

    const keepCvars = keepList.filter(e => !unkept.has(e.cvar.toLowerCase())).map(e => e.cvar);
    const keepLoading = tickedServers.some(s => (keepByServer[s.inst.id]?.phase || 'loading') === 'loading');
    const keepErrors = tickedServers.filter(s => keepByServer[s.inst.id]?.phase === 'error');

    // Dropping the failed entries makes the fetch effect load them again.
    const retryKeep = () => {
        setKeepByServer(prev => {
            const next = { ...prev };
            Object.keys(next).forEach(id => { if (next[id]?.phase === 'error') delete next[id]; });
            return next;
        });
    };

    // Any change to what would be sent makes the previews (and their hashes) stale.
    const inputKey = JSON.stringify([presetId, tickedServers.map(s => s.inst.id), keepCvars]);
    useEffect(() => {
        setRows({});
        setResults({});
        setQuestions([]);
    }, [inputKey]);

    // --- selection ---

    const choosePreset = (value) => {
        presetRef.current = value;
        setPresetId(value);
        setKeepByServer({});
        setUnkept(new Set());
    };

    const toggleServer = (id) => {
        setTicked(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const toggleHost = (host) => {
        const ids = (host.instances || []).map(i => i.id);
        const all = ids.every(id => ticked.has(id));
        setTicked(prev => {
            const next = new Set(prev);
            ids.forEach(id => { if (all) next.delete(id); else next.add(id); });
            return next;
        });
    };

    const toggleKeep = (cvar) => {
        const key = cvar.toLowerCase();
        setUnkept(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key); else next.add(key);
            return next;
        });
    };

    const addCvar = () => {
        const name = addInput.trim();
        setAddInput('');
        if (!name || /\s/.test(name) || name.toLowerCase() === NEVER_KEPT) return;
        const key = name.toLowerCase();
        setUnkept(prev => {
            const next = new Set(prev);
            next.delete(key);
            return next;
        });
        if (!keepList.some(e => e.cvar.toLowerCase() === key)) setAdded(prev => [...prev, name]);
    };

    // --- preview ---

    const bodyFor = (accepted) => ({
        preset_id: Number(presetId),
        keep_cvars: keepCvars,
        ...(accepted ? { accepted_replacements: accepted } : {}),
    });

    const previewServers = async (servers, body) => {
        setPending(n => n + 1);
        setRows(prev => {
            const next = { ...prev };
            servers.forEach(s => { next[s.inst.id] = { phase: 'previewing' }; });
            return next;
        });
        const done = {};
        await runLimited(servers, CONCURRENCY, async (s) => {
            let row;
            try {
                row = { phase: 'ready', preview: await previewPresetApply(s.inst.id, body), body };
            } catch (err) {
                row = { phase: 'error', reason: errorText(err, 'Preview failed') };
            }
            done[s.inst.id] = row;
            setRows(prev => ({ ...prev, [s.inst.id]: row }));
        });
        setPending(n => n - 1);
        return done;
    };

    const handlePreview = async () => {
        const servers = tickedServers;
        setResults({});
        setQuestions([]);
        const done = await previewServers(servers, bodyFor());
        // One question per runtime, for every server whose preset plugins get
        // stripped (as the editor asks whenever the list is not empty, so a
        // plugin with no replacement is never dropped silently). The group's
        // dialog lists the stripped entries of all its servers.
        const groups = new Map();
        servers.forEach(s => {
            const row = done[s.inst.id];
            const stripped = row?.phase === 'ready' ? row.preview.compatibility?.stripped || [] : [];
            if (stripped.length === 0) return;
            const runtime = runtimeLabel(s.host.runtime);
            if (!groups.has(runtime)) {
                groups.set(runtime, { runtime, compatibility: { ...row.preview.compatibility, stripped: [] }, servers: [] });
            }
            const group = groups.get(runtime);
            stripped.forEach(entry => {
                if (!group.compatibility.stripped.some(e => e.path === entry.path)) group.compatibility.stripped.push(entry);
            });
            group.servers.push(s);
        });
        const asked = Array.from(groups.values());
        // Not appliable until their runtime's question is answered.
        setRows(prev => {
            const next = { ...prev };
            asked.forEach(q => q.servers.forEach(s => { next[s.inst.id] = { ...next[s.inst.id], awaiting: true }; }));
            return next;
        });
        setQuestions(asked);
    };

    const question = questions[0];

    // The ticked paths (possibly none) are the decision: the re-preview with
    // an explicit accepted_replacements list never needs one again.
    const handleConfirmCompatibility = async (tickedPaths) => {
        const q = question;
        if (!q) return;
        setQuestions(prev => prev.slice(1));
        await previewServers(q.servers, bodyFor(Array.from(tickedPaths || [])));
    };

    const handleCancelCompatibility = () => {
        const q = question;
        if (!q) return;
        setQuestions(prev => prev.slice(1));
        setRows(prev => {
            const next = { ...prev };
            q.servers.forEach(s => {
                next[s.inst.id] = { phase: 'blocked', reason: 'Plugin compatibility not confirmed, not applied' };
            });
            return next;
        });
    };

    // --- apply ---

    const applyJobs = tickedServers.filter(s => {
        const row = rows[s.inst.id];
        const result = results[s.inst.id];
        // A sent row is never sent twice; a stale one needs a new preview first.
        return row?.phase === 'ready'
            && !row.awaiting
            && !row.preview.needs_decision
            && !row.preview.diff?.unchanged
            && !result?.ok
            && !result?.stale;
    });

    const handleApply = async () => {
        setApplying(true);
        await runLimited(applyJobs, CONCURRENCY, async ({ inst }) => {
            const row = rows[inst.id];
            let result;
            try {
                await applyPresetToInstance(inst.id, {
                    ...row.body,
                    restart: restart && !isStopped(inst),
                    preview_hash: row.preview.preview_hash,
                });
                result = { ok: true, text: 'queued' };
            } catch (err) {
                result = {
                    ok: false,
                    stale: err?.error?.message === STALE_HASH,
                    text: applyErrorText(err),
                    title: errorText(err, ''),
                };
            }
            setResults(prev => ({ ...prev, [inst.id]: result }));
        });
        setApplying(false);
    };

    // --- render ---

    const busy = pending > 0 || applying;
    const selectedPreset = presets.find(p => String(p.id) === presetId);

    return (
        <div>
            <fieldset disabled={busy} className="space-y-4 max-h-[60vh] overflow-y-auto scrollbar-thin pr-2">
                {presetsError && (
                    <div className="flex items-start gap-2 text-xs text-red-500">
                        <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                        {presetsError}
                    </div>
                )}

                <select
                    aria-label="Preset"
                    value={presetId}
                    onChange={(e) => choosePreset(e.target.value)}
                    className="select-base"
                >
                    <option value="">Choose a preset...</option>
                    {presets.map(p => (
                        <option key={p.id} value={String(p.id)}>
                            {p.name} ({runtimeLabel(p.runtime)}){p.is_builtin ? ' - built-in' : ''}
                        </option>
                    ))}
                </select>

                {hostList.length === 0 && (
                    <p className="text-xs text-[var(--text-muted)] py-6 text-center">No servers.</p>
                )}

                {hostList.filter(h => (h.instances || []).length > 0).map(host => {
                    const active = isActive(host);
                    const ids = (host.instances || []).map(i => i.id);
                    const n = ids.filter(id => ticked.has(id)).length;
                    return (
                        <div key={host.id} className="p-3 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-raised)]">
                            <div className="flex items-center gap-2">
                                {active && (
                                    <input
                                        type="checkbox"
                                        aria-label={`All servers on ${host.name}`}
                                        ref={(el) => { if (el) el.indeterminate = n > 0 && n < ids.length; }}
                                        checked={n === ids.length}
                                        onChange={() => toggleHost(host)}
                                    />
                                )}
                                <span className="text-sm font-medium text-[var(--text-primary)]">{host.name}</span>
                                <span className="text-xs font-mono text-[var(--text-muted)]">{runtimeLabel(host.runtime)}</span>
                                {!active && <span className="text-xs text-[var(--text-muted)]">Host is {host.status}, not available</span>}
                            </div>
                            {active && (host.instances || []).map(inst => {
                                const row = ticked.has(inst.id) ? rows[inst.id] : null;
                                const result = results[inst.id];
                                const showDiff = row?.phase === 'ready' && !row.awaiting && !row.preview.needs_decision && !row.preview.diff?.unchanged;
                                return (
                                    <div key={inst.id} data-testid={`preset-row-${inst.id}`} className="mt-2 ml-2">
                                        <div className="flex items-center gap-2">
                                            <input
                                                type="checkbox"
                                                aria-label={`Server ${inst.name}`}
                                                checked={ticked.has(inst.id)}
                                                onChange={() => toggleServer(inst.id)}
                                            />
                                            <span className="text-xs text-[var(--text-primary)]">
                                                {inst.name} <span className="font-mono text-[var(--text-muted)]">:{inst.port}</span>
                                            </span>
                                            <RowStatus row={row} />
                                            {result && (
                                                <span
                                                    data-testid={`preset-result-${inst.id}`}
                                                    title={result.title || undefined}
                                                    className={`ml-auto text-xs ${result.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}
                                                >
                                                    {result.text}
                                                </span>
                                            )}
                                        </div>
                                        {showDiff && <ServerDiff diff={row.preview.diff} />}
                                    </div>
                                );
                            })}
                        </div>
                    );
                })}

                {presetId && tickedServers.length > 0 && (
                    <div className="p-3 rounded-lg border border-[var(--surface-border)]">
                        <div className="text-xs font-medium text-[var(--text-primary)] mb-1">
                            Keep each server&apos;s own value of
                        </div>
                        {keepLoading && <Loader2 size={14} className="animate-spin text-[var(--text-muted)]" />}
                        {keepErrors.map(s => (
                            <div key={s.inst.id} className="text-xs text-red-500">{s.inst.name}: {keepByServer[s.inst.id].error}</div>
                        ))}
                        {keepErrors.length > 0 && (
                            <button type="button" className="btn btn-secondary mt-1" onClick={retryKeep}>Retry</button>
                        )}
                        <ul className="space-y-1">
                            {keepList.map(entry => (
                                <li key={entry.cvar.toLowerCase()} className="flex items-center gap-2 text-xs">
                                    <input
                                        type="checkbox"
                                        aria-label={`Keep ${entry.cvar}`}
                                        checked={!unkept.has(entry.cvar.toLowerCase())}
                                        onChange={() => toggleKeep(entry.cvar)}
                                    />
                                    <span className="font-mono text-[var(--text-primary)]">{entry.cvar}</span>
                                    <span className="text-[var(--text-muted)]">{entry.sources.join(', ')}</span>
                                </li>
                            ))}
                        </ul>
                        <div className="flex items-center gap-2 mt-2">
                            <input
                                type="text"
                                aria-label="Add cvar"
                                placeholder="cvar name"
                                value={addInput}
                                onChange={(e) => setAddInput(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCvar(); } }}
                                className="input-base w-auto py-1 text-xs font-mono"
                            />
                            <button type="button" className="btn btn-secondary" onClick={addCvar}>Add</button>
                        </div>
                    </div>
                )}
            </fieldset>

            <div className="flex justify-end items-center gap-3 mt-6 pt-4 border-t border-[var(--surface-border)]">
                <label className="mr-auto flex items-center gap-1.5 text-xs text-[var(--text-muted)] cursor-pointer" title="Stopped servers are never started">
                    <input type="checkbox" checked={restart} disabled={busy} onChange={() => setRestart(r => !r)} />
                    Restart servers to apply
                </label>
                <button type="button" onClick={onClose} className="btn btn-secondary" disabled={applying}>
                    Close
                </button>
                {/* A server whose own cvars did not load would get only the
                    others' as keep_cvars, so it is retried before a preview. */}
                <button
                    type="button"
                    onClick={handlePreview}
                    className="btn btn-secondary"
                    disabled={!selectedPreset || tickedServers.length === 0 || keepLoading || keepErrors.length > 0 || busy}
                >
                    Preview
                </button>
                <button type="button" onClick={handleApply} className="btn btn-primary" disabled={applyJobs.length === 0 || busy}>
                    {applying ? 'Applying...' : 'Apply'}
                </button>
            </div>

            <PresetCompatibilityDialog
                key={question?.runtime || 'none'}
                isOpen={Boolean(question)}
                compatibility={question?.compatibility}
                onConfirm={handleConfirmCompatibility}
                onCancel={handleCancelCompatibility}
            />
        </div>
    );
}

export default BulkPresetApplyTab;
