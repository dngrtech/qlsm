import React, { Fragment, useMemo, useEffect, useRef } from 'react';
import { Transition } from '@headlessui/react';
import { X, Users } from 'lucide-react';
import QlColorString from '../common/QlColorString';
import { useWorkshopPreview } from '../../hooks/useWorkshopPreview';
import standardMapPreviews from '../../constants/standardMapPreviews';

// Team mapping — minqlx sends string values ('red', 'blue', 'free', 'spectator')
// and sometimes numeric values.
const TEAM_NAMES = {
    0: 'Free', free: 'Free',
    1: 'Red', red: 'Red',
    2: 'Blue', blue: 'Blue',
    3: 'Spectator', spectator: 'Spectator',
};

const TEAM_COLORS = {
    0: 'text-theme-primary', free: 'text-theme-primary',
    1: 'text-red-500', red: 'text-red-500',
    2: 'text-blue-400', blue: 'text-blue-400',
    3: 'text-theme-muted', spectator: 'text-theme-muted',
};

// Derived from local minqlx plugins' TEAM_BASED_GAMETYPES and common aliases.
const TEAM_BASED_GAMETYPES = new Set([
    'ca', 'ctf', 'tdm', 'ft', 'ad', 'dom', 'har', '1f', '1fctf', 'ictf', 'wipeout', 'ob', 'obelisk',
]);

const TEAM_SORT_ORDER = { red: 0, blue: 1, spectator: 2, free: 3 };

const TEAM_VALUE_MAP = {
    '0': 'free',
    '1': 'red',
    '2': 'blue',
    '3': 'spectator',
    free: 'free',
    red: 'red',
    blue: 'blue',
    spectator: 'spectator',
    spec: 'spectator',
};

const normalizeTeam = (team) => TEAM_VALUE_MAP[String(team ?? 'free').toLowerCase()] || 'free';

const cleanNameForSort = (name) => String(name || '').replace(/\^\d/g, '').toLocaleLowerCase();

const scoreValue = (player) => {
    const parsed = Number(player?.score);
    return Number.isFinite(parsed) ? parsed : 0;
};

const isTeamBasedGametype = (gametype, players = []) => {
    const type = String(gametype || '').toLowerCase();
    if (TEAM_BASED_GAMETYPES.has(type)) return true;
    return players.some((player) => {
        const team = normalizeTeam(player?.team);
        return team === 'red' || team === 'blue';
    });
};

const teamName = (team) => {
    const normalized = normalizeTeam(team);
    return TEAM_NAMES[normalized] || 'Unknown';
};

const teamColor = (team) => TEAM_COLORS[normalizeTeam(team)] || 'text-theme-muted';

