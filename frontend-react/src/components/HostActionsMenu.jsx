import React, { Fragment } from 'react';
import { Menu, Transition, Portal } from '@headlessui/react';
import { useFloating, shift, offset, autoUpdate, flip } from '@floating-ui/react-dom';
import { Trash2, RefreshCw, ShieldCheck, ShieldOff, Loader2, Eye, PowerIcon } from 'lucide-react';
import { HostStatus, QLFILTER_STATUS } from '../utils/statusEnums';

function HostActionsMenu({
  host,
  handleDelete,
  onOpenDrawer,
  POLLABLE_STATUSES,
  onInstallQlfilter,
  onUninstallQlfilter,
  onRequestRestart,
  onOpenUpdateWorkshop,
  onOpenAutoRestart
}) {
  const { x, y, refs, strategy } = useFloating({
    placement: 'bottom-end',
    middleware: [
      offset(8),
      flip(),
      shift({ padding: 8 })
    ],
    whileElementsMounted: autoUpdate,
  });

  const hostStatus = host.status?.toLowerCase();
  const qlStatus = host.qlfilter_status || QLFILTER_STATUS.UNKNOWN;
  const isQlFilterBusy = qlStatus === QLFILTER_STATUS.INSTALLING || qlStatus === QLFILTER_STATUS.UNINSTALLING;
  const isHostBusy = [HostStatus.PROVISIONING, HostStatus.DELETING, HostStatus.REBOOTING, HostStatus.CONFIGURING].map(s => s.toLowerCase()).includes(hostStatus);
  const isHostReady = hostStatus === HostStatus.ACTIVE.toLowerCase() || hostStatus === HostStatus.ERROR.toLowerCase();

  return (
    <Menu as="div" className="relative inline-block text-left ml-2">
      {({ open, close: closeMenu }) => (
        <>
          <div>
            <Menu.Button
              ref={refs.setReference}
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md text-theme-muted hover:text-theme-secondary hover:bg-black/[0.04] dark:hover:bg-white/[0.04] focus:outline-none transition-all ${open ? 'bg-black/[0.04] dark:bg-white/[0.04] text-theme-secondary' : ''
                }`}
              title="Host Settings"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="1" /><circle cx="12" cy="5" r="1" /><circle cx="12" cy="19" r="1" /></svg>
              Actions
            </Menu.Button>
          </div>
          <Portal>
            <Transition
              as={Fragment}
              show={open}
              enter="transition ease-out duration-100"
              enterFrom="transform opacity-0 scale-95"
              enterTo="transform opacity-100 scale-100"
              leave="transition ease-in duration-75"
              leaveFrom="transform opacity-100 scale-100"
              leaveTo="transform opacity-0 scale-95"
            >
              <Menu.Items
                ref={refs.setFloating}
                style={{
                  position: strategy,
                  top: y ?? 0,
                  left: x ?? 0,
                  background: 'var(--surface-raised)',
                  borderColor: 'var(--surface-border)',
                }}
                className="z-20 w-64 rounded-lg shadow-lg border focus:outline-none overflow-hidden"
              >
                {/* View action */}
                <div className="px-1 py-1">
                  <Menu.Item>
                    {({ active }) => (
                      <button
                        type="button"
                        onClick={() => { onOpenDrawer(host.id); closeMenu(); }}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}
                      >
                        <Eye size={15} className="mr-3 flex-shrink-0 text-theme-muted" />
                        View Details
                      </button>
                    )}
                  </Menu.Item>
                </div>

                {/* Management actions */}
                <div className="px-1 py-1" style={{ borderTop: '1px solid var(--surface-border)' }}>
                  <Menu.Item>
                    {({ active }) => (
                      <button
                        type="button"
                        onClick={() => {
                          if (typeof onRequestRestart === 'function') onRequestRestart(host);
                          closeMenu();
                        }}
                        disabled={!isHostReady || isQlFilterBusy}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}
                      >
                        <PowerIcon size={15} className="mr-3 flex-shrink-0 text-theme-muted" />
                        Restart Host
                      </button>
                    )}
                  </Menu.Item>

                  <Menu.Item>
                    {({ active }) => (
                      <button
                        type="button"
                        onClick={() => {
                          if (typeof onOpenAutoRestart === 'function') onOpenAutoRestart(host);
                          closeMenu();
                        }}
                        disabled={!isHostReady || isQlFilterBusy}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mr-3 flex-shrink-0 text-theme-muted"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                        Configure Auto-Restart
                      </button>
                    )}
                  </Menu.Item>

                  <Menu.Item>
                    {({ active }) => (
                      <button
                        type="button"
                        onClick={() => {
                          if (typeof onOpenUpdateWorkshop === 'function') onOpenUpdateWorkshop(host);
                          closeMenu();
                        }}
                        disabled={!isHostReady || isQlFilterBusy}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}
                      >
                        <RefreshCw size={15} className="mr-3 flex-shrink-0 text-theme-muted" />
                        Update Workshop Item
                      </button>
                    )}
                  </Menu.Item>

                  {/* QLFilter Install/Uninstall */}
                  <Menu.Item>
                    {({ active }) => {
                      const isLoading = isQlFilterBusy;
                      const isInstalled = qlStatus === QLFILTER_STATUS.ACTIVE || qlStatus === QLFILTER_STATUS.INACTIVE;
                      const canInstall = qlStatus === QLFILTER_STATUS.NOT_INSTALLED || qlStatus === QLFILTER_STATUS.ERROR || qlStatus === QLFILTER_STATUS.UNKNOWN;

                      let buttonText, Icon, action;

                      if (isLoading) {
                        buttonText = qlStatus === QLFILTER_STATUS.INSTALLING ? 'Installing QLFilter...' : 'Uninstalling QLFilter...';
                        Icon = Loader2;
                        action = null;
                      } else if (isInstalled) {
                        buttonText = 'Uninstall QLFilter';
                        Icon = ShieldOff;
                        action = () => { if (typeof onUninstallQlfilter === 'function') onUninstallQlfilter(host.id); closeMenu(); };
                      } else if (canInstall) {
                        buttonText = 'Install QLFilter';
                        Icon = ShieldCheck;
                        action = () => { if (typeof onInstallQlfilter === 'function') onInstallQlfilter(host.id); closeMenu(); };
                      } else {
                        buttonText = 'QLFilter Unknown';
                        Icon = ShieldCheck;
                        action = null;
                      }

                      return (
                        <button
                          type="button"
                          onClick={action}
                          disabled={isLoading || !action || isHostBusy}
                          className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}
                        >
                          <Icon size={15} className={`mr-3 flex-shrink-0 text-theme-muted ${isLoading ? 'animate-spin' : ''}`} />
                          <span className="flex-1 text-left">{buttonText}</span>
                          {!isLoading && isInstalled && (
                            <span className="ml-2 inline-flex items-center text-[11px] font-medium px-1.5 py-0.5 rounded text-emerald-400"
                              style={{ background: 'rgba(34,217,127,0.12)' }}>
                              ACTIVE
                            </span>
                          )}
                        </button>
                      );
                    }}
                  </Menu.Item>
                </div>

                {/* Destructive action */}
                <div className="px-1 py-1" style={{ borderTop: '1px solid var(--surface-border)' }}>
                  <Menu.Item>
                    {({ active }) => (
                      <button
                        type="button"
                        onClick={() => { handleDelete(host.id, host.name); closeMenu(); }}
                        disabled={isHostBusy}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-red-500/10' : ''}`}
                        style={{ color: 'var(--accent-danger)' }}
                      >
                        <Trash2 size={15} className="mr-3 flex-shrink-0" />
                        {host.is_standalone ? 'Remove' : 'Delete'}
                      </button>
                    )}
                  </Menu.Item>
                </div>
              </Menu.Items>
            </Transition>
          </Portal>
        </>
      )}
    </Menu>
  );
}

export default HostActionsMenu;
