import React, { useRef } from 'react';
import { CheckCircle, Loader2, LockKeyhole, Upload, XCircle } from 'lucide-react';

const inputClass = 'mt-1 block w-full px-3 py-2 rounded-lg text-sm text-theme-primary placeholder:text-theme-muted focus:outline-none focus:ring-1 transition-colors';
const inputFocusRing = 'focus:ring-[var(--accent-primary)] focus:border-[var(--accent-primary)]';
const inputStyle = { background: 'var(--surface-elevated)', border: '1px solid var(--surface-border)' };
const labelClass = 'block text-sm font-medium text-theme-secondary';

const AUTH_OPTIONS = [
  {
    id: 'key',
    label: 'SSH key',
    description: 'Paste or upload a private key for the bootstrap connection.',
  },
  {
    id: 'password',
    label: 'Password',
    description: 'Use the password once, then QLSM installs a managed key.',
  },
];

function StandaloneAuthSection({
  authMethod,
  onAuthMethodChange,
  sshKey,
  onSshKeyChange,
  sshPassword,
  onSshPasswordChange,
  ipAddress,
  sshUser,
  connectionTestStatus,
  connectionTestMessage,
  onTestConnection,
}) {
  const fileInputRef = useRef(null);
  const isPasswordAuth = authMethod === 'password';
  const [showPassword, setShowPassword] = React.useState(false);
  const hasRequiredFields = Boolean(
    ipAddress?.trim()
    && sshUser?.trim()
    && (isPasswordAuth ? sshPassword?.trim() : sshKey?.trim())
    && connectionTestStatus !== 'testing'
  );

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const content = event.target?.result;
        if (content && onSshKeyChange) {
          onSshKeyChange({ target: { value: content } });
        }
      };
      reader.readAsText(file);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-end justify-between gap-3">
          <label className={labelClass}>Authentication</label>
          <span className="text-xs text-theme-muted">Choose the bootstrap method for this standalone host.</span>
        </div>
        <div className="mt-2 grid gap-3 sm:grid-cols-2" role="tablist" aria-label="Standalone authentication method">
          {AUTH_OPTIONS.map((option) => {
            const selected = authMethod === option.id;
            return (
              <button
                key={option.id}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => onAuthMethodChange(option.id)}
                className="rounded-xl px-4 py-3 text-left transition-all"
                style={{
                  background: selected ? 'rgba(0, 255, 157, 0.08)' : 'var(--surface-elevated)',
                  border: selected ? '1px solid rgba(0, 255, 157, 0.35)' : '1px solid var(--surface-border)',
                  boxShadow: selected ? '0 0 0 1px rgba(0, 255, 157, 0.08) inset' : 'none',
                }}
              >
                <div className="flex items-center gap-2">
                  <LockKeyhole size={14} style={{ color: selected ? 'var(--accent-primary)' : 'var(--text-secondary)' }} />
                  <span className="text-sm font-semibold text-theme-primary">{option.label}</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-theme-muted">{option.description}</p>
              </button>
            );
          })}
        </div>
      </div>

      {isPasswordAuth ? (
        <div>
          <label htmlFor="modal-ssh-password" className={labelClass}>SSH Password</label>
          <input
            id="modal-ssh-password"
            type={showPassword ? 'text' : 'password'}
            value={sshPassword || ''}
            onChange={onSshPasswordChange}
            required
            placeholder="Password used to bootstrap access"
            className={`${inputClass} ${inputFocusRing}`}
            style={inputStyle}
          />
          <div className="mt-2 flex items-center justify-between gap-3">
            <div
              className="rounded-lg px-3.5 py-3 text-xs leading-5 text-theme-secondary"
              style={{
                background: 'rgba(0, 255, 157, 0.08)',
                border: '1px solid rgba(0, 255, 157, 0.2)',
              }}
            >
              QLSM uses this password once to install a managed SSH key. The password is not stored.
            </div>
            <button
              type="button"
              onClick={() => setShowPassword((current) => !current)}
              className="shrink-0 rounded-lg px-3 py-2 text-xs font-medium text-theme-secondary hover:text-theme-primary hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors"
              style={{ border: '1px solid var(--surface-border)' }}
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>
      ) : (
        <div>
          <label htmlFor="modal-ssh-key" className={labelClass}>SSH Private Key</label>
          <div className="mt-1">
            <textarea
              id="modal-ssh-key"
              value={sshKey || ''}
              onChange={onSshKeyChange}
              required
              rows={6}
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
              className={`${inputClass} ${inputFocusRing} font-mono text-xs resize-none`}
              style={inputStyle}
            />
            <div className="mt-2 flex items-center">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pem,.key,.txt,*"
                onChange={handleFileUpload}
                className="hidden"
                id="ssh-key-file-input"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-theme-secondary hover:text-theme-primary hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors"
                style={{ border: '1px solid var(--surface-border)' }}
              >
                <Upload size={14} className="mr-1.5" />
                Upload Key File
              </button>
              <span className="ml-3 text-xs text-theme-muted">Or paste key content above</span>
            </div>
          </div>
        </div>
      )}

      {sshUser?.trim() && sshUser.trim() !== 'root' && (
        <p className="text-xs text-theme-muted">
          Must have passwordless sudo on this machine.
        </p>
      )}

      <div className="pt-1">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onTestConnection}
            disabled={!hasRequiredFields}
            className="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:bg-black/[0.04] dark:hover:bg-white/[0.06]"
            style={{ border: '1px solid var(--surface-border-strong)', color: 'var(--text-secondary)' }}
          >
            {connectionTestStatus === 'testing' ? (
              <>
                <Loader2 size={15} className="mr-2 animate-spin" />
                Testing...
              </>
            ) : (
              'Test Connection'
            )}
          </button>

          {connectionTestStatus === 'success' && (
            <div className="flex items-center gap-1.5 text-sm font-medium" style={{ color: '#22d97f' }}>
              <CheckCircle size={16} />
              <span>Connected</span>
            </div>
          )}

          {connectionTestStatus === 'failed' && (
            <div className="flex items-center gap-1.5 text-sm font-medium" style={{ color: 'var(--accent-danger)' }}>
              <XCircle size={16} />
              <span>Failed</span>
            </div>
          )}
        </div>

        {connectionTestMessage && connectionTestStatus === 'failed' && (
          <p className="mt-2 text-xs" style={{ color: 'var(--accent-danger)' }}>{connectionTestMessage}</p>
        )}

        {connectionTestStatus === 'idle' && (
          <p className="mt-2 text-xs text-theme-muted">
            A successful connection test is required before adding the host.
          </p>
        )}
      </div>
    </div>
  );
}

export default StandaloneAuthSection;
