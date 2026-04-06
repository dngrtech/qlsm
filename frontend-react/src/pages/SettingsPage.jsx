import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Copy, KeyRound, Loader2, AlertCircle, Trash2 } from 'lucide-react';
import { getApiKey, regenerateApiKey, revokeApiKey } from '../services/api';
import { useNotification } from '../components/NotificationProvider';
import ConfirmationModal from '../components/ConfirmationModal';
import { formatDateTime } from '../utils/uiUtils';

function SettingsPage() {
  const [apiKey, setApiKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [regenerating, setRegenerating] = useState(false);
  const [showRevokeModal, setShowRevokeModal] = useState(false);

  const { showSuccess, showError } = useNotification();

  const fetchApiKey = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const keyData = await getApiKey();
      setApiKey(keyData);
    } catch (err) {
      setError(err.error?.message || 'Failed to load API key.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchApiKey(); }, [fetchApiKey]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const newKey = await regenerateApiKey();
      setApiKey(newKey);
      showSuccess(apiKey ? 'API key regenerated.' : 'New API key generated.');
    } catch (err) {
      showError(err.error?.message || 'Failed to regenerate key.');
    } finally {
      setRegenerating(false);
    }
  };

  const handleRevoke = async () => {
    try {
      await revokeApiKey();
      setApiKey(null);
      showSuccess('API key revoked.');
    } catch (err) {
      showError(err.error?.message || 'Failed to revoke key.');
    }
    setShowRevokeModal(false);
  };

  const handleCopy = () => {
    if (apiKey?.key) {
      navigator.clipboard.writeText(apiKey.key);
      showSuccess('API key copied to clipboard.');
    }
  };

  if (error) {
    return (
      <div className="users-page">
        <div className="users-page-header">
          <div className="users-page-title-row">
            <div className="users-page-title-wrapper">
              <KeyRound className="users-page-title-icon" strokeWidth={2} />
              <h1 className="users-page-title">External API</h1>
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
      {/* Page header */}
      <div className="users-page-header">
        <div className="users-page-title-row">
          <div className="users-page-title-wrapper">
            <KeyRound className="users-page-title-icon" strokeWidth={2} />
            <h1 className="users-page-title">External API</h1>
          </div>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            className="users-add-btn"
          >
            {regenerating
              ? <Loader2 size={18} className="animate-spin" />
              : apiKey
                ? <RefreshCw size={18} strokeWidth={2} />
                : <KeyRound size={18} strokeWidth={2} />
            }
            <span>{apiKey ? 'Regenerate Key' : 'Generate Key'}</span>
          </button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="users-loading-state">
          <Loader2 className="users-loading-spinner" strokeWidth={2} />
          <span className="users-loading-text">Loading API key...</span>
        </div>
      ) : !apiKey ? (
        <div className="users-empty-state">
          <KeyRound size={32} strokeWidth={1.5} className="users-empty-icon" />
          <p className="users-empty-text">No API key generated yet.</p>
        </div>
      ) : (
        <div className="users-table-container">
          <table className="users-table">
            <thead>
              <tr>
                <th className="users-th">API Key</th>
                <th className="users-th">Created</th>
                <th className="users-th users-th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr className="users-tr">
                <td className="users-td">
                  <div className="settings-key-group">
                    <span className="settings-key-cell">{apiKey.key}</span>
                    <button
                      onClick={handleCopy}
                      className="users-action-btn users-action-btn-reset settings-copy-btn"
                      title="Copy to clipboard"
                    >
                      <Copy size={14} strokeWidth={2} />
                    </button>
                  </div>
                </td>
                <td className="users-td">
                  <span className="users-td-date">{formatDateTime(apiKey.created_at)}</span>
                </td>
                <td className="users-td users-td-actions">
                  <button
                    onClick={() => setShowRevokeModal(true)}
                    className="users-action-btn users-action-btn-delete"
                    title="Revoke API key"
                  >
                    <Trash2 size={16} strokeWidth={2} />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <ConfirmationModal
        isOpen={showRevokeModal}
        onClose={() => setShowRevokeModal(false)}
        onConfirm={handleRevoke}
        title="Revoke API Key"
        message="Are you sure you want to revoke the API key? External services using this key will immediately lose access."
        confirmButtonText="Revoke"
        confirmButtonVariant="danger"
      />
    </div>
  );
}

export default SettingsPage;
