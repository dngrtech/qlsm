import React, { useState, useEffect, useCallback } from 'react';
import {
  PackagePlus, Trash2, RefreshCw, AlertCircle, AlertTriangle, Loader2, Download, ChevronDown, ChevronRight,
} from 'lucide-react';
import {
  getPluginRepositories,
  createPluginRepository,
  syncPluginRepository,
  deletePluginRepository,
  downloadPluginRepositoryPlugins,
} from '../services/api';
import { useNotification } from '../components/NotificationProvider';
import ConfirmationModal from '../components/ConfirmationModal';
import AddPluginRepositoryModal from '../components/pluginRepositories/AddPluginRepositoryModal';
import { formatDateTime } from '../utils/uiUtils';
import { RUNTIME_OPTIONS } from '../constants/runtimes';

// One repository's plugin list: expand/collapse, per-plugin checkboxes, and a
// per-plugin runtime pick for selected entries that declare no runtime.
function PluginRepositoryCard({ repo, onSync, onDelete, onDownloaded, syncing }) {
  const [expanded, setExpanded] = useState(false);
  const [checked, setChecked] = useState(new Set());
  const [downloading, setDownloading] = useState(false);
  const [pickedRuntimes, setPickedRuntimes] = useState({});
  // Filenames a download attempt reported as already present in the local
  // pool ({ code: 'exists' } from the backend) -- offered as an overwrite
  // confirm rather than a dead-end error, since that's the one failure mode
  // with an obvious next step.
  const [overwriteConfirm, setOverwriteConfirm] = useState(null);
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
      showSuccess(`Downloaded ${downloaded.length} plugin(s) into the local pool.`);
    }
    const existing = errors.filter(e => e.code === 'exists');
    const otherErrors = errors.filter(e => e.code !== 'exists');
    if (otherErrors.length) {
      showError(otherErrors.map(e => `${e.filename}: ${e.error}`).join(' · '));
    }
    if (existing.length) {
      setOverwriteConfirm({ filenames: existing.map(e => e.filename) });
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

  const handleConfirmOverwrite = () => {
    const filenames = overwriteConfirm?.filenames || [];
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
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
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
            onClick={() => onDelete(repo)}
            className="users-action-btn users-action-btn-delete"
            title="Delete Repository"
          >
            <Trash2 size={16} strokeWidth={2} />
          </button>
        </div>
      </div>

      {expanded && (
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
                    <th className="users-th">Runtime</th>
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
                          className="h-3.5 w-3.5 rounded border-gray-500 text-blue-500 focus:ring-blue-500"
                        />
                      </td>
                      <td className="users-td">
                        <div>{plugin.label || plugin.filename}</div>
                        {plugin.description && (
                          <div className="text-xs text-[var(--text-muted)]">{plugin.description}</div>
                        )}
                      </td>
                      <td className="users-td">
                        {plugin.runtime ? (
                          <span className="font-mono text-xs">{plugin.runtime}</span>
                        ) : checked.has(plugin.filename) ? (
                          <select
                            value={pickedRuntimes[plugin.filename] || ''}
                            onChange={(e) => {
                              const value = e.target.value;
                              setPickedRuntimes(prev => ({ ...prev, [plugin.filename]: value }));
                            }}
                            aria-label={`Runtime for ${plugin.filename}`}
                            className="input-base text-xs py-1"
                          >
                            <option value="">Pick runtime...</option>
                            {RUNTIME_OPTIONS.map((opt) => (
                              <option key={opt.id} value={opt.id}>{opt.name}</option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-xs text-[var(--text-muted)]" title="This plugin doesn't declare a runtime. Select it to pick one.">
                            not declared
                          </span>
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
      )}

      {overwriteConfirm && (
        <ConfirmationModal
          isOpen={!!overwriteConfirm}
          onClose={() => setOverwriteConfirm(null)}
          onConfirm={handleConfirmOverwrite}
          title="Overwrite existing plugins?"
          message={`Already in the local pool: ${overwriteConfirm.filenames.join(', ')}. Overwrite with this repository's copy?`}
          confirmButtonText="Overwrite"
          confirmButtonVariant="danger"
        />
      )}
    </div>
  );
}

function PluginRepositoriesPage() {
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedForDelete, setSelectedForDelete] = useState(null);
  const [syncingId, setSyncingId] = useState(null);

  const { showSuccess, showError } = useNotification();

  const fetchRepos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPluginRepositories();
      setRepos(data || []);
    } catch (err) {
      setError(err.error?.message || err.message || 'Failed to fetch plugin repositories.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRepos(); }, [fetchRepos]);

  const handleCreateRepository = async (repoData) => {
    await createPluginRepository(repoData);
    showSuccess(`Repository "${repoData.name}" added.`);
    fetchRepos();
  };

  const handleSync = async (repo) => {
    setSyncingId(repo.id);
    try {
      await syncPluginRepository(repo.id);
      showSuccess(`Synced "${repo.name}".`);
    } catch (err) {
      showError(err.error?.message || err.message || `Failed to sync "${repo.name}".`);
    } finally {
      setSyncingId(null);
      fetchRepos();
    }
  };

  const handleDeleteRepository = async () => {
    if (!selectedForDelete) return;
    try {
      await deletePluginRepository(selectedForDelete.id);
      showSuccess(`Repository "${selectedForDelete.name}" deleted.`);
      fetchRepos();
    } catch (err) {
      showError(err.error?.message || err.message || 'Failed to delete repository.');
    }
    setIsDeleteModalOpen(false);
    setSelectedForDelete(null);
  };

  const openDeleteModal = (repo) => {
    setSelectedForDelete(repo);
    setIsDeleteModalOpen(true);
  };

  if (error) {
    return (
      <div className="users-page">
        <div className="users-page-header">
          <div className="users-page-title-row">
            <div className="users-page-title-wrapper">
              <PackagePlus className="users-page-title-icon" strokeWidth={2} />
              <h1 className="users-page-title">Plugin Repositories</h1>
            </div>
          </div>
        </div>
        <div className="users-error-state">
          <AlertCircle size={24} strokeWidth={2} style={{ color: 'var(--accent-danger)' }} />
          <p className="users-error-text">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="users-page">
      <div className="users-page-header">
        <div className="users-page-title-row">
          <div className="users-page-title-wrapper">
            <PackagePlus className="users-page-title-icon" strokeWidth={2} />
            <h1 className="users-page-title">Plugin Repositories</h1>
            {!loading && (
              <span className="users-page-count">{repos.length}</span>
            )}
          </div>
          <button onClick={() => setIsAddModalOpen(true)} className="users-add-btn">
            <PackagePlus size={18} strokeWidth={2} />
            <span>Add Repository</span>
          </button>
        </div>
        <p className="text-sm text-[var(--text-muted)] mt-2">
          External sources of minqlx plugins. Downloading a plugin copies it into the local pool
          (ql-assets/data), the same place bundled plugins live — it's picked up wherever that pool
          already is, no different from one qlsm ships itself.
        </p>
      </div>

      {loading ? (
        <div className="users-loading-state">
          <Loader2 className="users-loading-spinner" strokeWidth={2} />
          <span className="users-loading-text">Loading repositories...</span>
        </div>
      ) : repos.length === 0 ? (
        <div className="users-empty-state">
          <PackagePlus size={32} strokeWidth={1.5} className="users-empty-icon" />
          <p className="users-empty-text">No plugin repositories added yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {repos.map((repo) => (
            <PluginRepositoryCard
              key={repo.id}
              repo={repo}
              syncing={syncingId === repo.id}
              onSync={handleSync}
              onDelete={openDeleteModal}
              onDownloaded={fetchRepos}
            />
          ))}
        </div>
      )}

      <AddPluginRepositoryModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSubmit={handleCreateRepository}
      />

      {selectedForDelete && (
        <ConfirmationModal
          isOpen={isDeleteModalOpen}
          onClose={() => {
            setIsDeleteModalOpen(false);
            setSelectedForDelete(null);
          }}
          onConfirm={handleDeleteRepository}
          title="Delete Plugin Repository"
          message={`Are you sure you want to remove "${selectedForDelete.name}"? Plugins already downloaded from it stay in the local pool.`}
          confirmButtonText="Delete"
          confirmButtonVariant="danger"
        />
      )}
    </div>
  );
}

export default PluginRepositoriesPage;
