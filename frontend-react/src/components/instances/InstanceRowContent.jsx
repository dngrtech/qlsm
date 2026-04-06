import { Zap, Users } from 'lucide-react';
import StatusIndicator from '../StatusIndicator';
import InstanceActionsMenu from '../InstanceActionsMenu';

export default function InstanceRowContent({
    inst,
    host,
    pollableStatuses,
    serverStatus,
    onOpenDetails,
    onOpenLiveStatus,
    onRestart,
    onDelete,
    onStop,
    onStart,
    onToggleLanRate,
    onEditConfig,
    onViewLogs,
    onViewChatLogs,
    onOpenRcon,
}) {
    return (
        <>
            <button
                onClick={() => onOpenDetails(inst.id)}
                className="text-sm font-medium hover:underline text-left truncate pl-2 text-blue-600 dark:text-blue-400"
            >
                {inst.name}
            </button>
            <span
                className="text-[13px] truncate text-theme-secondary"
                style={{ gridColumn: 'span 2' }}
                title={inst.hostname}
            >
                {inst.hostname || '—'}
            </span>
            <span className="font-mono text-[13px] text-theme-secondary">
                {inst.port}
            </span>
            <span
                className={`flex items-center gap-1 text-[12px] font-mono font-semibold ${inst.lan_rate_enabled
                    ? 'text-[var(--accent-warning)]'
                    : 'text-theme-muted'
                    }`}
            >
                {inst.lan_rate_enabled && <Zap size={12} />}
                {inst.lan_rate_enabled ? '99k' : '25k'}
            </span>
            <span className="flex items-center gap-1.5" title="View live status">
                {serverStatus
                    ? (
                        <button
                            onClick={() => onOpenLiveStatus(inst.id)}
                            className={`live-status-toggle flex items-center justify-center gap-1 w-[62px] py-0.5 rounded border text-[11px] font-mono tabular-nums transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)] focus:ring-offset-1 focus:ring-offset-[var(--surface-base)] ${(serverStatus.players?.length ?? 0) > 0
                                    ? 'border-[var(--accent-primary)]/50 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20'
                                    : 'border-theme-strong bg-theme-elevated text-theme-primary hover:bg-black/10 dark:hover:bg-white/10'
                                }`}
                        >
                            <Users size={12} className={(serverStatus.players?.length ?? 0) > 0 ? 'text-[var(--accent-primary)]' : 'text-theme-muted'} />
                            {serverStatus.players?.length ?? 0}/{serverStatus.maxplayers ?? '?'}
                        </button>
                    )
                    : <span className="text-[13px] font-mono text-theme-muted px-2 py-0.5">—</span>
                }
            </span>
            <div className="flex items-center gap-4">
                <StatusIndicator
                    status={inst.status}
                    pollableStatuses={pollableStatuses}
                />
                {['running', 'updated'].includes(
                    inst.status?.toLowerCase()
                ) &&
                    host.ip_address &&
                    inst.port && (
                        <a
                            href={`steam://connect/${host.ip_address}:${inst.port}`}
                            className="btn-connect"
                        >
                            <Zap size={12} /> Connect
                            <span className="connect-tooltip">
                                connect {host.ip_address}:{inst.port}
                            </span>
                        </a>
                    )}
            </div>
            <div className="flex justify-end">
                <InstanceActionsMenu
                    instance={{
                        ...inst,
                        host_id: host.id,
                        host_ip: host.ip_address,
                    }}
                    handleRestart={(id, name) => onRestart(id, name)}
                    handleDelete={(id, name) => onDelete(id, name)}
                    handleStop={(id, name) => onStop(id, name)}
                    handleStart={(id, name) => onStart(id, name)}
                    handleToggleLanRate={() =>
                        onToggleLanRate(
                            inst.id,
                            inst.name,
                            inst.lan_rate_enabled
                        )
                    }
                    onOpenEditConfigModal={(instance) => onEditConfig(instance)}
                    onViewInstanceDetails={() => onOpenDetails(inst.id)}
                    onViewLogs={() => onViewLogs(inst)}
                    onViewChatLogs={() => onViewChatLogs(inst)}
                    onOpenRconConsole={(instance) =>
                        onOpenRcon({
                            ...instance,
                            host_id: host.id,
                            host_ip: host.ip_address,
                        })
                    }
                    POLLABLE_INSTANCE_STATUSES={pollableStatuses}
                />
            </div>
        </>
    );
}
