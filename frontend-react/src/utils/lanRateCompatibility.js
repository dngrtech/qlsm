export const SUPPORTED_LAN_RATE_OS_TYPES = new Set(['debian']);
export const UBUNTU_99K_LAN_RATE_MESSAGE = '99k LAN rate is not compatible with Ubuntu.';
export const UNKNOWN_99K_LAN_RATE_MESSAGE = '99k LAN rate is only supported on Debian hosts.';

function normalizeOsType(osType) {
  if (typeof osType !== 'string') return null;
  const normalized = osType.trim().toLowerCase();
  return normalized || null;
}

export function isLanRateSupported(osType) {
  return SUPPORTED_LAN_RATE_OS_TYPES.has(normalizeOsType(osType));
}

export function getLanRateUnsupportedReason(osType) {
  const normalized = normalizeOsType(osType);
  if (isLanRateSupported(normalized)) return null;
  return normalized === 'ubuntu' ? UBUNTU_99K_LAN_RATE_MESSAGE : UNKNOWN_99K_LAN_RATE_MESSAGE;
}

export function canEnableLanRate({ osType, currentEnabled }) {
  if (isLanRateSupported(osType)) return true;
  return currentEnabled === true;
}