export default function LiveServerStatusModal({ isOpen, onClose, instance, serverStatus }) {
    const panelRef = useRef(null);
    const lastResolvedMapPreviewRef = useRef(null);
    const fallbackPreviewSrc = `${import.meta.env.BASE_URL}map-previews/defaultmap.webp`;

    useEffect(() => {
        if (!isOpen) return;
        const handleEscape = (e) => { if (e.key === 'Escape') onClose(); };
        const handleClickOutside = (e) => {
            if (
                panelRef.current &&
                !panelRef.current.contains(e.target) &&
                !e.target.closest('.live-status-toggle')
            ) {
                onClose();
            }
        };
        document.addEventListener('keydown', handleEscape);
        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('keydown', handleEscape);
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [isOpen, onClose]);

    useEffect(() => {
        if (!isOpen) {
            lastResolvedMapPreviewRef.current = null;
        }
    }, [isOpen]);

    const isTeamMode = useMemo(
        () => isTeamBasedGametype(serverStatus?.gametype, serverStatus?.players || []),
        [serverStatus?.gametype, serverStatus?.players]
    );

    const sortedPlayers = useMemo(() => {
        if (!serverStatus?.players) return [];
        return [...serverStatus.players].sort((a, b) => {
            const teamA = normalizeTeam(a?.team);
            const teamB = normalizeTeam(b?.team);

            if (isTeamMode) {
                const orderA = TEAM_SORT_ORDER[teamA] ?? Number.MAX_SAFE_INTEGER;
                const orderB = TEAM_SORT_ORDER[teamB] ?? Number.MAX_SAFE_INTEGER;
                if (orderA !== orderB) return orderA - orderB;

                if (teamA === 'red' || teamA === 'blue') {
                    const scoreDiff = scoreValue(b) - scoreValue(a);
                    if (scoreDiff !== 0) return scoreDiff;
                    return cleanNameForSort(a?.name).localeCompare(cleanNameForSort(b?.name));
                }

                if (teamA === 'spectator') {
                    return cleanNameForSort(a?.name).localeCompare(cleanNameForSort(b?.name));
                }

                const scoreDiff = scoreValue(b) - scoreValue(a);
                if (scoreDiff !== 0) return scoreDiff;
                return cleanNameForSort(a?.name).localeCompare(cleanNameForSort(b?.name));
            }

            const isSpecA = teamA === 'spectator';
            const isSpecB = teamB === 'spectator';
            if (isSpecA !== isSpecB) return isSpecA ? 1 : -1;

            if (!isSpecA) {
                const scoreDiff = scoreValue(b) - scoreValue(a);
                if (scoreDiff !== 0) return scoreDiff;
            }

            return cleanNameForSort(a?.name).localeCompare(cleanNameForSort(b?.name));
        });
    }, [serverStatus?.players, isTeamMode]);

    const { previewUrl: workshopPreviewUrl, loading: workshopPreviewLoading } = useWorkshopPreview(
        serverStatus?.workshop_item_id,
        isOpen
    );

    const computedMapPreview = (() => {
        const mapName = String(serverStatus?.map || '').trim().toLowerCase();
        const workshopItemId = serverStatus?.workshop_item_id;
        const mappedStandardFilename = mapName ? standardMapPreviews[mapName] : null;

        if (mappedStandardFilename) {
            return {
                src: `${import.meta.env.BASE_URL}map-previews/standard/${mappedStandardFilename}`,
                layout: 'standard',
            };
        }
        if (workshopPreviewUrl) {
            return {
                src: workshopPreviewUrl,
                layout: 'workshop',
            };
        }
        if (workshopItemId && workshopPreviewLoading) return null;
        if (mapName && !workshopItemId) {
            return {
                src: `${import.meta.env.BASE_URL}map-previews/standard/${mapName}.webp`,
                layout: 'standard',
            };
        }
        return {
            src: fallbackPreviewSrc,
            layout: 'workshop',
        };
    })();

    if (computedMapPreview) {
        lastResolvedMapPreviewRef.current = computedMapPreview;
    }
    const mapPreview = computedMapPreview || lastResolvedMapPreviewRef.current || {
        src: fallbackPreviewSrc,
        layout: 'workshop',
    };

    const Field = ({ label, children, className = '' }) => (
        <dl className={`drawer-field ${className}`}>
            <dt>{label}</dt>
            <dd>{children}</dd>
        </dl>
    );

    // Formats seconds into MM:SS
    const formatTime = (totalSeconds) => {
        const m = Math.floor(totalSeconds / 60);
        const s = totalSeconds % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    const LiveClock = ({ startTime }) => {
        const [elapsed, setElapsed] = React.useState(() => Math.max(0, Math.floor(Date.now() / 1000) - startTime));

        useEffect(() => {
            const interval = setInterval(() => {
                setElapsed(Math.max(0, Math.floor(Date.now() / 1000) - startTime));
            }, 1000);
            return () => clearInterval(interval);
        }, [startTime]);

        return <span className="font-mono text-theme-secondary">{formatTime(elapsed)}</span>;
    };

    return (
        <Transition.Root show={isOpen} as={Fragment}>
            <div
                className="fixed inset-x-0 top-0 z-40 overflow-hidden pointer-events-none"
                style={{ bottom: 'var(--footer-height)' }}
            >
                <div
                    className="fixed top-0 right-0 flex max-w-full pointer-events-none"
                    style={{ bottom: 'var(--footer-height)' }}
                >
                    <Transition.Child
                        as={Fragment}
                        enter="transform transition ease-out duration-300"
                        enterFrom="translate-x-full"
                        enterTo="translate-x-0"
                        leave="transform transition ease-in duration-200"
                        leaveFrom="translate-x-0"
                        leaveTo="translate-x-full"
                    >
                        <div ref={panelRef} className="drawer-panel w-[500px] pointer-events-auto flex flex-col">
                            {/* Header */}
                            <div className="drawer-header shrink-0 mt-0" style={{ borderBottom: 'none' }}>
                                <div>
                                    <h2 className="heading-display text-lg text-theme-primary tracking-wider flex items-center gap-2">
                                        <Users size={18} className="text-theme-muted" />
                                        Live Status
                                    </h2>
                                    <p className="font-mono text-xs text-theme-secondary mt-1">
                                        {instance?.name || 'Unknown Instance'}
                                        {instance?.port && ` • Port ${instance.port}`}
                                    </p>
                                </div>
                                <button onClick={onClose} className="p-1.5 rounded-lg text-theme-muted hover:text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                                    <X size={20} />
                                </button>
                            </div>

                            {/* Body */}
                            <div className="drawer-body flex-1 overflow-y-auto scrollbar-thin">
                                {!serverStatus ? (
                                    <div className="flex justify-center items-center h-40">
                                        <p className="text-sm text-theme-muted italic">
                                            No live data — server may be offline or starting up.
                                        </p>
                                    </div>
                                ) : (
                                    <div className="space-y-6 mt-6">
                                        {/* Map Preview */}
                                        <div className={`relative w-full flex items-center justify-center ${mapPreview.layout === 'standard' ? '' : 'h-[251px]'}`}>
                                            <div className={`${mapPreview.layout === 'standard' ? 'w-full aspect-[904/502]' : 'h-full w-fit max-w-full'} overflow-hidden rounded-lg border border-theme-strong`}>
                                                <img
                                                    src={mapPreview.src}
                                                    alt="map preview"
                                                    className={`${mapPreview.layout === 'standard' ? 'w-full h-full object-cover' : 'h-full w-auto max-w-full object-contain'}`}
                                                    onError={(e) => {
                                                        e.currentTarget.onerror = null;
                                                        e.currentTarget.src = fallbackPreviewSrc;
                                                    }}
                                                />
                                            </div>
                                        </div>

                                        {/* General Details */}
                                        <div>
                                            <Field label="Map" className="border-t-0 pt-0"><span className="font-mono text-theme-primary">{serverStatus.map || '—'}</span></Field>
                                            <Field label="Gametype"><span className="uppercase">{serverStatus.gametype || '—'}</span></Field>
                                            <Field label="Factory">{serverStatus.factory || '—'}</Field>
                                            {isTeamMode && (
                                                <Field label="Score">
                                                    <span className="text-red-500 font-semibold">{serverStatus.red_score || 0}</span>
                                                    <span className="text-theme-muted mx-1">-</span>
                                                    <span className="text-blue-400 font-semibold">{serverStatus.blue_score || 0}</span>
                                                </Field>
                                            )}
                                            <Field label="State"><span className="capitalize">{serverStatus.state?.replaceAll('_', ' ') || '—'}</span></Field>
                                            <Field label="Time Elapsed">
                                                {serverStatus.match_start_time ? <LiveClock startTime={serverStatus.match_start_time} /> : '00:00'}
                                            </Field>
                                            <Field label="Players">{serverStatus.players?.length ?? 0} / {serverStatus.maxplayers ?? '?'}</Field>
                                        </div>

                                        {/* Players Table */}
                                        <div>
                                            <div className="drawer-section-label flex justify-between items-end mb-2">
                                                <span>Players</span>
                                            </div>

                                            {sortedPlayers.length > 0 ? (
                                                <div className="border border-theme-strong rounded overflow-hidden">
                                                    <table className="w-full text-left text-[13px]">
                                                        <thead className="bg-theme-elevated text-[11px] font-mono text-theme-muted uppercase tracking-wider">
                                                            <tr>
                                                                <th className="px-3 py-2 font-medium">Name</th>
                                                                <th className="px-3 py-2 font-medium">SteamID</th>
                                                                <th className="px-3 py-2 font-medium">Team</th>
                                                                <th className="px-3 py-2 font-medium text-right">Score</th>
                                                                <th className="px-3 py-2 font-medium text-right">Ping</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-theme border-t border-theme-strong">
                                                            {sortedPlayers.map((p, i) => (
                                                                <tr key={i} className="hover:bg-theme-elevated/50 transition-colors">
                                                                    <td className="px-3 py-2 font-medium truncate max-w-[150px]" title={p.name}>
                                                                        <QlColorString text={p.name || 'Unknown'} className="text-theme-primary" />
                                                                    </td>
                                                                    <td className="px-3 py-2 font-mono text-[11px] text-theme-muted">
                                                                        {p.steam || p.steamid || p.steam_id || '—'}
                                                                    </td>
                                                                    <td className={`px-3 py-2 font-mono text-[11px] ${teamColor(p.team)}`}>
                                                                        {teamName(p.team)}
                                                                    </td>
                                                                    <td className="px-3 py-2 font-mono text-theme-secondary text-right">
                                                                        {p.score ?? 0}
                                                                    </td>
                                                                    <td className="px-3 py-2 font-mono text-theme-secondary text-right">
                                                                        {p.ping ?? '?'}
                                                                    </td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            ) : (
                                                <div className="bg-theme-elevated rounded p-4 text-center border border-theme-strong">
                                                    <p className="text-sm text-theme-muted italic">No players online.</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </Transition.Child>
                </div>
            </div>
        </Transition.Root>
    );
}
