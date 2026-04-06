import React, { Fragment, useState, useEffect, useCallback, useRef } from 'react';
import { getInstanceById, restartInstance, stopInstance, startInstance, deleteInstance, updateInstanceLanRate, updateInstance } from '../../services/api';
import { Transition } from '@headlessui/react';
import { X, RefreshCw, Trash2, Edit3, Play, Square, Copy, Check, Pencil, LoaderCircle, Users } from 'lucide-react';
import ConfirmationModal from '../ConfirmationModal';
import { useNotification } from '../NotificationProvider';
import { formatDateTime } from '../../utils/uiUtils';
import StatusIndicator from '../StatusIndicator';
import QlColorString from '../common/QlColorString';
import LiveServerStatusModal from './LiveServerStatusModal';
import { validateInstanceName, INSTANCE_NAME_MAX_LENGTH } from '../../utils/resourceValidation';

const POLLING_INTERVAL = 3000;
const POLLABLE_STATUSES = ['PENDING', 'DEPLOYING', 'CONFIGURING', 'STARTING', 'STOPPING', 'RESTARTING', 'DELETING'];

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

function InstanceDetailsModal({ instanceId, isOpen, onClose, onInstanceDeleted, onInstanceUpdated, onOpenEditConfig, onOpenHostDrawer, serverStatus }) {
  const [instance, setInstance] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isLiveStatusOpen, setIsLiveStatusOpen] = useState(false);
  const [ipCopied, setIpCopied] = useState(false);
  const [copiedField, setCopiedField] = useState(null);
  const [lanRateUpdating, setLanRateUpdating] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState('');
  const [editedNameError, setEditedNameError] = useState(null);
  const [isUpdatingName, setIsUpdatingName] = useState(false);
  const nameInputRef = useRef(null);
  const { addNotification } = useNotification();
  const panelRef = useRef(null);

  const fetchInstanceData = useCallback(async (isInitialFetch = true) => {
    if (!instanceId) return;
    if (isInitialFetch) { setLoading(true); setError(null); }
    try {
      const data = await getInstanceById(instanceId);
      setInstance(data);
      if (isInitialFetch) setLoading(false);
    } catch (err) {
      const errMsg = err.response?.data?.error?.message || err.message || `Failed to fetch instance details for ID ${instanceId}`;
      if (isInitialFetch) { setError(errMsg); setLoading(false); }
    }
  }, [instanceId]);

  useEffect(() => {
    if (isOpen && instanceId) {
      fetchInstanceData(true);
      setIsEditingName(false); setEditedName(''); setEditedNameError(null);
    }
    // Don't clear data on close — keeps content visible during slide-out animation
  }, [isOpen, instanceId, fetchInstanceData]);

  useEffect(() => {
    let intervalId;
    if (isOpen && instance && POLLABLE_STATUSES.includes(instance.status)) {
      intervalId = setInterval(() => fetchInstanceData(false), POLLING_INTERVAL);
    }
    return () => { if (intervalId) clearInterval(intervalId); };
  }, [isOpen, instance, fetchInstanceData]);

  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e) => {
      if (e.key !== 'Escape') return;
      if (isDeleteModalOpen || isLiveStatusOpen) return;
      onClose();
    };
    const handleClickOutside = (e) => {
      if (isDeleteModalOpen || isLiveStatusOpen) return;
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    document.addEventListener('mousedown', handleClickOutside);
    return () => { document.removeEventListener('keydown', handleEscape); document.removeEventListener('mousedown', handleClickOutside); };
  }, [isOpen, onClose, isDeleteModalOpen, isLiveStatusOpen]);

  const handleRestart = async () => {
    if (!instanceId) return;
    setActionLoading(true); setActionError(null);
    try {
      const response = await restartInstance(instanceId);
      addNotification(response.message || 'Instance restart task queued.', 'success');
      fetchInstanceData(false);
      if (onInstanceUpdated) onInstanceUpdated(instanceId);
    } catch (err) {
      const errorMsg = err.response?.data?.error?.message || err.message || 'Failed to restart instance.';
      setActionError(errorMsg); addNotification(errorMsg, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStopStart = async () => {
    if (!instanceId || !instance) return;
    const isStopped = statusUpper === 'STOPPED';
    setActionLoading(true); setActionError(null);
    try {
      const response = isStopped ? await startInstance(instanceId) : await stopInstance(instanceId);
      addNotification(response.message || `Instance ${isStopped ? 'start' : 'stop'} task queued.`, 'success');
      fetchInstanceData(false);
      if (onInstanceUpdated) onInstanceUpdated(instanceId);
    } catch (err) {
      const errorMsg = err.response?.data?.error?.message || err.message || `Failed to ${isStopped ? 'start' : 'stop'} instance.`;
      setActionError(errorMsg); addNotification(errorMsg, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!instanceId || !instance) return;
    setActionLoading(true); setActionError(null);
    try {
      const response = await deleteInstance(instanceId);
      addNotification(response.message || `Instance "${instance?.name}" deletion initiated.`, 'success');
      setIsDeleteModalOpen(false); onClose();
      if (onInstanceDeleted) onInstanceDeleted(instanceId);
    } catch (err) {
      const errorMsg = err.response?.data?.error?.message || err.message || 'Failed to delete instance.';
      setActionError(errorMsg); addNotification(errorMsg, 'error'); setIsDeleteModalOpen(false);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCopyIp = (ipAddress) => {
    if (!ipAddress) return;
    navigator.clipboard.writeText(ipAddress).then(() => {
      setIpCopied(true); addNotification('IP Address copied to clipboard!', 'success');
      setTimeout(() => setIpCopied(false), 2000);
    }).catch(() => addNotification('Failed to copy IP address.', 'error'));
  };

  const handleCopyText = (text, field) => {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field);
      addNotification('Copied to clipboard!', 'success');
      setTimeout(() => setCopiedField(null), 2000);
    }).catch(() => addNotification('Failed to copy.', 'error'));
  };

  const handleToggleLanRate = async () => {
    if (!instanceId || !instance) return;
    setLanRateUpdating(true); setActionError(null);
    try {
      const newEnabled = !instance.lan_rate_enabled;
      const response = await updateInstanceLanRate(instanceId, newEnabled);
      addNotification(response.message || `LAN rate mode ${newEnabled ? 'enabled' : 'disabled'}.`, 'success');
      fetchInstanceData(false);
      if (onInstanceUpdated) onInstanceUpdated(instanceId);
    } catch (err) {
      const errorMsg = err.response?.data?.error?.message || err.message || 'Failed to update LAN rate mode.';
      setActionError(errorMsg); addNotification(errorMsg, 'error');
    } finally {
      setLanRateUpdating(false);
    }
  };

  const handleStartEditName = () => {
    if (instance) { setEditedName(instance.name || ''); setIsEditingName(true); setTimeout(() => nameInputRef.current?.focus(), 0); }
  };
  const handleCancelEditName = () => { setIsEditingName(false); setEditedName(''); setEditedNameError(null); };

  const handleSaveEditName = async () => {
    if (!instance) return;
    const trimmedName = editedName.trim();
    const validationError = validateInstanceName(trimmedName);
    if (validationError) { setEditedNameError(validationError); return; }
    setEditedNameError(null);
    if (trimmedName === instance.name) { setIsEditingName(false); return; }
    setIsUpdatingName(true);
    try {
      const response = await updateInstance(instance.id, { name: trimmedName });
      const updatedName = response.data?.name || trimmedName;
      setInstance(prev => ({ ...prev, name: updatedName }));
      addNotification(`Instance renamed to "${updatedName}".`, 'success');
      setIsEditingName(false);
      if (onInstanceUpdated) onInstanceUpdated(instance.id);
    } catch (err) {
      const errorMessage = err?.error?.message || err?.error || err?.message || 'Failed to update instance name.';
      addNotification(errorMessage, 'error'); setEditedNameError(errorMessage);
    } finally {
      setIsUpdatingName(false);
    }
  };

  const handleNameInputKeyDown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); handleSaveEditName(); }
    else if (e.key === 'Escape') handleCancelEditName();
  };

  const hostIp = instance?.host?.ip_address || instance?.host_ip_address;
  const hostId = instance?.host?.id || instance?.host_id;
  const hostName = instance?.host?.name || instance?.host_name;
  const statusUpper = instance?.status?.toUpperCase();
  const isActionableStatus = ['ACTIVE', 'RUNNING', 'UPDATED', 'ERROR', 'STOPPED', 'IDLE', 'INACTIVE'].includes(statusUpper);
  const isBusyStatus = ['DEPLOYING', 'CONFIGURING', 'RESTARTING', 'DELETING', 'STOPPING', 'STARTING'].includes(statusUpper);

  const Field = ({ label, children }) => (
    <dl className="drawer-field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </dl>
  );

  return (
    <>
      <Transition.Root show={isOpen} as={Fragment}>
        <div className="fixed inset-0 z-40 overflow-hidden pointer-events-none">
          <div className="fixed inset-y-0 right-0 flex max-w-full pointer-events-none">
            <Transition.Child as={Fragment} enter="transform transition ease-out duration-300" enterFrom="translate-x-full" enterTo="translate-x-0" leave="transform transition ease-in duration-200" leaveFrom="translate-x-0" leaveTo="translate-x-full">
              <div ref={panelRef} className="drawer-panel w-[500px] pointer-events-auto">
                {/* Header */}
                <div className="drawer-header">
                  <h2 className="heading-display text-lg text-theme-primary tracking-wider">Instance Details</h2>
                  <button onClick={onClose} className="p-1.5 rounded-lg text-theme-muted hover:text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                    <X size={20} />
                  </button>
                </div>

                {/* Body */}
                <div className="drawer-body">
                  {loading && (
                    <div className="flex justify-center items-center h-40">
                      <LoaderCircle size={28} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
                    </div>
                  )}
                  {error && <div className="alert-error"><p className="text-sm">{error}</p></div>}
                  {actionError && <div className="alert-error mt-2"><p className="text-sm">Action Error: {actionError}</p></div>}

                  {instance && !loading && !error && (
                    <div className="space-y-5 pt-4">
                      {/* Name */}
                      <div style={{ borderBottom: '1px solid var(--surface-border)' }} className="pb-4">
                        {isEditingName ? (
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-2">
                              <input ref={nameInputRef} type="text" value={editedName}
                                onChange={(e) => { setEditedName(e.target.value); if (editedNameError) setEditedNameError(null); }}
                                onKeyDown={handleNameInputKeyDown} maxLength={INSTANCE_NAME_MAX_LENGTH}
                                className={`input-base flex-1 text-lg font-semibold ${editedNameError ? 'input-error' : ''}`}
                                disabled={isUpdatingName} />
                              <button onClick={handleSaveEditName} disabled={isUpdatingName} className="p-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition-colors" style={{ color: 'var(--accent-primary)' }} title="Save">
                                {isUpdatingName ? <LoaderCircle size={18} className="animate-spin" /> : <Check size={18} />}
                              </button>
                              <button onClick={handleCancelEditName} disabled={isUpdatingName} className="p-1.5 rounded-md text-theme-muted hover:bg-black/5 dark:hover:bg-white/5 transition-colors" title="Cancel">
                                <X size={18} />
                              </button>
                            </div>
                            {editedNameError && <p className="text-sm" style={{ color: 'var(--accent-danger)' }}>{editedNameError}</p>}
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <h3 className="text-lg font-semibold text-theme-primary">{instance.name}</h3>
                            <button onClick={handleStartEditName} className="p-1 rounded-md text-theme-muted hover:text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5 transition-colors" title="Edit name">
                              <Pencil size={14} />
                            </button>
                          </div>
                        )}
                        <p className="mt-1 font-mono text-xs text-theme-muted">ID: {instance.id}</p>
                      </div>

                      {/* Details Section */}
                      <div>
                        <div className="drawer-section-label">Details</div>
                        <Field label="Host">
                          {hostId && hostName ? (
                            <button onClick={() => { onOpenHostDrawer(hostId); onClose(); }} className="font-medium hover:underline" style={{ color: '#3b82f6' }}>
                              {hostName}
                            </button>
                          ) : 'N/A'}
                        </Field>
                        <Field label="Host IP">
                          <span className="flex items-center gap-2">
                            <span className="font-mono">{hostIp || 'N/A'}</span>
                            {hostIp && (
                              <button onClick={() => handleCopyIp(hostIp)} className="p-1 rounded text-theme-muted hover:text-theme-secondary transition-colors" title="Copy IP">
                                {ipCopied ? <Check size={14} style={{ color: 'var(--accent-primary)' }} /> : <Copy size={14} />}
                              </button>
                            )}
                          </span>
                        </Field>
                        <Field label="Port"><span className="font-mono">{instance.port}</span></Field>
                        <Field label="Hostname">{instance.hostname || 'N/A'}</Field>
                        <Field label="Status"><StatusIndicator status={instance.status} /></Field>
                        <Field label="99k LAN Rate">
                          <div className="flex items-center gap-2">
                            <button type="button" onClick={handleToggleLanRate}
                              disabled={lanRateUpdating || actionLoading || isBusyStatus}
                              className="neu-toggle neu-toggle--sm">
                              <span className={`neu-toggle__track ${instance.lan_rate_enabled ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                <span className={`neu-toggle__knob ${instance.lan_rate_enabled ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                              </span>
                            </button>
                            <span className="text-xs text-theme-secondary">
                              {lanRateUpdating ? 'Updating...' : (instance.lan_rate_enabled ? 'Enabled' : 'Disabled')}
                            </span>
                          </div>
                        </Field>
                        <Field label="Created">{formatDateTime(instance.created_at)}</Field>
                        {instance.updated_at && <Field label="Updated">{formatDateTime(instance.updated_at)}</Field>}

                        <div className="drawer-section-label mt-4">ZMQ Configuration</div>
                        <Field label="ZMQ RCON Port"><span className="font-mono">{instance.zmq_rcon_port || 'N/A'}</span></Field>
                        <Field label="ZMQ RCON Password">
                          <span className="flex items-center gap-2">
                            <span className="font-mono select-all truncate max-w-[200px]">{instance.zmq_rcon_password || 'N/A'}</span>
                            {instance.zmq_rcon_password && (
                              <button onClick={() => handleCopyText(instance.zmq_rcon_password, 'rcon_pwd')} className="p-1 rounded text-theme-muted hover:text-theme-secondary transition-colors" title="Copy Password">
                                {copiedField === 'rcon_pwd' ? <Check size={14} style={{ color: 'var(--accent-primary)' }} /> : <Copy size={14} />}
                              </button>
                            )}
                          </span>
                        </Field>
                        <Field label="ZMQ Stats Port"><span className="font-mono">{instance.zmq_stats_port || 'N/A'}</span></Field>
                        <Field label="ZMQ Stats Password">
                          <span className="flex items-center gap-2">
                            <span className="font-mono select-all truncate max-w-[200px]">{instance.zmq_stats_password || 'N/A'}</span>
                            {instance.zmq_stats_password && (
                              <button onClick={() => handleCopyText(instance.zmq_stats_password, 'stats_pwd')} className="p-1 rounded text-theme-muted hover:text-theme-secondary transition-colors" title="Copy Password">
                                {copiedField === 'stats_pwd' ? <Check size={14} style={{ color: 'var(--accent-primary)' }} /> : <Copy size={14} />}
                              </button>
                            )}
                          </span>
                        </Field>
                      </div>

                      {/* Live Status */}
                      <div>
                        <div className="drawer-section-label">Live Status</div>
                        {serverStatus ? (
                          <div className="space-y-2">
                            <dl className="drawer-field">
                              <dt>Map</dt>
                              <dd className="font-mono">{serverStatus.map || '—'}</dd>
                            </dl>
                            <dl className="drawer-field">
                              <dt>Gametype</dt>
                              <dd className="uppercase">{serverStatus.gametype || '—'}</dd>
                            </dl>
                            <dl className="drawer-field">
                              <dt>Factory</dt>
                              <dd>{serverStatus.factory || '—'}</dd>
                            </dl>
                            {['ca', 'ctf', 'tdm', 'ft', 'ad', 'har', 'dom', 'ob', 'rr'].includes(serverStatus.gametype?.toLowerCase()) && (
                              <dl className="drawer-field">
                                <dt>Score</dt>
                                <dd>
                                  <span className="text-red-500 font-semibold">{serverStatus.red_score || 0}</span>
                                  <span className="text-theme-muted mx-1">-</span>
                                  <span className="text-blue-400 font-semibold">{serverStatus.blue_score || 0}</span>
                                </dd>
                              </dl>
                            )}
                            <dl className="drawer-field">
                              <dt>State</dt>
                              <dd className="capitalize">{serverStatus.state?.replaceAll('_', ' ') || '—'}</dd>
                            </dl>
                            <dl className="drawer-field">
                              <dt>Time Elapsed</dt>
                              <dd>{serverStatus.match_start_time ? <LiveClock startTime={serverStatus.match_start_time} /> : '00:00'}</dd>
                            </dl>
                            <dl className="drawer-field">
                              <dt>Players</dt>
                              <dd>
                                <button
                                  onClick={() => setIsLiveStatusOpen(true)}
                                  className="live-status-toggle flex items-center gap-1.5 px-2 py-0.5 rounded border border-theme-strong bg-theme-elevated hover:bg-black/10 dark:hover:bg-white/10 text-[12px] font-mono text-theme-primary transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)] focus:ring-offset-1 focus:ring-offset-[var(--surface-base)]"
                                >
                                  <Users size={12} className="text-theme-muted" />
                                  {serverStatus.players?.length ?? 0}/{serverStatus.maxplayers ?? '?'}
                                </button>
                              </dd>
                            </dl>
                          </div>
                        ) : (
                          <p className="text-sm text-theme-muted italic">
                            No live data — server may be offline or starting up.
                          </p>
                        )}
                      </div>

                    </div>
                  )}
                </div>

                {/* Footer Actions */}
                {instance && !loading && !error && (
                  <div className="drawer-footer">
                    <button type="button" onClick={() => { if (instance) onOpenEditConfig(instance); onClose(); }}
                      disabled={actionLoading || ['DEPLOYING', 'CONFIGURING'].includes(statusUpper)}
                      className="btn btn-secondary gap-1.5" style={{ borderColor: '#3b82f6', color: '#3b82f6' }}>
                      <Edit3 size={14} /> Edit Config
                    </button>
                    <button type="button" onClick={handleStopStart}
                      disabled={actionLoading || isBusyStatus || statusUpper === 'IDLE'}
                      className="btn btn-secondary gap-1.5"
                      style={statusUpper === 'STOPPED' ? { borderColor: 'var(--accent-primary)', color: 'var(--accent-primary)' } : isActionableStatus ? { borderColor: 'var(--accent-warning)', color: 'var(--accent-warning)' } : {}}>
                      {statusUpper === 'STOPPED'
                        ? <><Play size={14} /> {actionLoading && statusUpper === 'STARTING' ? 'Starting...' : 'Start'}</>
                        : <><Square size={14} /> {actionLoading && statusUpper === 'STOPPING' ? 'Stopping...' : 'Stop'}</>
                      }
                    </button>
                    <button type="button" onClick={handleRestart} disabled={actionLoading || !isActionableStatus}
                      className="btn btn-secondary gap-1.5" style={isActionableStatus ? { borderColor: 'var(--accent-warning)', color: 'var(--accent-warning)' } : {}}>
                      <RefreshCw size={14} className={actionLoading && statusUpper === 'RESTARTING' ? 'animate-spin' : ''} />
                      {actionLoading && statusUpper === 'RESTARTING' ? 'Restarting...' : 'Restart'}
                    </button>
                    <button type="button" onClick={() => setIsDeleteModalOpen(true)}
                      disabled={actionLoading || ['DELETING', 'DEPLOYING', 'CONFIGURING'].includes(statusUpper)}
                      className="btn btn-danger gap-1.5">
                      <Trash2 size={14} /> {actionLoading && statusUpper === 'DELETING' ? 'Deleting...' : 'Delete'}
                    </button>
                    <button type="button" onClick={onClose} className="btn btn-secondary">Close</button>
                  </div>
                )}
              </div>
            </Transition.Child>
          </div>
        </div>
      </Transition.Root>

      <ConfirmationModal
        isOpen={isDeleteModalOpen} onClose={() => setIsDeleteModalOpen(false)} onConfirm={handleConfirmDelete}
        title="Delete Instance"
        message={`Are you sure you want to delete instance "${instance?.name || ''}"? This action may be irreversible.`}
        confirmButtonText="Delete" confirmButtonColor="red"
      />
      <LiveServerStatusModal isOpen={isLiveStatusOpen} onClose={() => setIsLiveStatusOpen(false)} instance={instance} serverStatus={serverStatus} />
    </>
  );
}

export default InstanceDetailsModal;
