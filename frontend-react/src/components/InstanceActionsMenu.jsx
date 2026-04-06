import React, { Fragment } from 'react'; // Removed useEffect
// Link removed for Edit Config
import { Menu, Transition, Portal } from '@headlessui/react';
import { useFloating, shift, offset, autoUpdate, flip } from '@floating-ui/react-dom';
import { Trash2, RefreshCw, SlidersHorizontal, Zap, FileText, ExternalLink, Check, Square, Play, Terminal, MessageSquare } from 'lucide-react';

// Define InstanceStatus constants to match backend enum values
const InstanceStatus = {
  IDLE: 'idle',
  DEPLOYING: 'deploying',
  CONFIGURING: 'configuring',
  RUNNING: 'running',
  STOPPING: 'stopping',
  STOPPED: 'stopped',
  STARTING: 'starting',
  RESTARTING: 'restarting',
  UPDATED: 'updated',
  ERROR: 'error',
  DELETING: 'deleting',
  ACTIVE: 'active'
};

function InstanceActionsMenu({ instance, handleRestart, handleDelete, handleStop, handleStart, handleToggleLanRate, POLLABLE_INSTANCE_STATUSES, onOpenEditConfigModal, onViewInstanceDetails, onViewLogs, onViewChatLogs, onOpenRconConsole }) {
  const { x, y, refs, strategy } = useFloating({
    placement: 'bottom-end',
    middleware: [
      offset(8),
      flip(),
      shift({ padding: 8 })
    ],
    whileElementsMounted: autoUpdate,
  });

  const isActionable = [InstanceStatus.RUNNING, InstanceStatus.ACTIVE, InstanceStatus.UPDATED, InstanceStatus.ERROR, InstanceStatus.STOPPED, InstanceStatus.IDLE].includes(instance.status?.toLowerCase());

  return (
    <Menu as="div" className="relative inline-block text-left ml-2">
      {({ open }) => (
        <>
          <div>
            <Menu.Button
              ref={refs.setReference}
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md text-theme-muted hover:text-theme-secondary hover:bg-black/[0.04] dark:hover:bg-white/[0.04] focus:outline-none transition-all ${open ? 'bg-black/[0.04] dark:bg-white/[0.04] text-theme-secondary' : ''
                }`}
              title="Instance Settings"
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
                className="z-20 w-52 rounded-lg shadow-lg border focus:outline-none overflow-hidden"
              >
                {/* Edit Config & RCON */}
                <div className="px-1 py-1">
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={() => onOpenEditConfigModal(instance)}
                        disabled={[InstanceStatus.DEPLOYING, InstanceStatus.CONFIGURING].includes(instance.status?.toLowerCase())}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                        <SlidersHorizontal size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> Edit Config
                      </button>
                    )}
                  </Menu.Item>
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={() => onOpenRconConsole?.(instance)}
                        disabled={![InstanceStatus.RUNNING, InstanceStatus.ACTIVE, InstanceStatus.UPDATED].includes(instance.status?.toLowerCase()) || !instance.zmq_rcon_port}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                        <Terminal size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> RCON Console
                      </button>
                    )}
                  </Menu.Item>
                </div>

                {/* View / Read-only actions */}
                <div className="px-1 py-1" style={{ borderTop: '1px solid var(--surface-border)' }}>
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={() => onViewLogs(instance)}
                        disabled={!isActionable}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                        <FileText size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> View Server Logs
                      </button>
                    )}
                  </Menu.Item>
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={() => onViewChatLogs(instance)}
                        disabled={!isActionable}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                        <MessageSquare size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> View Chat Logs
                      </button>
                    )}
                  </Menu.Item>
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={onViewInstanceDetails}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                        <ExternalLink size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> View Details
                      </button>
                    )}
                  </Menu.Item>
                </div>

                {/* Mutation actions */}
                <div className="px-1 py-1" style={{ borderTop: '1px solid var(--surface-border)' }}>
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={() => handleToggleLanRate(instance.id, instance.name, instance.lan_rate_enabled)}
                        disabled={!isActionable}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                        <Zap size={15} className="mr-3 flex-shrink-0 text-theme-muted" />
                        <span className="flex-1 text-left">99k LAN Rate</span>
                        <span className={`ml-2 inline-flex items-center gap-1 text-[11px] font-medium px-1.5 py-0.5 rounded ${instance.lan_rate_enabled ? 'text-emerald-400' : 'text-theme-muted'}`}
                          style={instance.lan_rate_enabled ? { background: 'rgba(34,217,127,0.12)' } : { background: 'rgba(100,116,139,0.12)' }}>
                          {instance.lan_rate_enabled ? <><Check size={10} /> ON</> : 'OFF'}
                        </span>
                      </button>
                    )}
                  </Menu.Item>
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={() => handleRestart(instance.id, instance.name)}
                        disabled={!isActionable}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                        <RefreshCw size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> Restart
                      </button>
                    )}
                  </Menu.Item>
                  <Menu.Item>
                    {({ active }) => {
                      const status = instance.status?.toLowerCase();
                      const isStopped = status === InstanceStatus.STOPPED;
                      const isBusy = [InstanceStatus.DEPLOYING, InstanceStatus.CONFIGURING, InstanceStatus.RESTARTING, InstanceStatus.DELETING, InstanceStatus.STOPPING, InstanceStatus.STARTING].includes(status);
                      return (
                        <button
                          onClick={() => isStopped ? handleStart?.(instance.id, instance.name) : handleStop?.(instance.id, instance.name)}
                          disabled={isBusy || status === InstanceStatus.IDLE || (!handleStop && !handleStart)}
                          className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'}`}>
                          {isStopped
                            ? <><Play size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> Start</>
                            : <><Square size={15} className="mr-3 flex-shrink-0 text-theme-muted" /> Stop</>
                          }
                        </button>
                      );
                    }}
                  </Menu.Item>
                </div>

                {/* Destructive action */}
                <div className="px-1 py-1" style={{ borderTop: '1px solid var(--surface-border)' }}>
                  <Menu.Item>
                    {({ active }) => (
                      <button onClick={() => handleDelete(instance.id, instance.name)}
                        disabled={[InstanceStatus.DELETING, InstanceStatus.DEPLOYING, InstanceStatus.CONFIGURING].includes(instance.status?.toLowerCase())}
                        className={`group flex rounded-md items-center w-full px-3 py-2 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${active ? 'bg-red-500/10' : ''}`}
                        style={{ color: 'var(--accent-danger)' }}>
                        <Trash2 size={15} className="mr-3 flex-shrink-0" /> Delete
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

export default InstanceActionsMenu;
