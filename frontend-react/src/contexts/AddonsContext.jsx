import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { listAddons } from '../services/addons';
import { useAuth } from './AuthContext';
import { MOUNT_SCOPES } from '../components/addons/panelRoute';

// One catalog fetch per session, shared by every mount point. Menus render on
// every row of the servers table, so per-menu fetching would mean dozens of
// identical requests on one page.
const AddonsContext = createContext({
  addons: [],
  loading: false,
  error: null,
  reload: () => {},
  mounts: () => [],
});

/**
 * Entries one addon mounts at one extension point.
 *
 * Split out of the `mounts()` callback below so a single addon's entries can
 * be computed straight from its catalog entry (e.g. an addon card's own
 * settings button) without iterating the whole addon list for one id.
 *
 * Only an addon that actually loaded and whose declared ui_api this core
 * implements contributes. A broken or too-new addon stays visible on the
 * Addons list with its reason, but must not inject half-working UI.
 */
export function mountEntriesForAddon(addon, point) {
  const out = [];
  if (!addon || !addon.loaded || !addon.ui_mountable) return out;
  // Every addon (bundled or uploaded) stays hidden from operator-facing
  // surfaces until switched on from the Addons page (default off).
  // `settings_section` is exempt so an addon can be configured before being
  // turned on.
  if (!addon.enabled && point !== 'settings_section') return out;
  const declared = addon.ui?.[point];
  if (!declared) return out;
  const scope = MOUNT_SCOPES[point];
  const entries = Array.isArray(declared) ? declared : [declared];
  entries.forEach((entry, index) => {
    if (!entry || typeof entry !== 'object') return;
    const panel = entry.panel ? addon.ui?.panels?.[entry.panel] : null;
    if (entry.panel && !panel) return;  // manifest validation should have caught this
    out.push({
      key: `${addon.id}:${point}:${entry.id || index}`,
      addon,
      entry,
      panel,
      scope,
      // A malformed manifest label (not a non-empty string) must not reach
      // React as a child; fall back to the addon's name, then its id.
      label: textOr(entry.label) || textOr(addon.name) || addon.id,
      icon: entry.icon,
    });
  });
  return out;
}

function textOr(value) {
  return typeof value === 'string' && value.trim() ? value : null;
}

export function AddonsProvider({ children }) {
  const [addons, setAddons] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const { isAuthenticated } = useAuth();

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAddons(await listAddons());
    } catch (err) {
      // Non-fatal by design: qlsm's own pages must keep working when the
      // addon catalog cannot be read. The UI simply shows no addon entries.
      setAddons([]);
      setError(err?.response?.data?.error?.message || 'Failed to load addons');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) reload();
    else setAddons([]);
  }, [isAuthenticated, reload]);

  /**
   * Entries mounted at one extension point, flattened across addons.
   *
   * Only addons that actually loaded and whose declared ui_api this core
   * implements contribute. A broken or too-new addon stays visible on the
   * Addons list with its reason, but must not inject half-working UI into a
   * host's action menu.
   */
  const mounts = useCallback((point) => {
    const out = [];
    for (const addon of addons) out.push(...mountEntriesForAddon(addon, point));
    return out;
  }, [addons]);

  const value = useMemo(
    () => ({ addons, loading, error, reload, mounts }),
    [addons, loading, error, reload, mounts],
  );

  return <AddonsContext.Provider value={value}>{children}</AddonsContext.Provider>;
}

export function useAddons() {
  return useContext(AddonsContext);
}

export function useAddonMounts(point) {
  const { mounts } = useAddons();
  return mounts(point);
}

export default AddonsContext;
