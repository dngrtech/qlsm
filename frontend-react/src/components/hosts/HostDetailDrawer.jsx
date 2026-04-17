import React, { Fragment, useState, useEffect, useRef } from 'react';
import { Transition } from '@headlessui/react';
import { X, Zap, Copy, Check, PowerIcon, ShieldCheck, ShieldOff, Loader2, Pencil, LoaderCircle } from 'lucide-react';
import { getHostById, deleteHost as apiDeleteHost, updateHost } from '../../services/api';
import ConfirmationModal from '../ConfirmationModal';
import { useNotification } from '../NotificationProvider';
import StatusIndicator from '../StatusIndicator';
import { formatDateTime } from '../../utils/uiUtils';
import { formatVultrRegion, formatVultrPlan } from '../../utils/formatters';
import { HostStatus, QLFILTER_STATUS } from '../../utils/statusEnums';
import { copyToClipboard } from '../../utils/clipboard';
import { validateHostName, HOST_NAME_MAX_LENGTH } from '../../utils/resourceValidation';

const OS_TYPE_LABELS = {
  debian: 'Debian',
  debian12: 'Debian',
  ubuntu: 'Ubuntu',
  ubuntu20: 'Ubuntu',
  ubuntu22: 'Ubuntu',
  ubuntu24: 'Ubuntu',
};

