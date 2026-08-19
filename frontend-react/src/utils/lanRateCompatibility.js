export const SUPPORTED_LAN_RATE_OS_TYPES = new Set(['debian']);

const OS_ALIASES = {
  debian12: 'debian',
};

export const ALWAYS_ON_LAN_RATE_MESSAGE =
  '99k LAN rate is always on for minqlxtended hosts — the runtime treats ' +
  'every client as a LAN address itself, so this setting cannot be changed.';

function normalizeOs(osType) {
  const lower = (osType || '').toLowerCase();
  return OS_ALIASES[lower] || lower;
}

/**
 * minqlxtended hooks Sys_IsLANAddress unconditionally and QLSM excludes
 * force_rate.so on it, so neither the hook path nor the legacy iptables path
 * is reachable. Mirrors lan_rate_always_on() in ui/lan_rate_policy.py.
 *
 * @param {Object} host — { os_type, lan_rate_uses_hook, runtime }
 *   For instance-scoped components, pass
 *   { os_type: instance.host_os_type,
 *     lan_rate_uses_hook: instance.host_lan_rate_uses_hook,
 *     runtime: instance.host_runtime }
 */
export function isLanRateAlwaysOn(host) {
  const runtime = host && typeof host.runtime === 'string'
    ? host.runtime.trim().toLowerCase()
    : '';
  return runtime === 'minqlxtended';
}

/**
 * Migration-aware: returns true if the runtime provides 99k unconditionally,
 * or if the host has been migrated to the LD_PRELOAD hook mechanism,
 * regardless of OS. Legacy hosts fall back to the Debian-only OS check.
 *
 * @param {Object} host — { os_type, lan_rate_uses_hook, runtime }
 *   For instance-scoped components, pass
 *   { os_type: instance.host_os_type,
 *     lan_rate_uses_hook: instance.host_lan_rate_uses_hook,
 *     runtime: instance.host_runtime }
 */
export function isLanRateSupported(host) {
  if (isLanRateAlwaysOn(host)) {
    // Fixed on, not unsupported: reporting false here would make the UI offer
    // to "fix" a host that already has it.
    return true;
  }
  if (host && host.lan_rate_uses_hook === true) {
    return true;
  }
  return SUPPORTED_LAN_RATE_OS_TYPES.has(normalizeOs(host && host.os_type));
}

/**
 * Migration-aware: explains the fixed-on state on minqlxtended; empty string
 * when supported and changeable; actionable migration hint for legacy hosts
 * on unsupported OSes.
 *
 * @param {Object} host — { os_type, lan_rate_uses_hook, runtime }
 */
export function getLanRateUnsupportedMessage(host) {
  if (isLanRateAlwaysOn(host)) {
    return ALWAYS_ON_LAN_RATE_MESSAGE;
  }
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
 * Returns true if enabling is permitted. Note this answers "may it be on",
 * not "may the operator change it" — callers must also check
 * isLanRateAlwaysOn() before offering a toggle.
 *
 * @param {Object} params.host — { os_type, lan_rate_uses_hook, runtime }
 */
export function canEnableLanRate({ host, currentEnabled }) {
  if (currentEnabled === true) {
    return true;
  }
  return isLanRateSupported(host);
}
