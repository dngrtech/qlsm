import { useEffect, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { Settings, X } from 'lucide-react';

import InfoTooltip from '../common/InfoTooltip';
import { parseCvarValue, readCvarFromConfig, serializeCvarValue, upsertCvarInConfig } from '../../utils/serverCfgCvars';

// Edit form for the cvars a plugin manifest declares (pluginManifest.js ->
// getPluginCvars). Values are read from / written back into the server.cfg
// draft as `set <cvar> "<value>"` lines — the same mechanism the Hostname
// field already uses for sv_hostname, just generalized to an arbitrary list.
function initialValues(cvars, configText) {
  const values = {};
  for (const c of cvars) {
    const raw = readCvarFromConfig(configText, c.cvar);
    const parsed = raw !== null ? parseCvarValue(c.type, raw) : null;
    values[c.cvar] = parsed !== null ? parsed : c.default;
  }
  return values;
}

export default function PluginCvarsModal({
  isOpen,
  onClose,
  onSave,
  pluginLabel,
  cvars = [],
  configText = '',
}) {
  const [values, setValues] = useState({});

  useEffect(() => {
    if (isOpen) {
      setValues(initialValues(cvars, configText));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const handleChange = (cvar, value) => {
    setValues(prev => ({ ...prev, [cvar]: value }));
  };

  const handleSave = () => {
    let nextConfig = configText;
    for (const c of cvars) {
      const value = values[c.cvar];
      if (value === null || value === undefined || value === '') continue;
      nextConfig = upsertCvarInConfig(nextConfig, c.cvar, serializeCvarValue(c.type, value));
    }
    onSave(nextConfig);
    onClose();
  };

  return (
    <Dialog open={isOpen} as="div" className="relative z-[60]" onClose={onClose}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4">
          <Dialog.Panel transition className="modal-panel w-full max-w-md max-h-[85vh] p-6 flex flex-col transition data-[enter]:ease-out data-[enter]:duration-200 data-[leave]:ease-in data-[leave]:duration-150 data-[closed]:opacity-0 data-[closed]:scale-95">
            <Dialog.Title className="text-lg font-display font-semibold uppercase tracking-wider text-[var(--text-primary)] mb-4 flex items-center justify-between flex-shrink-0">
              <span className="flex items-center gap-2">
                <Settings className="w-4 h-4" />
                {pluginLabel} Settings
              </span>
              <button type="button" onClick={onClose} className="logs-modal-close-btn">
                <X size={16} />
              </button>
            </Dialog.Title>
            <div className="space-y-3 flex-1 min-h-0 overflow-y-auto scrollbar-thin pr-2 pb-2">
              {cvars.map(c => (
                <div key={c.cvar}>
                  <label className="label-tech mb-1.5 flex items-center gap-1.5">
                    {c.label}
                    {c.description && <InfoTooltip text={c.description} size={13} />}
                  </label>
                  {c.type === 'bool' ? (
                    <label className="flex items-center gap-2 text-sm text-[var(--text-primary)] cursor-pointer select-none">
                      <input
                        type="checkbox"
                        aria-label={c.label}
                        checked={!!values[c.cvar]}
                        onChange={(e) => handleChange(c.cvar, e.target.checked)}
                        className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0"
                      />
                      {c.cvar}
                    </label>
                  ) : c.type === 'number' ? (
                    <input
                      type="number"
                      aria-label={c.label}
                      value={values[c.cvar] ?? ''}
                      min={c.min ?? undefined}
                      max={c.max ?? undefined}
                      onChange={(e) => handleChange(c.cvar, e.target.value === '' ? null : Number(e.target.value))}
                      className="input-base"
                    />
                  ) : (
                    <input
                      type="text"
                      aria-label={c.label}
                      value={values[c.cvar] ?? ''}
                      onChange={(e) => handleChange(c.cvar, e.target.value)}
                      className="input-base"
                    />
                  )}
                </div>
              ))}
              {cvars.length === 0 && (
                <p className="text-sm text-[var(--text-muted)]">No settings declared for this plugin.</p>
              )}
            </div>
            <div className="mt-5 flex justify-end gap-2 flex-shrink-0">
              <button type="button" onClick={onClose} className="btn btn-secondary">
                <X className="w-4 h-4 mr-1" />
                Cancel
              </button>
              <button type="button" onClick={handleSave} className="btn btn-primary" disabled={cvars.length === 0}>
                Save
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}
