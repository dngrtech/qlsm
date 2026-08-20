import { Zap } from 'lucide-react';
import InfoTooltip from '../common/InfoTooltip';

const PASSWORD_INPUT_BASE = 'w-44 rounded py-1.5 px-2 text-sm font-mono border bg-[var(--surface-raised)] text-[var(--text-primary)] transition-colors focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed';

function InstanceOptionsRow({
  lanRateEnabled, onLanRateChange,
  lanRateDisabled = false,
  lanRateUnavailableReason = null,
  autoGeneratePasswords = true, onAutoGeneratePasswordsChange,
  zmqStatsPassword = '', onZmqStatsPasswordChange,
  zmqRconPassword = '', onZmqRconPasswordChange,
  passwordErrors = {},
}) {
  const inputClass = (hasError) => (
    `${PASSWORD_INPUT_BASE} ${hasError
      ? 'border-[var(--accent-danger)]'
      : 'border-[var(--surface-border)] focus:border-[var(--accent-primary)]'}`
  );

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onLanRateChange(!lanRateEnabled)}
          className="neu-toggle"
          aria-pressed={lanRateEnabled}
          disabled={lanRateDisabled}
        >
          <span className="sr-only">Toggle 99k LAN Rate</span>
          <span className={`neu-toggle__track ${lanRateEnabled ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
            <span className={`neu-toggle__knob ${lanRateEnabled ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
          </span>
        </button>
        <span className="flex items-center gap-1.5 text-sm font-medium text-[var(--text-primary)]">
          <Zap size={16} className={`mr-1 ${lanRateEnabled ? 'text-[var(--accent-warning)]' : 'text-[var(--text-muted)]'}`} />
          <span>99k LAN Rate</span>
          {lanRateUnavailableReason && (
            <InfoTooltip text={lanRateUnavailableReason} variant="danger" size={14} />
          )}
        </span>
      </div>

      <span className="h-6 w-px bg-[var(--surface-border)]" aria-hidden="true" />

      <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)] cursor-pointer select-none">
        <input
          type="checkbox"
          aria-label="Auto Generate Passwords"
          checked={autoGeneratePasswords}
          onChange={(event) => onAutoGeneratePasswordsChange(event.target.checked)}
          className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0"
        />
        Auto Generate Passwords
        <InfoTooltip
          text="ZMQ stats and RCON passwords are generated for you at deploy time. Turn this off to set them yourself."
          size={14}
        />
      </label>

      <input
        id="zmq_stats_password"
        aria-label="ZMQ Stats Password"
        aria-invalid={Boolean(passwordErrors.stats)}
        type="text"
        value={zmqStatsPassword}
        onChange={(event) => onZmqStatsPasswordChange(event.target.value)}
        disabled={autoGeneratePasswords}
        maxLength={64}
        placeholder={autoGeneratePasswords ? 'Auto-generated' : 'ZMQ Stats Password'}
        className={inputClass(passwordErrors.stats)}
      />
      <input
        id="zmq_rcon_password"
        aria-label="ZMQ RCON Password"
        aria-invalid={Boolean(passwordErrors.rcon)}
        type="text"
        value={zmqRconPassword}
        onChange={(event) => onZmqRconPasswordChange(event.target.value)}
        disabled={autoGeneratePasswords}
        maxLength={64}
        placeholder={autoGeneratePasswords ? 'Auto-generated' : 'ZMQ RCON Password'}
        className={inputClass(passwordErrors.rcon)}
      />
    </div>
  );
}

export default InstanceOptionsRow;
