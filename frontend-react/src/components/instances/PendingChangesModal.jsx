import React, { useEffect, useState } from 'react';
import { Loader2, RotateCw } from 'lucide-react';
import Modal from '../Modal';
import { getInstancePendingChanges } from '../../services/api';
import { formatDateTime } from '../../utils/uiUtils';

const SOURCE_LABEL = {
  config_save: 'Config saved without restart',
  plugin_update: 'Plugin update without restart',
  workshop_update: 'Workshop item updated without restart',
};

const CHANGE_CLASS = {
  added: 'text-[var(--accent-primary)]',
  removed: 'text-[var(--accent-danger)]',
  modified: 'text-[var(--accent-info)]',
};

const SETTING_LABEL = {
  hostname: 'Server hostname',
  qlx_plugins: 'Enabled plugins',
  workshop_item: 'Workshop item',
};

// The backend stores naive UTC timestamps; without a zone the browser would
// read them as local time.
const asUtc = (iso) => (iso && !/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? `${iso}Z` : iso);

function diffLineClass(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-theme-muted';
  if (line.startsWith('@@')) return 'text-[var(--accent-info)]';
  if (line.startsWith('+')) return 'text-[var(--accent-primary)] bg-[var(--accent-primary)]/10';
  if (line.startsWith('-')) return 'text-[var(--accent-danger)] bg-[var(--accent-danger)]/10';
  return 'text-theme-secondary';
}

function DiffBlock({ diff }) {
  const lines = diff.replace(/\n$/, '').split('\n');
  return (
    <pre className="mt-2 max-h-80 overflow-auto rounded border border-[var(--surface-border)] bg-theme-elevated p-2 text-xs font-mono leading-5">
      {lines.map((line, index) => (
        // Index keys are fine: the list is static for the modal's lifetime.
        <div key={index} className={`whitespace-pre-wrap break-all ${diffLineClass(line)}`}>{line || ' '}</div>
      ))}
    </pre>
  );
}

// Also used by the bulk preset apply to show a server's diff.
export function FileChange({ file }) {
  return (
    <details className="rounded border border-[var(--surface-border)] px-3 py-2">
      <summary className="cursor-pointer text-sm">
        <span className="font-mono text-theme-primary">{file.path}</span>
        <span className={`ml-2 text-xs font-semibold uppercase ${CHANGE_CLASS[file.change] || ''}`}>{file.change}</span>
        {file.truncated && <span className="ml-2 text-xs text-theme-muted">(diff truncated)</span>}
      </summary>
      {file.diff
        ? <DiffBlock diff={file.diff} />
        : (
          <p className="mt-2 text-xs text-theme-muted">
            {file.binary
              ? 'Binary or large file - content not shown, its checksum changed.'
              : 'No textual difference.'}
          </p>
        )}
    </details>
  );
}

function Entry({ entry }) {
  return (
    <section className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-theme-secondary">
        {SOURCE_LABEL[entry.source] || entry.source}
        <span className="ml-2 font-normal normal-case tracking-normal text-theme-muted">
          {formatDateTime(asUtc(entry.created_at))}
        </span>
      </h4>
      {entry.settings.map((setting) => (
        <div key={setting.field} className="text-sm text-theme-primary">
          <span className="text-theme-secondary">{SETTING_LABEL[setting.field] || setting.field}:</span>{' '}
          {setting.before != null && (
            <>
              <span className="font-mono text-[var(--accent-danger)] line-through">{setting.before || '(empty)'}</span>
              {' -> '}
            </>
          )}
          <span className="font-mono text-[var(--accent-primary)]">{setting.after || '(empty)'}</span>
        </div>
      ))}
      {entry.files.map((file) => <FileChange key={file.path} file={file} />)}
      {entry.files.length === 0 && entry.settings.length === 0 && (
        <p className="text-sm text-theme-muted">No file changes.</p>
      )}
    </section>
  );
}

// Opened from an instance's "Updated" status badge: what was synced to the
// host since the last restart, and a way to restart now.
function PendingChangesModal({ isOpen, onClose, instance, onRestart }) {
  const [result, setResult] = useState({ status: 'loading' });
  const instanceId = instance?.id;

  useEffect(() => {
    if (!isOpen || instanceId == null) return undefined;
    let cancelled = false;
    setResult({ status: 'loading' });
    getInstancePendingChanges(instanceId)
      .then((data) => {
        if (!cancelled) setResult({ status: 'ready', entries: data.entries || [] });
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({ status: 'error', message: err?.error?.message || err?.message || 'Failed to load pending changes.' });
        }
      });
    return () => { cancelled = true; };
  }, [isOpen, instanceId]);

  const handleRestart = () => {
    onRestart(instance.id, instance.name);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="2xl"
      height="80vh"
      zIndexClass="z-50"
      title={`Pending changes: ${instance?.name ?? ''}`}
      footer={(
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Close</button>
          <button type="button" className="btn btn-primary inline-flex items-center gap-2" onClick={handleRestart}>
            <RotateCw size={14} /> Restart now
          </button>
        </>
      )}
    >
      <p className="text-sm text-theme-secondary">
        These changes are already on the host, but the server is still running the previous files.
        Any restart applies them - this button, a scheduled auto-restart, a crash or a host reboot.
      </p>
      <div className="mt-4 space-y-6">
        {result.status === 'loading' && (
          <div className="flex items-center gap-2 text-theme-secondary">
            <Loader2 size={16} className="animate-spin" /> Loading...
          </div>
        )}
        {result.status === 'error' && <div className="alert-error">{result.message}</div>}
        {result.status === 'ready' && result.entries.length === 0 && (
          <p className="text-sm text-theme-muted">
            No change details were recorded for this instance. It may have been updated before
            change tracking existed.
          </p>
        )}
        {result.status === 'ready' && result.entries.map((entry) => <Entry key={entry.id} entry={entry} />)}
      </div>
    </Modal>
  );
}

export default PendingChangesModal;
