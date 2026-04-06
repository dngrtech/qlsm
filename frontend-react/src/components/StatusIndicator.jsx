import { formatStatus } from '../utils/formatters';
import { useTheme } from '../context/ThemeContext';
import InfoTooltip from './common/InfoTooltip';

const DEFAULT_POLLABLE_STATUSES = ['deploying', 'deleting', 'restarting', 'configuring', 'provisioning', 'installing', 'stopping', 'starting'];

function StatusIndicator({ status, pollableStatuses = DEFAULT_POLLABLE_STATUSES }) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const lowerStatus = status?.toLowerCase();
  const isPollable = pollableStatuses.includes(lowerStatus);
  const isRunning = lowerStatus === 'running';
  const isActive = lowerStatus === 'active';
  const isUpdated = lowerStatus === 'updated';
  const isStoppedOrIdle = lowerStatus === 'stopped' || lowerStatus === 'idle';
  const isError = lowerStatus === 'error';

  let bgColor, textColor;

  if (isRunning || isActive) {
    bgColor = isDark ? 'rgba(34, 217, 127, 0.12)' : 'rgba(13, 150, 104, 0.1)';
    textColor = isDark ? '#22d97f' : '#0D9668';
  } else if (isUpdated) {
    bgColor = isDark ? 'rgba(34, 211, 238, 0.12)' : 'rgba(8, 145, 178, 0.1)';
    textColor = isDark ? '#22d3ee' : '#0891b2';
  } else if (isPollable && lowerStatus !== 'deleting') {
    bgColor = isDark ? 'rgba(245, 158, 11, 0.12)' : 'rgba(217, 119, 6, 0.1)';
    textColor = isDark ? '#f59e0b' : '#B45309';
  } else if (isStoppedOrIdle || isError || lowerStatus === 'deleting') {
    bgColor = isDark ? 'rgba(239, 68, 68, 0.12)' : 'rgba(220, 38, 38, 0.08)';
    textColor = isDark ? '#ef4444' : '#DC2626';
  } else {
    bgColor = isDark ? 'rgba(100, 116, 139, 0.12)' : 'rgba(62, 76, 94, 0.08)';
    textColor = isDark ? '#64748b' : '#3E4C5E';
  }

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '6px',
        padding: '4px 0',
        width: '110px',
        fontSize: '12px',
        fontWeight: 600,
        letterSpacing: '0.5px',
        textTransform: 'uppercase',
        borderRadius: '20px',
        background: bgColor,
        color: textColor,
        whiteSpace: 'nowrap',
      }}
    >
      {isUpdated ? (
        <InfoTooltip
          text="Configuration has been synced to the host but the instance has not been restarted. Restart to apply changes."
          variant="cyan"
          size={12}
        />
      ) : (
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: textColor,
            flexShrink: 0,
            animation: (isPollable || isRunning || isActive) ? 'statusPulse 2s infinite' : 'none',
          }}
        />
      )}
      {formatStatus(status)}
      <style>{`
        @keyframes statusPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </span>
  );
}

export default StatusIndicator;
