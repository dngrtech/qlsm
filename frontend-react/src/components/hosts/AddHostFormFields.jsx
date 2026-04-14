import React from 'react';
import FloatingListbox from '../common/FloatingListbox';
import { providerOptions } from '../../utils/providerData';
import { HOST_NAME_MAX_LENGTH, HOST_NAME_PATTERN } from '../../utils/resourceValidation';
import { STANDALONE_TIMEZONES } from '../../utils/formatters';
import SelfHostFields from './SelfHostFields';
import StandaloneAuthSection from './StandaloneAuthSection';

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
  providerListOptions,
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
  standaloneAuthMethod,
  onStandaloneAuthMethodChange,
  sshKey,
  onSshKeyChange,
  sshPassword,
  onSshPasswordChange,
  timezone,
  onTimezoneChange,
  connectionTestStatus,
  connectionTestMessage,
  onTestConnection,
}) {
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
            ipAddress={ipAddress}
            onIpAddressChange={onIpAddressChange}
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
          <div
            className="rounded-lg px-3.5 py-3 text-sm text-theme-secondary"
            style={{
              background: 'rgba(0, 255, 157, 0.08)',
              border: '1px solid rgba(0, 255, 157, 0.2)',
            }}
          >
            Operating system is detected automatically during connection test and setup.
          </div>

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

          <StandaloneAuthSection
            authMethod={standaloneAuthMethod}
            onAuthMethodChange={onStandaloneAuthMethodChange}
            sshKey={sshKey}
            onSshKeyChange={onSshKeyChange}
            sshPassword={sshPassword}
            onSshPasswordChange={onSshPasswordChange}
            ipAddress={ipAddress}
            sshUser={sshUser}
            connectionTestStatus={connectionTestStatus}
            connectionTestMessage={connectionTestMessage}
            onTestConnection={onTestConnection}
          />
        </>
      )}
    </>
  );
}

export default AddHostFormFields;
