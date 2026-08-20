export const SUPPORTED_LAN_RATE_OS_TYPES = new Set(['debian']);

const OS_ALIASES = {
  debian12: 'debian',
};

function normalizeOs(osType) {
  const lower = (osType || '').toLowerCase();
  return OS_ALIASES[lower] || lower;
}

/**
 * Migration-aware: returns true if the host has been migrated to the
 * LD_PRELOAD hook mechanism, regardless of OS. Legacy hosts fall back
 * to the Debian-only OS check.
 *
 * @param {Object} host — { os_type, lan_rate_uses_hook }
 *   For instance-scoped components, pass
 *   { os_type: instance.host_os_type, lan_rate_uses_hook: instance.host_lan_rate_uses_hook }
 */
export function isLanRateSupported(host) {
  if (host && host.lan_rate_uses_hook === true) {
    return true;
  }
  return SUPPORTED_LAN_RATE_OS_TYPES.has(normalizeOs(host && host.os_type));
}

/**
 * Migration-aware: empty string when supported; actionable migration
 * hint for legacy hosts on unsupported OSes.
 */
export function getLanRateUnsupportedMessage(host) {
  if (!host || host.lan_rate_uses_hook === true) {
    return '';
  }
  if (SUPPORTED_LAN_RATE_OS_TYPES.has(normalizeOs(host.os_type))) {
    return '';
  }
  return (
    "99k LAN Rate currently requires Debian on this host. To enable it on " +
    "Ubuntu (and other OSes), run 'Re-run Host Setup' from the host actions " +
    "menu — this migrates the host to the new LD_PRELOAD hook mechanism " +
    "that works on any OS."
  );
}

/**
 * Migration-aware wrapper compatible with the deleted canEnableLanRate API.
 * Returns true if enabling is permitted.
 */
export function canEnableLanRate({ host, currentEnabled }) {
  if (currentEnabled === true) {
    return true;
  }
  return isLanRateSupported(host);
}
