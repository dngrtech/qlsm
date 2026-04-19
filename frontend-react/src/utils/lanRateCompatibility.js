export const UBUNTU_99K_LAN_RATE_MESSAGE = '99k LAN rate is not compatible with Ubuntu.';

export function isLanRateSupported(osType) {
  return osType !== 'ubuntu';
}

export function getLanRateUnsupportedReason(osType) {
  return osType === 'ubuntu' ? UBUNTU_99K_LAN_RATE_MESSAGE : null;
}

export function canEnableLanRate({ osType, currentEnabled }) {
  if (isLanRateSupported(osType)) return true;
  return currentEnabled === true;
}
