import { useState, useMemo } from 'react';
import { copyToClipboard } from '../utils/clipboard';
import { ChevronDown, ChevronUp, ChevronRight, Plus, Copy, Check, MapPin, GripVertical } from 'lucide-react';
import { useServers } from '../hooks/useServers';
import StatusIndicator from '../components/StatusIndicator';
import ConfirmationModal from '../components/ConfirmationModal';
import HostDetailDrawer from '../components/hosts/HostDetailDrawer';
import AddHostModal from '../components/hosts/AddHostModal';
import AddInstanceModal from '../components/instances/AddInstanceModal';
import InstanceDetailsModal from '../components/instances/InstanceDetailsModal';
import EditInstanceConfigModal from '../components/instances/EditInstanceConfigModal';
import ViewLogsModal from '../components/instances/ViewLogsModal';
import RconConsoleModal from '../components/RconConsoleModal';
import HostActionsMenu from '../components/HostActionsMenu';
import SortableInstanceList from '../components/instances/SortableInstanceList';
import InstanceRowContent from '../components/instances/InstanceRowContent';
import { POLLABLE_HOST_STATUSES, POLLABLE_INSTANCE_STATUSES } from '../hooks/useServers';
import { formatVultrRegion } from '../utils/formatters';
import { useNotification } from '../components/NotificationProvider';
import { useQlfilterActions } from '../hooks/useQlfilterActions';
import InfoTooltip from '../components/common/InfoTooltip';
import { useHostRestart } from '../hooks/useHostRestart';
import LiveServerStatusModal from '../components/instances/LiveServerStatusModal';
import { useInstanceLanRate } from '../hooks/useInstanceLanRate';
import { useViewLogs } from '../hooks/useViewLogs';
import { useViewChatLogs } from '../hooks/useViewChatLogs';
import { useInstanceStopStart } from '../hooks/useInstanceStopStart';
import ViewChatLogsModal from '../components/instances/ViewChatLogsModal';
import { useInstanceOrder } from '../hooks/useInstanceOrder';
import { useHostOrder } from '../hooks/useHostOrder';
import SortableHostList from '../components/hosts/SortableHostList';
import { useWorkshopUpdate } from '../hooks/useWorkshopUpdate';
import { useHostAutoRestart } from '../hooks/useHostAutoRestart';
import ForceUpdateWorkshopModal from '../components/hosts/ForceUpdateWorkshopModal';
import HostAutoRestartScheduleModal from '../components/hosts/HostAutoRestartScheduleModal';
import { useServerStatus } from '../hooks/useServerStatus';

