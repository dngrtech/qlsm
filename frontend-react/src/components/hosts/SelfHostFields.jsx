import React from 'react';
import FloatingListbox from '../common/FloatingListbox';
import { STANDALONE_TIMEZONES } from '../../utils/formatters';

const inputClass = 'mt-1 block w-full px-3 py-2 rounded-lg text-sm text-theme-primary placeholder:text-theme-muted focus:outline-none focus:ring-1 transition-colors';
const inputFocusRing = 'focus:ring-[var(--accent-primary)] focus:border-[var(--accent-primary)]';
const inputStyle = { background: 'var(--surface-elevated)', border: '1px solid var(--surface-border)' };
const labelClass = 'block text-sm font-medium text-theme-secondary';

function SelfHostFields({ ipAddress, onIpAddressChange, sshUser, onSshUserChange, timezone, onTimezoneChange }) {
  return (
    <>
      <div>
        <label htmlFor="modal-self-ip" className={labelClass}>
          Host Public IP <span style={{ color: 'var(--accent-danger)' }}>*</span>
        </label>
        <input
          id="modal-self-ip"
          type="text"
          value={ipAddress || ''}
          onChange={onIpAddressChange}
          required
          placeholder="e.g. 203.0.113.10"
          className={`${inputClass} ${inputFocusRing}`}
          style={inputStyle}
        />
        <p className="mt-1 text-xs text-theme-muted">
          Public IP of this server. Set <code>QLSM_HOST_IP</code> in <code>.env</code> to pre-fill automatically.
        </p>
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
        <label htmlFor="modal-self-ssh-user" className={labelClass}>SSH User</label>
        <input
          id="modal-self-ssh-user"
          type="text"
          value={sshUser || ''}
          onChange={onSshUserChange}
          required
          placeholder="root"
          className={`${inputClass} ${inputFocusRing}`}
          style={inputStyle}
        />
        {sshUser !== 'root' && (
          <p className="mt-2 text-xs text-theme-muted">
            Must have passwordless sudo on this machine.
          </p>
        )}
      </div>
    </>
  );
}

export default SelfHostFields;
