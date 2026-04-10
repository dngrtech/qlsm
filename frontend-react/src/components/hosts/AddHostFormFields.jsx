import React, { useRef } from 'react';
import { Upload, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import FloatingListbox from '../common/FloatingListbox';
import { providerOptions } from '../../utils/providerData';
import { HOST_NAME_MAX_LENGTH, HOST_NAME_PATTERN } from '../../utils/resourceValidation';
import { STANDALONE_TIMEZONES } from '../../utils/formatters';
import SelfHostFields from './SelfHostFields';

const inputClass = 'mt-1 block w-full px-3 py-2 rounded-lg text-sm text-theme-primary placeholder:text-theme-muted focus:outline-none focus:ring-1 transition-colors';
const inputFocusRing = 'focus:ring-[var(--accent-primary)] focus:border-[var(--accent-primary)]';
const inputStyle = { background: 'var(--surface-elevated)', border: '1px solid var(--surface-border)' };
const labelClass = 'block text-sm font-medium text-theme-secondary';

function AddHostFormFields({
  name,
  onNameChange,
  nameError,
  onNameBlur,
  provider,
  onProviderChange,
  selectedContinent,
  onContinentChange,
  vultrContinentOptions,
  region,
  onRegionChange,
  vultrFilteredRegions,
  machineSize,
  onMachineSizeChange,
  currentSizes,
  ipAddress,
  onIpAddressChange,
  sshPort,
  onSshPortChange,
  sshUser,
  onSshUserChange,
  sshKey,
  onSshKeyChange,
  osType,
  onOsTypeChange,
  timezone,
  onTimezoneChange,
  connectionTestStatus,
  connectionTestMessage,
  onTestConnection,
}) {
  const fileInputRef = useRef(null);
  const providerLabels = {
    standalone: 'Standalone',
    self: 'QLSM Host (self)',
  };
  const providerListOptions = Object.keys(providerOptions).map(pKey => ({
    id: pKey,
    name: providerLabels[pKey] || pKey.toUpperCase()
  }));

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

  const isStandalone = provider === 'standalone';
  const isSelf = provider === 'self';

  return (
    <>
      {/* Host Name */}
      <div>
        <label htmlFor="modal-name" className={labelClass}>Host Name</label>
        <input
          id="modal-name"
          type="text"
          value={name}
          onChange={onNameChange}
          onBlur={onNameBlur}
          required
          maxLength={HOST_NAME_MAX_LENGTH}
          pattern={HOST_NAME_PATTERN.source}
          title="Lowercase letters, numbers, and hyphens only. Must start and end with a letter or number."
          className={`${inputClass} ${inputFocusRing}`}
          style={nameError ? { ...inputStyle, borderColor: 'var(--accent-danger)' } : inputStyle}
          placeholder="e.g., my-vultr-server"
        />
        {nameError && (
          <p className="mt-1.5 text-xs" style={{ color: 'var(--accent-danger)' }}>{nameError}</p>
        )}
      </div>

      {/* Provider */}
      <FloatingListbox
        label="Provider"
        value={provider}
        onChange={onProviderChange}
        options={providerListOptions}
        getOptionKey={(opt) => opt.id}
        getOptionDisplay={(opt) => opt.name}
        getSelectedDisplay={(val, opts) => {
          if (!val) return 'Select Provider';
          const selectedOpt = opts.find(o => o.id === val);
          return selectedOpt ? selectedOpt.name : 'Select Provider';
        }}
      />

      {/* Cloud provider fields */}
      {!isStandalone && !isSelf && (
        <>
          {provider === 'vultr' && (
            <FloatingListbox
              label="Continent"
              value={selectedContinent}
              onChange={onContinentChange}
              options={vultrContinentOptions}
              getOptionKey={(opt) => opt.id}
              getOptionValue={(opt) => opt.name}
              getOptionDisplay={(opt) => opt.name}
              getSelectedDisplay={(val, opts) => {
                if (!val) return 'Select Continent';
                const selectedOpt = opts.find(o => o.name === val);
                return selectedOpt ? selectedOpt.name : 'Select Continent';
              }}
            />
          )}

          <FloatingListbox
            label="Region"
            value={region}
            onChange={onRegionChange}
            options={provider === 'vultr' ? vultrFilteredRegions : (providerOptions[provider]?.regions || [])}
            disabled={(provider === 'vultr' && !selectedContinent) || (provider !== 'vultr' && (providerOptions[provider]?.regions?.length || 0) === 0)}
            getOptionKey={(opt) => opt.id}
            getOptionDisplay={(opt) => provider === 'vultr' ? `${opt.city} (${opt.country})` : opt.name}
            getSelectedDisplay={(val, opts) => {
              if (!val) return 'Select Region';
              const selectedOpt = opts.find(o => o.id === val);
              if (!selectedOpt) return 'Select Region';
              return provider === 'vultr' ? `${selectedOpt.city} (${selectedOpt.country})` : selectedOpt.name;
            }}
            noOptionsMessage={
              ((provider === 'vultr' && vultrFilteredRegions.length === 0 && selectedContinent) || (provider !== 'vultr' && (providerOptions[provider]?.regions?.length || 0) === 0))
                ? "No regions available for this selection."
                : "No regions available."
            }
          />

          <FloatingListbox
            label="Machine Size / Plan"
            value={machineSize}
            onChange={onMachineSizeChange}
            options={currentSizes}
            disabled={!provider || currentSizes.length === 0}
            getOptionKey={(opt) => opt.id}
            getOptionDisplay={(opt) => opt.name}
            getSelectedDisplay={(val, opts) => {
              if (!val) return 'Select Size';
              const selectedOpt = opts.find(o => o.id === val);
              return selectedOpt ? selectedOpt.name : 'Select Size';
            }}
            noOptionsMessage="No sizes available for this provider."
          />
        </>
      )}

      {isSelf && (
        <>
          <div
            className="rounded-lg px-3.5 py-3 text-sm text-theme-secondary"
            style={{
              background: 'rgba(0, 255, 157, 0.08)',
              border: '1px solid rgba(0, 255, 157, 0.2)',
            }}
          >
            Deploys game servers on this machine. SSH keys are generated and configured automatically.
          </div>
          <SelfHostFields
            sshUser={sshUser}
            onSshUserChange={onSshUserChange}
            timezone={timezone}
            onTimezoneChange={onTimezoneChange}
          />
        </>
      )}

      {/* Standalone provider fields */}
      {isStandalone && (
        <>
          <div>
            <label htmlFor="modal-ip-address" className={labelClass}>IP Address</label>
            <input
              id="modal-ip-address"
              type="text"
              value={ipAddress || ''}
              onChange={onIpAddressChange}
              required
              placeholder="e.g., 192.168.1.100"
              className={`${inputClass} ${inputFocusRing}`}
              style={inputStyle}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="modal-ssh-port" className={labelClass}>SSH Port</label>
              <input
                id="modal-ssh-port"
                type="number"
                value={sshPort || 22}
                onChange={onSshPortChange}
                min="1"
                max="65535"
                className={`${inputClass} ${inputFocusRing}`}
                style={inputStyle}
              />
            </div>
            <div>
              <label htmlFor="modal-ssh-user" className={labelClass}>SSH Username</label>
              <input
                id="modal-ssh-user"
                type="text"
                value={sshUser || 'root'}
                onChange={onSshUserChange}
                required
                placeholder="root"
                className={`${inputClass} ${inputFocusRing}`}
                style={inputStyle}
              />
            </div>
          </div>

          <FloatingListbox
            label="Operating System"
            value={osType || 'debian12'}
            onChange={onOsTypeChange}
            options={providerOptions.standalone.osTypes}
            getOptionKey={(opt) => opt.id}
            getOptionDisplay={(opt) => opt.name}
            getSelectedDisplay={(val, opts) => {
              if (!val) return 'Select OS';
              const selectedOpt = opts.find(o => o.id === val);
              return selectedOpt ? selectedOpt.name : 'Select OS';
            }}
          />

          <FloatingListbox
            label="Timezone"
            value={timezone || ''}
            onChange={onTimezoneChange}
            options={STANDALONE_TIMEZONES.map(tz => ({ id: tz, name: tz }))}
            getOptionKey={(opt) => opt.id}
            getOptionDisplay={(opt) => opt.name}
            getSelectedDisplay={(val) => val || 'Select Timezone...'}
            noOptionsMessage="No timezones available."
          />

          {/* SSH Key */}
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

          {/* Test Connection */}
          <div className="pt-1">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onTestConnection}
                disabled={!ipAddress || !sshKey || connectionTestStatus === 'testing'}
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
        </>
      )}
    </>
  );
}

export default AddHostFormFields;