export default function ServersPage() {
    const { addNotification, showSuccess, showError } = useNotification();
    const {
        serversData, stats, loading, error,
        toggleExpand, expandAll, collapseAll, refreshData,
        deleteModal, requestDeleteHost, requestDeleteInstance, confirmDelete, closeDeleteModal,
        restartModal, requestRestartInstance, confirmRestart, closeRestartModal,
    } = useServers();

    const [selectedHostId, setSelectedHostId] = useState(null);
    const [isHostDrawerOpen, setIsHostDrawerOpen] = useState(false);
    const [isAddHostModalOpen, setIsAddHostModalOpen] = useState(false);
    const [isAddInstanceModalOpen, setIsAddInstanceModalOpen] = useState(false);
    const [addInstanceModalHostId, setAddInstanceModalHostId] = useState(null);
    const [selectedInstanceId, setSelectedInstanceId] = useState(null);
    const [isInstanceDetailsOpen, setIsInstanceDetailsOpen] = useState(false);
    const [isEditConfigOpen, setIsEditConfigOpen] = useState(false);
    const [selectedInstanceForConfig, setSelectedInstanceForConfig] = useState(null);
    const [copiedIp, setCopiedIp] = useState(null);
    const [isLiveStatusOpen, setIsLiveStatusOpen] = useState(false);
    const [selectedLiveStatusInstance, setSelectedLiveStatusInstance] = useState(null);

    const { hostForRestart, isRestartModalOpen: isHostRestartModalOpen, requestRestart: handleRequestHostRestart, confirmRestart: confirmHostRestart, closeRestartModal: closeHostRestartModal } = useHostRestart(showSuccess, showError, () => refreshData(false));
    const { selectedInstanceForLogs, isViewLogsModalOpen, openViewLogs: handleViewLogs, closeViewLogs: closeViewLogsModal } = useViewLogs();
    const { selectedInstanceForChatLogs, isViewChatLogsModalOpen, openViewChatLogs: handleViewChatLogs, closeViewChatLogs: closeViewChatLogsModal } = useViewChatLogs(); // Instantiate hook
    const { lanRateAction, isLanRateModalOpen, requestToggleLanRate, confirmToggleLanRate, closeLanRateModal } = useInstanceLanRate(showSuccess, showError, () => refreshData(false));
    const { handleQlfilterAction } = useQlfilterActions(showSuccess, showError, () => refreshData(false));
    const { stopStartAction, isStopStartModalOpen, requestStop, requestStart, confirmStopStart, closeStopStartModal } = useInstanceStopStart(showSuccess, showError, () => refreshData(false));
    const { isWorkshopModalOpen, hostForWorkshopUpdate, openWorkshopModal, closeWorkshopModal, handleWorkshopUpdateSubmit } = useWorkshopUpdate(showSuccess, showError, () => refreshData(false));
    const { isAutoRestartModalOpen, hostForAutoRestart, openAutoRestartModal, closeAutoRestartModal, handleAutoRestartSubmit } = useHostAutoRestart(showSuccess, showError, () => refreshData(false));
    const serverStatusMap = useServerStatus();

    // RCON Console state — store ID + host_id, re-derive from live data
    const [rconKey, setRconKey] = useState(null); // { instanceId, hostId }
    const [isRconConsoleOpen, setIsRconConsoleOpen] = useState(false);
    const handleOpenRconConsole = (instance) => { setRconKey({ instanceId: instance.id, hostId: instance.host_id }); setIsRconConsoleOpen(true); };
    const handleCloseRconConsole = () => { setIsRconConsoleOpen(false); setRconKey(null); };
    const rconInstance = useMemo(() => {
        if (!rconKey) return null;
        const host = serversData.find(h => h.id === rconKey.hostId);
        if (!host) return null;
        const inst = host.instances.find(i => i.id === rconKey.instanceId);
        return inst ? { ...inst, host_id: host.id, host_ip: host.ip_address } : null;
    }, [serversData, rconKey]);

    const allExpanded = useMemo(() => serversData.length > 0 && serversData.every(h => h.expanded), [serversData]);

    const copyToClipboard = (ip, hostId, e) => {
        e?.stopPropagation();
        copyToClipboard(ip).then(() => {
            setCopiedIp(hostId);
            addNotification('IP copied to clipboard', 'success');
            setTimeout(() => setCopiedIp(null), 2000);
        });
    };

    const handleOpenHostDrawer = (hostId) => { setIsInstanceDetailsOpen(false); setSelectedInstanceId(null); setSelectedHostId(hostId); setIsHostDrawerOpen(true); };
    const handleOpenInstanceDetails = (instanceId) => { setIsHostDrawerOpen(false); setSelectedHostId(null); setSelectedInstanceId(instanceId); setIsInstanceDetailsOpen(true); };
    const handleOpenEditConfig = (instance) => { setSelectedInstanceForConfig(instance); setIsEditConfigOpen(true); };
    const handleOpenLiveStatus = (instanceId) => {
        const host = serversData.find(h => h.instances.some(i => i.id === instanceId));
        if (host) {
            const inst = host.instances.find(i => i.id === instanceId);
            setSelectedLiveStatusInstance(inst);
            setIsLiveStatusOpen(true);
        }
    };

    const { getOrderedInstances, setInstanceOrder } = useInstanceOrder();
    const { getOrderedHosts, setHostOrder } = useHostOrder();

    const currentHostForDrawer = selectedHostId ? serversData.find(h => h.id === selectedHostId) : null;

    if (error) {
        return (
            <div className="max-w-[1280px] mx-auto py-8 px-8">
                <div className="alert-error">
                    <p className="font-medium">Failed to load servers</p>
                    <p className="text-sm mt-1">{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-[1280px] mx-auto py-8 px-8">
            {/* Page Header */}
            <div className="flex items-end justify-between mb-7">
                <div>
                    <h1 className="heading-display text-[32px] text-theme-primary tracking-wider">Servers</h1>
                    <div className="flex gap-5 mt-3">
                        <span className="flex items-center gap-1.5 text-sm font-medium text-theme-secondary">
                            <span className="w-2 h-2 rounded-full bg-blue-500" />
                            {stats.totalHosts} Host{stats.totalHosts !== 1 ? 's' : ''}
                        </span>
                        <span className="flex items-center gap-1.5 text-sm font-medium text-theme-secondary">
                            <span className="w-2 h-2 rounded-full bg-theme-muted" style={{ background: 'var(--text-muted)' }} />
                            {stats.totalInstances} Instance{stats.totalInstances !== 1 ? 's' : ''}
                        </span>
                        <span className="flex items-center gap-1.5 text-sm font-medium text-theme-secondary">
                            <span className="w-2 h-2 rounded-full status-pulse status-pulse-active" />
                            {stats.runningInstances} Running
                        </span>
                    </div>
                </div>
                <div className="flex gap-2.5">
                    <button onClick={allExpanded ? collapseAll : expandAll} className="btn btn-secondary gap-2">
                        {allExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        {allExpanded ? 'Collapse All' : 'Expand All'}
                    </button>
                    <button onClick={() => setIsAddHostModalOpen(true)} className="btn btn-primary gap-2">
                        <Plus size={14} /> Add New Host
                    </button>
                </div>
            </div>

            {/* Content */}
            {loading ? (
                <div className="card flex items-center justify-center py-16">
                    <div className="loader-tech" />
                </div>
            ) : serversData.length === 0 ? (
                <div className="text-center py-12 text-theme-muted text-sm">
                    <p className="mb-4">No servers found. Add a host to get started.</p>
                    <button onClick={() => setIsAddHostModalOpen(true)} className="btn btn-primary gap-2">
                        <Plus size={14} /> Add New Host
                    </button>
                </div>
            ) : (
                <SortableHostList
                    hosts={getOrderedHosts(serversData)}
                    onOrderChange={setHostOrder}
                    renderHostCard={(host, dragHandleProps) => (
                        <div className={`server-card${host.expanded ? ' expanded' : ''}`}>
                            {/* Host Column Labels */}
                            <div className="server-grid py-2.5 host-header-row">
                                <span />
                                <span className="col-label">Name</span>
                                <span className="col-label">Provider</span>
                                <span className="col-label">Region</span>
                                <span className="col-label" style={{ gridColumn: 'span 3' }}>IP Address</span>
                                <span className="col-label">Status</span>
                                <span />
                            </div>

                            {/* Host Row */}
                            <div className="server-grid py-[18px] cursor-pointer transition-colors host-row host-row-sortable" onClick={() => toggleExpand(host.id)}>
                                <div className="host-row-first-col">
                                    <div
                                        className="host-drag-handle"
                                        {...dragHandleProps.attributes}
                                        {...dragHandleProps.listeners}
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        <GripVertical size={14} />
                                    </div>
                                    <span className="expand-icon text-theme-muted">
                                        <ChevronRight size={16} />
                                    </span>
                                </div>
                                <button
                                    onClick={(e) => { e.stopPropagation(); handleOpenHostDrawer(host.id); }}
                                    className="text-[15px] font-semibold hover:underline text-left truncate"
                                    style={{ color: 'var(--accent-primary)' }}
                                >
                                    {host.name}
                                </button>
                                <span className="text-[13px] capitalize truncate text-theme-secondary">
                                    {host.provider || 'standalone'}
                                </span>
                                <span className="text-[13px] truncate text-theme-secondary flex items-center gap-1.5">
                                    <MapPin size={14} className="text-theme-muted flex-shrink-0" />
                                    {host.is_standalone
                                        ? (host.timezone || '—')
                                        : (formatVultrRegion(host.region) || '—')
                                    }
                                </span>
                                <div className="flex items-center gap-2 truncate" style={{ gridColumn: 'span 3' }} onClick={(e) => e.stopPropagation()}>
                                    <span className="font-mono text-[13px] text-theme-secondary">{host.ip_address || '—'}</span>
                                    {host.ip_address && (
                                        <button onClick={(e) => copyToClipboard(host.ip_address, host.id, e)} className="p-1 text-theme-muted hover:text-theme-secondary rounded transition-colors hover:bg-black/5 dark:hover:bg-white/5">
                                            {copiedIp === host.id ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                                        </button>
                                    )}
                                </div>
                                <div>
                                    {(host.qlfilter_status === 'installing' || host.qlfilter_status === 'uninstalling')
                                        ? <StatusIndicator status="configuring" pollableStatuses={['configuring']} />
                                        : <StatusIndicator status={host.status} pollableStatuses={POLLABLE_HOST_STATUSES} />
                                    }
                                </div>
                                <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
                                    <HostActionsMenu host={host} handleDelete={(id, name) => requestDeleteHost(id, name)} onOpenDrawer={handleOpenHostDrawer} POLLABLE_STATUSES={POLLABLE_HOST_STATUSES} onInstallQlfilter={(hostId) => handleQlfilterAction(hostId, 'install')} onUninstallQlfilter={(hostId) => handleQlfilterAction(hostId, 'uninstall')} onRequestRestart={handleRequestHostRestart} onOpenUpdateWorkshop={openWorkshopModal} onOpenAutoRestart={openAutoRestartModal} />
                                </div>
                            </div>

                            {/* Instances Section (animated expand/collapse) */}
                            {/* onPointerDown stops the outer host DndContext from capturing instance drags */}
                            <div className="instances-section" onPointerDown={(e) => e.stopPropagation()}>
                                <div className="server-grid py-2.5 instances-header-row">
                                    <span />
                                    <span className="col-label">Name</span>
                                    <span className="col-label">Server Hostname</span>
                                    <span />
                                    <span className="col-label">Port</span>
                                    <span className="col-label">Rate</span>
                                    <span className="col-label">Players</span>
                                    <span className="col-label">Status</span>
                                    <span />
                                </div>

                                {host.instances.length > 0 ? (
                                    <SortableInstanceList
                                        instances={getOrderedInstances(host.id, host.instances)}
                                        onOrderChange={(reordered) => setInstanceOrder(host.id, reordered)}
                                        renderInstanceContent={(inst) => (
                                            <InstanceRowContent
                                                inst={inst}
                                                host={host}
                                                pollableStatuses={POLLABLE_INSTANCE_STATUSES}
                                                serverStatus={serverStatusMap[String(inst.id)]}
                                                onOpenDetails={handleOpenInstanceDetails}
                                                onOpenLiveStatus={handleOpenLiveStatus}
                                                onRestart={requestRestartInstance}
                                                onDelete={requestDeleteInstance}
                                                onStop={requestStop}
                                                onStart={requestStart}
                                                onToggleLanRate={requestToggleLanRate}
                                                onEditConfig={handleOpenEditConfig}
                                                onViewLogs={handleViewLogs}
                                                onViewChatLogs={handleViewChatLogs}
                                                onOpenRcon={handleOpenRconConsole}
                                            />
                                        )}
                                    />
                                ) : (
                                    <div className="py-3 pl-5">
                                        <span className="text-sm italic ml-10 text-theme-muted">No instances</span>
                                    </div>
                                )}

                                <div className="add-instance-area">
                                    <button
                                        onClick={() => { setAddInstanceModalHostId(host.id); setIsAddInstanceModalOpen(true); }}
                                        className="add-instance-btn"
                                        disabled={host.instances.length >= 4}
                                    >
                                        <Plus size={14} /> Add QLDS Instance to {host.name}
                                    </button>
                                    {host.instances.length >= 4 && (
                                        <InfoTooltip text="Maximum of 4 instances per host" variant="warning" size={14} />
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                />
            )}

            {/* Modals */}
            <ConfirmationModal isOpen={deleteModal.open} onClose={closeDeleteModal} onConfirm={confirmDelete} title={`Delete ${deleteModal.type === 'host' ? 'Host' : 'Instance'}`} message={deleteModal.item ? `Are you sure you want to delete "${deleteModal.item.name}"?` : ''} confirmButtonText="Delete" confirmButtonVariant="danger" />
            <ConfirmationModal isOpen={restartModal.open} onClose={closeRestartModal} onConfirm={confirmRestart} title="Restart Instance" message={restartModal.instance ? `Are you sure you want to restart "${restartModal.instance.name}"?` : ''} confirmButtonText="Restart" confirmButtonVariant="primary" />
            <AddHostModal isOpen={isAddHostModalOpen} onClose={() => setIsAddHostModalOpen(false)} onHostAdded={() => refreshData(false)} />
            <AddInstanceModal isOpen={isAddInstanceModalOpen} onClose={() => { setIsAddInstanceModalOpen(false); setAddInstanceModalHostId(null); }} onInstanceAdded={() => { setAddInstanceModalHostId(null); refreshData(false); }} initialHostId={addInstanceModalHostId} />
            <HostDetailDrawer host={currentHostForDrawer || selectedHostId} open={isHostDrawerOpen} onClose={() => setIsHostDrawerOpen(false)} onHostUpdated={() => refreshData(false)} onHostDeleted={() => refreshData(false)} onDeleteHost={(host) => requestDeleteHost({ id: host.id, name: host.name })} onRequestRestart={handleRequestHostRestart} onQlfilterAction={handleQlfilterAction} onSwitchToInstanceDrawer={(instanceId) => { setIsHostDrawerOpen(false); handleOpenInstanceDetails(instanceId); }} />
            <InstanceDetailsModal isOpen={isInstanceDetailsOpen} onClose={() => setIsInstanceDetailsOpen(false)} instanceId={selectedInstanceId} onInstanceDeleted={() => refreshData(false)} onInstanceUpdated={() => refreshData(false)} onOpenEditConfig={handleOpenEditConfig} onOpenHostDrawer={(hostId) => { setIsInstanceDetailsOpen(false); handleOpenHostDrawer(hostId); }} serverStatus={selectedInstanceId ? serverStatusMap[String(selectedInstanceId)] : null} />
            {selectedInstanceForConfig && (
                <EditInstanceConfigModal isOpen={isEditConfigOpen} onClose={() => { setIsEditConfigOpen(false); setSelectedInstanceForConfig(null); }} instanceId={selectedInstanceForConfig.id} instanceName={selectedInstanceForConfig.name} onConfigSaved={() => { refreshData(false); setIsEditConfigOpen(false); setSelectedInstanceForConfig(null); }} />
            )}
            {hostForRestart && (
                <ConfirmationModal isOpen={isHostRestartModalOpen} onClose={closeHostRestartModal} onConfirm={confirmHostRestart} title={`Restart Host "${hostForRestart.name}"`} message={`Are you sure you want to restart host "${hostForRestart.name}"? This will temporarily make the host and its instances unavailable.`} confirmButtonText="Restart" confirmButtonVariant="warning" />
            )}
            <ViewLogsModal isOpen={isViewLogsModalOpen} onClose={closeViewLogsModal} instance={selectedInstanceForLogs} />
            <ViewChatLogsModal isOpen={isViewChatLogsModalOpen} onClose={closeViewChatLogsModal} instance={selectedInstanceForChatLogs} />
            <ConfirmationModal isOpen={isLanRateModalOpen} onClose={closeLanRateModal} onConfirm={confirmToggleLanRate} title={lanRateAction?.enabling ? 'Enable 99k LAN Rate' : 'Disable 99k LAN Rate'} message={`Are you sure you want to ${lanRateAction?.enabling ? 'enable' : 'disable'} 99k LAN rate mode for instance "${lanRateAction?.name}"? The instance will be reconfigured and restarted.`} confirmButtonText={lanRateAction?.enabling ? 'Enable' : 'Disable'} confirmButtonVariant="amber" />
            <ConfirmationModal isOpen={isStopStartModalOpen} onClose={closeStopStartModal} onConfirm={confirmStopStart} title={stopStartAction?.action === 'stop' ? 'Stop Instance' : 'Start Instance'} message={stopStartAction?.action === 'stop' ? `Are you sure you want to stop instance "${stopStartAction?.name}"? The server will go offline.` : `Are you sure you want to start instance "${stopStartAction?.name}"?`} confirmButtonText={stopStartAction?.action === 'stop' ? 'Stop' : 'Start'} confirmButtonVariant={stopStartAction?.action === 'stop' ? 'warning' : 'primary'} />
            <ForceUpdateWorkshopModal isOpen={isWorkshopModalOpen} onClose={closeWorkshopModal} onSubmit={handleWorkshopUpdateSubmit} host={hostForWorkshopUpdate} />
            <HostAutoRestartScheduleModal isOpen={isAutoRestartModalOpen} onClose={closeAutoRestartModal} onSubmit={handleAutoRestartSubmit} host={hostForAutoRestart} />
            {isRconConsoleOpen && rconInstance && <RconConsoleModal isOpen={isRconConsoleOpen} onClose={handleCloseRconConsole} instance={rconInstance} />}
            <LiveServerStatusModal isOpen={isLiveStatusOpen} onClose={() => setIsLiveStatusOpen(false)} instance={selectedLiveStatusInstance} serverStatus={selectedLiveStatusInstance ? serverStatusMap[String(selectedLiveStatusInstance.id)] : null} />
        </div>
    );
}