export default function HostDetailDrawer({
  host, open, onClose, onDeleteHost, onHostDeleted, onHostUpdated,
  onSwitchToInstanceDrawer, onRequestRestart, onQlfilterAction
}) {
  const [internalHost, setInternalHost] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [ipCopied, setIpCopied] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState('');
  const [editedNameError, setEditedNameError] = useState(null);
  const [isUpdatingName, setIsUpdatingName] = useState(false);
  const { addNotification } = useNotification();
  const panelRef = useRef(null);
  const nameInputRef = useRef(null);

  useEffect(() => {
    if (open) {
      if (typeof host === 'number') {
        setLoading(true); setInternalHost(null); setError(null);
        getHostById(host)
          .then(data => { setInternalHost(data); setLoading(false); })
          .catch(err => { setError(`Failed to load host details: ${err.message || 'Unknown error'}`); setLoading(false); setInternalHost(null); });
      } else if (typeof host === 'object' && host !== null) {
        setInternalHost(host); setLoading(false); setError(null);
      } else {
        setError('Host details are not available.'); setLoading(false); setInternalHost(null);
      }
    }
    // Don't clear data on close — keeps content visible during slide-out animation
  }, [open, host]);

  useEffect(() => {
    if (!open) return;
    const handleEscape = (e) => { if (e.key === 'Escape') onClose(); };
    const handleClickOutside = (e) => {
      if (isDeleteModalOpen) return;
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    document.addEventListener('mousedown', handleClickOutside);
    return () => { document.removeEventListener('keydown', handleEscape); document.removeEventListener('mousedown', handleClickOutside); };
  }, [open, onClose, isDeleteModalOpen]);

  const handleDeleteClick = () => {
    if (onDeleteHost && internalHost) {
      onDeleteHost(internalHost.id, internalHost.name);
    } else if (internalHost) {
      setIsDeleteModalOpen(true);
    }
  };

  const handleConfirmDelete = async () => {
    if (!internalHost) return;
    setLoading(true);
    try {
      await apiDeleteHost(internalHost.id);
      addNotification(`Host ${internalHost.name} deleted successfully.`, 'success');
      setIsDeleteModalOpen(false);
      if (onHostDeleted) onHostDeleted(internalHost.id);
      onClose();
    } catch (err) {
      addNotification(`Failed to delete host: ${err.response?.data?.error?.message || err.message}`, 'error');
      setIsDeleteModalOpen(false);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyIp = () => {
    if (internalHost?.ip_address) {
      copyToClipboard(internalHost.ip_address).then(() => {
        setIpCopied(true);
        setTimeout(() => setIpCopied(false), 2000);
        addNotification('IP Address copied to clipboard!', 'success');
      }).catch(() => addNotification('Failed to copy IP Address.', 'error'));
    }
  };

  const handleStartEditName = () => {
    if (internalHost) { setEditedName(internalHost.name || ''); setIsEditingName(true); setTimeout(() => nameInputRef.current?.focus(), 0); }
  };
  const handleCancelEditName = () => { setIsEditingName(false); setEditedName(''); setEditedNameError(null); };

  const handleSaveEditName = async () => {
    if (!internalHost) return;
    const trimmedName = editedName.trim();
    const validationError = validateHostName(trimmedName);
    if (validationError) { setEditedNameError(validationError); return; }
    setEditedNameError(null);
    if (trimmedName === internalHost.name) { setIsEditingName(false); return; }
    setIsUpdatingName(true);
    try {
      const response = await updateHost(internalHost.id, { name: trimmedName });
      const updatedName = response.data?.name || trimmedName;
      setInternalHost(prev => ({ ...prev, name: updatedName }));
      addNotification(`Host name updated to "${updatedName}".`, 'success');
      setIsEditingName(false);
      if (onHostUpdated) onHostUpdated(internalHost.id, response.data);
    } catch (err) {
      const errorMessage = err?.error?.message || err?.error || err?.message || 'Failed to update host name.';
      addNotification(errorMessage, 'error');
    } finally {
      setIsUpdatingName(false);
    }
  };

  const handleNameInputKeyDown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); handleSaveEditName(); }
    else if (e.key === 'Escape') handleCancelEditName();
  };

  // Restart disabled logic
  let isRestartDisabled = true;
  if (internalHost) {
    const hs = internalHost.status?.toLowerCase();
    const qs = internalHost.qlfilter_status?.toLowerCase();
    const actionable = hs === HostStatus.ACTIVE.toLowerCase() || hs === HostStatus.ERROR.toLowerCase();
    const busy = [HostStatus.PROVISIONING, HostStatus.DELETING, HostStatus.REBOOTING, HostStatus.CONFIGURING].map(s => s.toLowerCase()).includes(hs);
    const qlBusy = [QLFILTER_STATUS.INSTALLING, QLFILTER_STATUS.UNINSTALLING].map(s => s.toLowerCase()).includes(qs);
    if (actionable && !busy && !qlBusy) isRestartDisabled = false;
  }

  // QLFilter button logic
  let qlBtn = { text: 'QLFilter Unknown', Icon: ShieldCheck, action: null, disabled: true, loading: false, variant: 'secondary' };
  if (internalHost && onQlfilterAction) {
    const qs = internalHost.qlfilter_status?.toLowerCase() || QLFILTER_STATUS.UNKNOWN;
    const hs = internalHost.status?.toLowerCase();
    const processing = qs === QLFILTER_STATUS.INSTALLING.toLowerCase() || qs === QLFILTER_STATUS.UNINSTALLING.toLowerCase();
    const hostBusy = [HostStatus.PROVISIONING, HostStatus.DELETING, HostStatus.REBOOTING, HostStatus.CONFIGURING].map(s => s.toLowerCase()).includes(hs);
    qlBtn.loading = processing;
    qlBtn.disabled = processing || hostBusy;
    if (qs === QLFILTER_STATUS.ACTIVE || qs === QLFILTER_STATUS.INACTIVE) {
      qlBtn = { ...qlBtn, text: 'Uninstall QLFilter', Icon: ShieldOff, action: () => onQlfilterAction(internalHost.id, 'uninstall'), variant: 'warning' };
    } else if ([QLFILTER_STATUS.NOT_INSTALLED, QLFILTER_STATUS.ERROR, QLFILTER_STATUS.UNKNOWN].includes(qs)) {
      qlBtn = { ...qlBtn, text: 'Install QLFilter', Icon: ShieldCheck, action: () => onQlfilterAction(internalHost.id, 'install'), variant: 'primary' };
    } else if (processing) {
      qlBtn.text = qs === QLFILTER_STATUS.INSTALLING.toLowerCase() ? 'Installing QLFilter' : 'Uninstalling QLFilter';
      qlBtn.Icon = Loader2;
    }
  }

  const Field = ({ label, children }) => (
    <dl className="drawer-field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </dl>
  );

  return (
    <>
      <Transition.Root show={open} as={Fragment}>
        <div className="fixed inset-0 z-40 overflow-hidden pointer-events-none">
          <div className="fixed inset-y-0 right-0 flex max-w-full pointer-events-none">
            <Transition.Child as={Fragment} enter="transform transition ease-out duration-300" enterFrom="translate-x-full" enterTo="translate-x-0" leave="transform transition ease-in duration-200" leaveFrom="translate-x-0" leaveTo="translate-x-full">
              <div ref={panelRef} className="drawer-panel w-[420px] pointer-events-auto">
                {/* Header */}
                <div className="drawer-header">
                  <h2 className="heading-display text-lg text-theme-primary tracking-wider">Host Details</h2>
                  <button onClick={onClose} className="p-1.5 rounded-lg text-theme-muted hover:text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                    <X size={20} />
                  </button>
                </div>

                {/* Body */}
                <div className="drawer-body">
                  {loading && !internalHost && (
                    <div className="flex justify-center items-center h-40">
                      <LoaderCircle size={28} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
                    </div>
                  )}
                  {error && <div className="alert-error"><p className="text-sm">{error}</p></div>}

                  {internalHost && !loading && !error && (
                    <div className="space-y-5">
                      {/* Name */}
                      <div style={{ borderBottom: '1px solid var(--surface-border)' }} className="pb-4">
                        {isEditingName ? (
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-2">
                              <input ref={nameInputRef} type="text" value={editedName}
                                onChange={(e) => { setEditedName(e.target.value); if (editedNameError) setEditedNameError(null); }}
                                onKeyDown={handleNameInputKeyDown} maxLength={HOST_NAME_MAX_LENGTH}
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
                            <h3 className="text-lg font-semibold text-theme-primary">{internalHost.name}</h3>
                            <button onClick={handleStartEditName} className="p-1 rounded-md text-theme-muted hover:text-theme-secondary hover:bg-black/5 dark:hover:bg-white/5 transition-colors" title="Edit name">
                              <Pencil size={14} />
                            </button>
                          </div>
                        )}
                        <p className="mt-1 font-mono text-xs text-theme-muted">ID: {internalHost.id}</p>
                      </div>

                      {/* Details Section */}
                      <div>
                        <div className="drawer-section-label">Details</div>
                        <Field label="Provider">
                          {internalHost.is_standalone ? (
                            <span className="flex items-center gap-2">
                              Standalone
                              <span className="text-[11px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.12)', color: '#f59e0b' }}>User-provided</span>
                            </span>
                          ) : internalHost.provider}
                        </Field>
                        {internalHost.is_standalone ? (
                          <>
                            <Field label="SSH Port">{internalHost.ssh_port || 22}</Field>
                            <Field label="OS Type">
                              {OS_TYPE_LABELS[internalHost.os_type] || internalHost.os_type || 'Unknown'}
                            </Field>
                          </>
                        ) : (
                          <>
                            <Field label="Region">{formatVultrRegion(internalHost.region)}</Field>
                            <Field label="Size">{formatVultrPlan(internalHost.machine_size)}</Field>
                          </>
                        )}
                        <Field label="IP Address">
                          <span className="flex items-center gap-2">
                            <span className="font-mono">{internalHost.ip_address || 'N/A'}</span>
                            {internalHost.ip_address && (
                              <button onClick={handleCopyIp} className="p-1 rounded text-theme-muted hover:text-theme-secondary transition-colors" title="Copy IP">
                                {ipCopied ? <Check size={14} style={{ color: 'var(--accent-primary)' }} /> : <Copy size={14} />}
                              </button>
                            )}
                          </span>
                        </Field>
                        <Field label="Status"><StatusIndicator status={internalHost.status} /></Field>
                        <Field label="Created">{formatDateTime(internalHost.created_at)}</Field>
                      </div>

                      {/* Instances */}
                      {internalHost.instances?.length > 0 && (
                        <div>
                          <div className="drawer-section-label">Deployed Instances</div>
                          <div className="space-y-2">
                            {internalHost.instances.map((inst) => (
                              <div key={inst.id} className="flex items-center justify-between py-2 px-3 rounded-lg" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--surface-border)' }}>
                                <div className="min-w-0">
                                  <button type="button" onClick={() => onSwitchToInstanceDrawer?.(inst.id)} className="text-sm font-medium hover:underline text-left truncate" style={{ color: '#3b82f6' }}>
                                    {inst.name}
                                  </button>
                                  <p className="text-xs text-theme-muted font-mono">Port: {inst.port}</p>
                                </div>
                                {internalHost.ip_address && inst.port ? (
                                  <a href={`steam://connect/${internalHost.ip_address}:${inst.port}`} className="btn-connect" style={{ padding: '4px 10px', fontSize: '11px' }}>
                                    <Zap size={12} /> Connect
                                  </a>
                                ) : (
                                  <span className="text-xs text-theme-muted px-2 py-1 rounded" style={{ background: 'var(--surface-raised)' }}>No connect info</span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Footer Actions */}
                {internalHost && !loading && !error && (
                  <div className="drawer-footer">
                    <button type="button" onClick={onClose} className="btn btn-ghost">Close</button>
                    <button type="button" onClick={() => internalHost && onRequestRestart?.(internalHost)} disabled={isRestartDisabled}
                      className="btn btn-secondary gap-1.5">
                      {internalHost?.status?.toLowerCase() === HostStatus.REBOOTING.toLowerCase()
                        ? <><LoaderCircle size={14} className="animate-spin" /> Rebooting...</>
                        : <><PowerIcon size={14} /> Restart</>}
                    </button>
                    <button type="button" onClick={() => qlBtn.action?.()} disabled={qlBtn.disabled}
                      className={`btn ${qlBtn.variant === 'primary' ? 'btn-primary' : 'btn-secondary'} gap-1.5`}>
                      <qlBtn.Icon size={14} className={qlBtn.loading ? 'animate-spin' : ''} /> {qlBtn.text}
                    </button>
                    <button type="button" onClick={handleDeleteClick} disabled={internalHost?.status === 'deleting'} className="btn btn-danger gap-1.5">
                      {internalHost?.is_standalone ? 'Remove' : 'Delete'}
                    </button>
                  </div>
                )}
              </div>
            </Transition.Child>
          </div>
        </div>
      </Transition.Root>

      <ConfirmationModal
        isOpen={isDeleteModalOpen} onClose={() => setIsDeleteModalOpen(false)} onConfirm={handleConfirmDelete}
        title={internalHost?.is_standalone ? 'Remove Host' : 'Delete Host'}
        message={internalHost?.is_standalone
          ? `Remove "${internalHost?.name || ''}" from inventory? The server will continue running but will no longer be managed.`
          : `Are you sure you want to delete the host "${internalHost?.name || ''}"? This action cannot be undone.`}
        confirmButtonText={internalHost?.is_standalone ? 'Remove' : 'Delete'}
        confirmButtonVariant={internalHost?.is_standalone ? 'orange' : 'danger'}
      />
    </>
  );
}
