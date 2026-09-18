import React, { useState } from 'react';
import {
  Trash2, RefreshCw, AlertTriangle, Loader2, Download, ChevronRight, FileEdit,
} from 'lucide-react';
import { downloadPluginRepositoryPlugins } from '../../services/api';
import { useNotification } from '../NotificationProvider';
import { formatDateTime } from '../../utils/uiUtils';
import RuntimePicker from './RuntimePicker';
import OverwritePluginsModal from './OverwritePluginsModal';
import PluginManifestEditorModal from './PluginManifestEditorModal';

// One repository's plugin list: expand/collapse, per-plugin checkboxes, and a
// per-plugin runtime pick for selected entries that declare no runtime.
function PluginRepositoryCard({ repo, onSync, onDelete, onDownloaded, syncing }) {
  const [expanded, setExpanded] = useState(false);
  const [checked, setChecked] = useState(new Set());
  const [downloading, setDownloading] = useState(false);
  const [pickedRuntimes, setPickedRuntimes] = useState({});
  // Files a download attempt reported as already present in the local pool
  // ({ code: 'exists' } from the backend) -- offered as an overwrite confirm
  // rather than a dead-end error, since that's the one failure mode with an
  // obvious next step. Shape: { files: [{filename, runtime}] }.
  const [overwriteConfirm, setOverwriteConfirm] = useState(null);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const { showSuccess, showError } = useNotification();

  const toggle = (filename) => {
    setChecked(prev => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  // `errors` here is always a plain array (never undefined), whether it came
  // back in a 2xx body or from the catch block below -- the two shapes are
  // {downloaded, errors} either way, just carried differently by axios.
  const reportResult = (result) => {
    const downloaded = result.downloaded || [];
    const errors = result.errors || [];
    if (downloaded.length) {
      const push = result.push || { queued: [], skipped: [] };
      const queuedNames = (push.queued || []).map(h => h.name);
      showSuccess(queuedNames.length
        ? `Downloaded ${downloaded.length} plugin(s). Pushing to ${queuedNames.join(', ')}.`
        : `Downloaded ${downloaded.length} plugin(s). No active host to push to.`);
      const skipped = push.skipped || [];
      if (skipped.length) {
        showError(`Not pushed to ${skipped.map(h => `${h.name} (${h.reason})`).join(', ')}. Run Check for Updates on those hosts later.`);
      }
    }
    const existing = errors.filter(e => e.code === 'exists');
    const otherErrors = errors.filter(e => e.code !== 'exists');
    if (otherErrors.length) {
      showError(otherErrors.map(e => `${e.filename}: ${e.error}`).join(' · '));
    }
    if (existing.length) {
      setOverwriteConfirm({
        files: existing.map(e => ({ filename: e.filename, runtime: pickedRuntimes[e.filename] ?? null })),
      });
    }
    if (downloaded.length || !existing.length) {
      setChecked(prev => {
        const next = new Set(prev);
        downloaded.forEach(f => next.delete(f));
        otherErrors.forEach(e => next.delete(e.filename));
        return next;
      });
    }
    if (downloaded.length) onDownloaded?.();
  };

  const runDownload = async (filenames, overwrite = false) => {
    setDownloading(true);
    try {
      const runtimes = {};
      filenames.forEach(f => { if (pickedRuntimes[f]) runtimes[f] = pickedRuntimes[f]; });
      const result = await downloadPluginRepositoryPlugins(repo.id, filenames, runtimes, overwrite);
      reportResult(result);
    } catch (err) {
      // A request where every file failed lands here (non-2xx), but the
      // backend still sent {downloaded: [], errors: [...]} as the body --
      // show those reasons instead of a generic message when present.
      if (Array.isArray(err?.errors)) {
        reportResult(err);
      } else {
        showError(err.error?.message || err.message || 'Failed to download plugins.');
      }
    } finally {
      setDownloading(false);
    }
  };

  // Selected plugins that declare no runtime and have no pick yet -- Download
  // stays disabled until each one has a runtime.
  const missingRuntime = repo.plugins
    .filter(p => checked.has(p.filename) && !p.runtime && !pickedRuntimes[p.filename])
    .map(p => p.filename);

  const handleDownload = () => {
    if (checked.size === 0 || missingRuntime.length) return;
    runDownload([...checked]);
  };

  // Unticked files are simply not downloaded; they stay ticked in the list,
  // the same as after Cancel.
  const handleConfirmOverwrite = (filenames) => {
    setOverwriteConfirm(null);
    runDownload(filenames, true);
  };

  return (
    <div className="users-table-container">
      <div className="flex items-center justify-between gap-3 p-4">
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-2 min-w-0 text-left"
        >
          <span className={`expand-icon${expanded ? ' is-expanded' : ''}`}>
            <ChevronRight size={16} />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="users-td-username">{repo.name}</span>
              <span className="text-xs text-[var(--text-muted)]">
                {repo.plugins.length} plugin{repo.plugins.length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="font-mono text-xs text-[var(--text-muted)] truncate">{repo.url}</div>
          </div>
        </button>
        <div className="flex items-center gap-3 flex-shrink-0">
          {repo.last_sync_error ? (
            <span className="flex items-center gap-1 text-xs text-red-500 dark:text-[#FF3366]" title={repo.last_sync_error}>
              <AlertTriangle size={14} /> Sync failed
            </span>
          ) : (
            <span className="text-xs text-[var(--text-muted)]">
              Synced {formatDateTime(repo.last_synced_at)}
            </span>
          )}
          <button
            onClick={() => onSync(repo)}
            disabled={syncing}
            className="users-action-btn"
            title="Sync"
          >
            <RefreshCw size={16} strokeWidth={2} className={syncing ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setIsEditOpen(true)}
            className="users-action-btn"
            title="Edit & Export Manifest"
          >
            <FileEdit size={16} strokeWidth={2} />
          </button>
          <button
            onClick={() => onDelete(repo)}
            className="users-action-btn users-action-btn-delete"
            title="Delete Repository"
          >
            <Trash2 size={16} strokeWidth={2} />
          </button>
        </div>
      </div>

      <div className={`collapsible-section${expanded ? ' is-expanded' : ''}`} inert={!expanded}>
        <div className="collapsible-inner">
        <div className="px-4 pb-4 border-t border-[var(--surface-border)]">
          {repo.plugins.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)] pt-3">
              {repo.last_sync_error ? 'Last sync failed — nothing to show.' : 'No plugins in this repository.'}
            </p>
          ) : (
            <>
              <table className="users-table mt-2">
                <thead>
                  <tr>
                    <th className="users-th" style={{ width: '2rem' }} />
                    <th className="users-th">Plugin</th>
                    <th className="users-th w-40">Runtime</th>
                    <th className="users-th">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {repo.plugins.map((plugin) => (
                    <tr key={plugin.filename} className="users-tr">
                      <td className="users-td">
                        <input
                          type="checkbox"
                          checked={checked.has(plugin.filename)}
                          onChange={() => toggle(plugin.filename)}
                          aria-label={plugin.label || plugin.filename}
                          className="h-3.5 w-3.5 rounded border-gray-500 text-blue-500 focus:ring-blue-500"
                        />
                      </td>
                      <td className="users-td">
                        <div>
                          {plugin.label || plugin.filename}
                          {plugin.label && plugin.label !== plugin.filename && (
                            <span className="ml-2 font-mono text-xs text-[var(--text-muted)]">{plugin.filename}</span>
                          )}
                        </div>
                        {plugin.description && (
                          <div className="text-xs text-[var(--text-muted)]">{plugin.description}</div>
                        )}
                      </td>
                      <td className="users-td">
                        {plugin.runtime ? (
                          <span className="font-mono text-xs">{plugin.runtime}</span>
                        ) : (
                          <RuntimePicker
                            value={pickedRuntimes[plugin.filename]}
                            onChange={(value) => setPickedRuntimes(prev => ({ ...prev, [plugin.filename]: value }))}
                            ariaLabel={`Runtime for ${plugin.filename}`}
                          />
                        )}
                      </td>
                      <td className="users-td">
                        {plugin.version_risk ? (
                          <span className="flex items-center gap-1 text-xs text-red-500 dark:text-[#FF3366]">
                            <AlertTriangle size={13} /> {plugin.version_risk.message}
                          </span>
                        ) : plugin.requires_qlsm_version ? (
                          <span className="text-xs text-[var(--text-muted)]">
                            Requires qlsm &gt;= {plugin.requires_qlsm_version}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="flex items-center gap-3 mt-3">
                <button
                  onClick={handleDownload}
                  disabled={checked.size === 0 || missingRuntime.length > 0 || downloading}
                  className="btn btn-primary"
                >
                  {downloading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Download size={16} />
                  )}
                  Download selected ({checked.size})
                </button>
                {missingRuntime.length > 0 && (
                  <span className="text-xs text-[var(--text-muted)]">
                    Pick a runtime for {missingRuntime.join(', ')}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
        </div>
      </div>

      {overwriteConfirm && (
        <OverwritePluginsModal
          isOpen
          repo={repo}
          files={overwriteConfirm.files}
          onConfirm={handleConfirmOverwrite}
          onClose={() => setOverwriteConfirm(null)}
        />
      )}

      <PluginManifestEditorModal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        repo={repo}
      />
    </div>
  );
}

export default PluginRepositoryCard;
