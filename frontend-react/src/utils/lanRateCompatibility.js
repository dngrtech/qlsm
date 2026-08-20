export const SUPPORTED_LAN_RATE_OS_TYPES = new Set(['debian']);

const OS_ALIASES = {
  debian12: 'debian',
};

/**
 * Mirrors FORCED_LAN_RATE_MESSAGE in ui/lan_rate_policy.py.
 */
export const FORCED_LAN_RATE_MESSAGE =
  'QLSM runs minqlxtended hosts at 99k LAN rate and does not offer 25k on ' +
  'this runtime, so this setting is fixed on.';

function normalizeOs(osType) {
  const lower = (osType || '').toLowerCase();
  return OS_ALIASES[lower] || lower;
}

/**
 * Whether QLSM fixes 99k LAN rate on for this host — a product decision, not
 * engine behaviour. Mirrors lan_rate_forced_on() in ui/lan_rate_policy.py,
 * which is what makes the backend emit `sv_lanForceRate 1` there. Callers must
 * render the toggle as on and disabled when this is true, so the UI matches the
 * cvar the backend actually writes.
 *
 * @param {Object} host — { os_type, lan_rate_uses_hook, runtime }
 *   For instance-scoped components, pass
 *   { os_type: instance.host_os_type,
 *     lan_rate_uses_hook: instance.host_lan_rate_uses_hook,
 *     runtime: instance.host_runtime }
 */
export function isLanRateForcedOn(host) {
  const runtime = host && typeof host.runtime === 'string'
    ? host.runtime.trim().toLowerCase()
    : '';
  return runtime === 'minqlxtended';
}

/**
 * Migration-aware: returns true if the host has been migrated to the
 * LD_PRELOAD hook mechanism, regardless of OS. Legacy hosts fall back
 * to the Debian-only OS check.
 *
 * @param {Object} host — { os_type, lan_rate_uses_hook, runtime }
 */
export function isLanRateSupported(host) {
  if (isLanRateForcedOn(host)) {
    // Fixed on, not unsupported: reporting false here would make the UI offer
    // to "fix" a host that is already running what QLSM intends.
    return true;
  }
  if (host && host.lan_rate_uses_hook === true) {
    return true;
  }
  return SUPPORTED_LAN_RATE_OS_TYPES.has(normalizeOs(host && host.os_type));
}

/**
 * The reason the toggle is not the operator's to set on this host: the fixed-on
 * policy message on minqlxtended, an actionable migration hint for legacy hosts
 * on unsupported OSes, and an empty string when it is freely settable.
 *
 * @param {Object} host — { os_type, lan_rate_uses_hook, runtime }
 */
export function getLanRateUnsupportedMessage(host) {
  if (isLanRateForcedOn(host)) {
    return FORCED_LAN_RATE_MESSAGE;
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
 * Returns true if 99k is permitted to be on. Note this answers "may it be on",
 * not "may the operator change it" — callers must also check
 * isLanRateForcedOn() before offering an editable toggle.
 *
 * @param {Object} params.host — { os_type, lan_rate_uses_hook, runtime }
 */
export function canEnableLanRate({ host, currentEnabled }) {
  if (currentEnabled === true) {
    return true;
  }
  return isLanRateSupported(host);
}
