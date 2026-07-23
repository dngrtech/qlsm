import { useCallback, useEffect, useRef, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { Copy, RefreshCw, Terminal, Trash2, Wifi, WifiOff, X } from 'lucide-react';

import { useRconSocket } from '../hooks/useRconSocket';
import RconCommandInput from './rcon/RconCommandInput';
import RconRawOutputViewer from './rcon/RconRawOutputViewer';

function statusAppearance(status) {
  if (status === 'connected') return { color: 'var(--accent-primary)', icon: Wifi };
  if (status === 'connecting') return { color: 'var(--accent-warning)', icon: RefreshCw };
  if (status === 'error') return { color: 'var(--accent-danger)', icon: WifiOff };
  return { color: 'var(--text-muted)', icon: WifiOff };
}

function RconConsoleModal({ isOpen, onClose, instance }) {
  const [showStats, setShowStats] = useState(true);
  const outputRef = useRef(null);
  const handleMessage = useCallback((event) => outputRef.current?.append(event), []);
  const { connected, status, sendCommand, subscribeStats, unsubscribeStats } =
    useRconSocket(instance, isOpen, handleMessage);

  useEffect(() => {
    if (isOpen) outputRef.current?.clear();
  }, [isOpen, instance?.id]);

  useEffect(() => {
    if (!connected) return;
    if (showStats) subscribeStats();
    else unsubscribeStats();
  }, [showStats, connected, subscribeStats, unsubscribeStats]);

  const copyOutput = useCallback(() => {
    const text = outputRef.current?.getText() || '';
    if (text) navigator.clipboard?.writeText(text);
  }, []);

  const appearance = statusAppearance(status);
  const StatusIcon = appearance.icon;

  return (
    <Dialog open={isOpen} as="div" className="relative z-50" onClose={onClose}>
      <DialogBackdrop transition className="fixed inset-0 bg-black/60 backdrop-blur-sm transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4 text-center">
          <Dialog.Panel
            transition
            className="rcon-console-modal w-full transform overflow-hidden rounded-xl bg-theme-raised border border-theme-strong text-left align-middle shadow-xl transition-all flex flex-col relative transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:scale-95"
            style={{ height: '70vh', maxWidth: '1000px' }}
          >
            <div className="accent-line-top" />
            <div className="flex items-center justify-between px-6 py-4 border-b border-theme flex-shrink-0 relative">
              <div className="flex items-center gap-3">
                <div className="logs-modal-icon-wrapper">
                  <div className="logs-modal-icon-glow" />
                  <Terminal className="logs-modal-icon" strokeWidth={2.5} />
                </div>
                <div>
                  <Dialog.Title as="h3" className="font-display text-lg font-bold tracking-wide text-theme-primary uppercase">
                    RCON Console
                  </Dialog.Title>
                  <p className="font-mono text-xs text-theme-secondary mt-0.5">
                    {instance?.name} <span className="text-theme-muted">•</span> Port {instance?.zmq_rcon_port}
                    <span className="text-theme-muted"> •</span>
                    <span className="inline-flex items-center gap-1 ml-1" style={{ color: appearance.color }}>
                      <StatusIcon className={`h-3 w-3 ${status === 'connecting' ? 'animate-spin' : ''}`} strokeWidth={2} />
                      {status}
                    </span>
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={copyOutput} className="logs-modal-close-btn" aria-label="Copy console output">
                  <Copy className="h-4 w-4" strokeWidth={2} />
                </button>
                <button type="button" onClick={() => outputRef.current?.clear()} className="logs-modal-close-btn" aria-label="Clear console output">
                  <Trash2 className="h-4 w-4" strokeWidth={2} />
                </button>
                <button type="button" onClick={onClose} className="logs-modal-close-btn" aria-label="Close RCON console">
                  <X className="h-5 w-5" strokeWidth={2} />
                </button>
              </div>
            </div>
            <div className="px-6 py-3 border-b border-theme bg-theme-elevated flex-shrink-0">
              <label className="flex items-center gap-2 text-sm text-theme-secondary cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={showStats}
                  onChange={(event) => setShowStats(event.target.checked)}
                  className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0"
                />
                Show real-time game events
              </label>
            </div>
            <div className="flex-1 overflow-hidden bg-theme-base p-4">
              <RconRawOutputViewer ref={outputRef} />
            </div>
            <RconCommandInput disabled={!connected} onSend={sendCommand} />
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}

export default RconConsoleModal;
