import React, { useRef, useState } from 'react';
import { AlertTriangle, FolderOpen, Loader2, Upload } from 'lucide-react';
import { importBackup } from '../../services/api';
import { useNotification } from '../NotificationProvider';
import { CURRENT_VERSION } from '../../utils/versioning';

const CONFIRM_PHRASE = 'RESTORE';
const labelClass = 'block text-sm font-medium text-theme-secondary mb-1.5';

function ImportBackupPanel() {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [password, setPassword] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [importing, setImporting] = useState(false);
  const { showSuccess, showError } = useNotification();

  const canImport = Boolean(file) && confirmText === CONFIRM_PHRASE && !importing;

  const handleImport = async () => {
    if (!canImport) return;
    setImporting(true);
    try {
      const result = await importBackup(file, password || undefined);
      const restoredVersion = result.data?.qlsm_version;
      const baseMessage = result.message || 'Backup restored successfully. Please log in again.';
      const message = restoredVersion && restoredVersion !== CURRENT_VERSION
        ? `${baseMessage} (Backup was made on QLSM v${restoredVersion}; this host is running v${CURRENT_VERSION}.)`
        : baseMessage;
      showSuccess(message);
      setFile(null);
      setPassword('');
      setConfirmText('');
    } catch (err) {
      showError(err.error?.message || 'Failed to import backup.');
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="users-table-container">
      <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '360px' }}>
        <div className="flex items-start gap-3 rounded-lg border border-red-200 dark:border-[#FF3366]/30 bg-red-100 dark:bg-[#FF3366]/10 p-3">
          <AlertTriangle className="w-5 h-5 text-red-600 dark:text-[#FF3366] flex-shrink-0 mt-0.5" strokeWidth={2} />
          <span className="text-sm font-medium text-red-700 dark:text-[#FF3366]">
            Importing will permanently wipe this QLSM instance&apos;s database, SSH keys,
            Terraform state, instance configs, presets, and plugin binaries, and replace
            all of it with the contents of the uploaded backup. This cannot be undone
            from the UI.
          </span>
        </div>

        <div>
          <label htmlFor="backup-file" className={labelClass}>Backup file</label>
          <input
            ref={fileInputRef}
            id="backup-file"
            type="file"
            accept=".qlsmbak"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="btn btn-secondary"
          >
            <FolderOpen size={16} strokeWidth={2} className="mr-1" />
            <span>{file ? file.name : 'Choose backup file'}</span>
          </button>
        </div>

        <div>
          <label htmlFor="import-password" className={labelClass}>Backup password</label>
          <input
            id="import-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input-base"
            placeholder="Leave blank if the backup has no password"
          />
        </div>

        <div>
          <label htmlFor="import-confirm" className={labelClass}>
            Type {CONFIRM_PHRASE} to confirm
          </label>
          <input
            id="import-confirm"
            type="text"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            className="input-base"
          />
        </div>

        <button
          onClick={handleImport}
          disabled={!canImport}
          className="btn btn-danger"
          style={{ alignSelf: 'flex-start' }}
        >
          {importing ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} strokeWidth={2} />}
          <span>Import Backup</span>
        </button>
      </div>
    </div>
  );
}

export default ImportBackupPanel;
