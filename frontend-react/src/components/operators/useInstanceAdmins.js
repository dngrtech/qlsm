import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getInstanceAdmins } from '../../services/api';

// Merges QLSM's stored admin rows with the live minqlx levels read off the
// server. The *parent* owns the edited list: `entries` is null until the user
// touches something, and only the mutators call onChange. Nothing is ever
// mirrored upward from an effect -- that loops forever (parent setState -> new
// prop reference -> new memo array -> effect again) and it would also mark the
// modal dirty on open and send an empty admin list on a save that raced the
// initial GET, revoking everyone.
export default function useInstanceAdmins({ instanceId, active, entries, onChange, onLoaded }) {
  const [stored, setStored] = useState([]);
  const [live, setLive] = useState(null);
  const [managed, setManaged] = useState(null);
  const [liveError, setLiveError] = useState(null);
  const [loading, setLoading] = useState(false);

  // onLoaded typically closes over parent state-setters, so a real caller
  // passes it inline and its identity changes every render. Keeping it out of
  // load's dependency array via a ref (updated every render, never a fetch
  // trigger) is what stops that from recreating `load` -> re-firing the mount
  // effect below -> refetching -> calling onLoaded -> parent re-render -> loop.
  const onLoadedRef = useRef(onLoaded);
  useEffect(() => { onLoadedRef.current = onLoaded; });

  // Refresh replaces server state only. The user's pending edits live in the
  // parent and are deliberately untouched: Refresh shows in-game changes, it is
  // not a discard button.
  const load = useCallback(async () => {
    if (!instanceId) return;
    setLoading(true);
    try {
      const data = await getInstanceAdmins(instanceId);
      setStored(data.stored || []);
      setLive(data.live ?? null);
      setManaged(data.managed ?? null);
      setLiveError(data.live_error || null);
      // Non-dirtying: lets the parent save-as-preset an untouched list. The
      // parent must not feed this back in as `entries`.
      if (onLoadedRef.current) {
        onLoadedRef.current((data.stored || []).map((r) => ({ steam_id64: r.steam_id64, level: r.level })));
      }
    } catch (err) {
      setLiveError(err?.error?.message || 'Could not load the admin list.');
    } finally {
      setLoading(false);
    }
  }, [instanceId]);

  useEffect(() => { if (active) load(); }, [active, load]);

  const storedEntries = useMemo(
    () => (stored || []).map((row) => ({ steam_id64: row.steam_id64, level: row.level })),
    [stored],
  );
  // Untouched: show what the server has (or, with no instance, the parent's list).
  const effectiveEntries = entries ?? storedEntries;

  const rows = useMemo(() => {
    // live === null means the read failed or there was nothing to read. No row
    // may then claim to be managed or pending -- the banner says why instead.
    const liveKnown = live !== null && live !== undefined;
    const listed = new Set(effectiveEntries.map((e) => e.steam_id64));
    const managedSet = new Set(managed || []);

    const merged = effectiveEntries.map(({ steam_id64: steamId, level }) => ({
      steamId,
      level,
      state: !liveKnown
        ? 'unknown'
        : (managedSet.has(steamId) && live[steamId] === level ? 'managed' : 'pending'),
    }));

    if (liveKnown) {
      Object.entries(live).forEach(([steamId, level]) => {
        if (listed.has(steamId)) return;
        if (level <= 0) return; // a key set to 0 is a revoked admin, not an admin
        merged.push({
          steamId,
          level,
          // In the managed set with no stored row: QLSM pushed this and lost the
          // row, so the next save resets it to 0 unless it is adopted.
          state: managedSet.has(steamId) ? 'will-be-revoked' : 'live-only',
        });
      });
    }
    return merged;
  }, [effectiveEntries, live, managed]);

  const emit = useCallback((next) => { if (onChange) onChange(next); }, [onChange]);

  const addAdmin = useCallback((steamId, level) => {
    emit([
      ...effectiveEntries.filter((e) => e.steam_id64 !== steamId),
      { steam_id64: steamId, level: Number(level) },
    ]);
  }, [effectiveEntries, emit]);

  const removeAdmin = useCallback((steamId) => {
    emit(effectiveEntries.filter((e) => e.steam_id64 !== steamId));
  }, [effectiveEntries, emit]);

  const adoptAdmin = useCallback((steamId) => {
    const level = (live || {})[steamId];
    if (level === undefined) return;
    emit([...effectiveEntries, { steam_id64: steamId, level }]);
  }, [effectiveEntries, live, emit]);

  return {
    rows,
    loading,
    liveError,
    refresh: load,
    addAdmin,
    removeAdmin,
    adoptAdmin,
    effectiveEntries,
    dirty: entries !== null && entries !== undefined,
  };
}
