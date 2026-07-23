import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { buildRconHosts } from '../utils/rconTargets';
const TARGETS_PREFIX = 'qlsm-global-rcon-targets-';
const EXPANDED_PREFIX = 'qlsm-global-rcon-expanded-hosts-';

function keysFor(userId) {
  if (userId === null || userId === undefined) return null;
  return {
    targets: `${TARGETS_PREFIX}${userId}`,
    expanded: `${EXPANDED_PREFIX}${userId}`,
  };
}
function readArray(key) {
  if (!key) return [];
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? '[]');
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}
function loadPreferences(userId) {
  const keys = keysFor(userId);
  return {
    userId,
    selectedKeys: new Set(readArray(keys?.targets).filter((value) => typeof value === 'string')),
    expandedHostIds: new Set(readArray(keys?.expanded).filter((value) => ['string', 'number'].includes(typeof value))),
  };
}
function writeSet(key, values) {
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify([...values]));
  } catch {
    // localStorage can be unavailable, full, or blocked. State remains usable in memory.
  }
}
function sameSet(left, right) {
  return left.size === right.size && [...left].every((value) => right.has(value));
}
export function useGlobalRconPreferences({
  hosts = [], instances = [], hostOrder, inventoryReady = false,
} = {}) {
  const { currentUser } = useAuth();
  const userId = currentUser?.id ?? null;
  const loaded = useMemo(() => loadPreferences(userId), [userId]);
  const [stored, setStored] = useState(loaded);
  const active = stored.userId === userId ? stored : loaded;
  const storageKeys = keysFor(userId);

  const rconHosts = useMemo(
    () => buildRconHosts(hosts, instances, { hostOrder }),
    [hostOrder, hosts, instances],
  );
  const inventoryKeys = useMemo(
    () => new Set(rconHosts.flatMap((host) => host.instances.map((instance) => instance.key))),
    [rconHosts],
  );
  const eligibleKeys = useMemo(
    () => new Set(rconHosts.flatMap((host) => host.instances.filter((instance) => instance.eligible).map((instance) => instance.key))),
    [rconHosts],
  );
  const hostIds = useMemo(() => new Set(hosts.map((host) => host.id)), [hosts]);

  const selectedKeys = useMemo(
    () => inventoryReady
      ? new Set([...active.selectedKeys].filter((key) => inventoryKeys.has(key)))
      : new Set(active.selectedKeys),
    [active.selectedKeys, inventoryKeys, inventoryReady],
  );
  const expandedHostIds = useMemo(
    () => inventoryReady
      ? new Set([...active.expandedHostIds].filter((id) => hostIds.has(id)))
      : new Set(active.expandedHostIds),
    [active.expandedHostIds, hostIds, inventoryReady],
  );
  useEffect(() => {
    const identityChanged = stored.userId !== userId;
    const selectedChanged = !sameSet(active.selectedKeys, selectedKeys);
    const expandedChanged = !sameSet(active.expandedHostIds, expandedHostIds);
    if (!identityChanged && !selectedChanged && !expandedChanged) return;
    const next = { userId, selectedKeys, expandedHostIds };
    setStored(next);
    if (selectedChanged) writeSet(storageKeys?.targets, selectedKeys);
    if (expandedChanged) writeSet(storageKeys?.expanded, expandedHostIds);
  }, [active, expandedHostIds, selectedKeys, storageKeys?.expanded, storageKeys?.targets, stored.userId, userId]);

  const updateSelected = useCallback((updater) => {
    setStored((previous) => {
      const base = previous.userId === userId ? previous : loaded;
      const nextSelected = updater(inventoryReady
        ? new Set([...base.selectedKeys].filter((key) => inventoryKeys.has(key)))
        : new Set(base.selectedKeys));
      writeSet(storageKeys?.targets, nextSelected);
      return { ...base, userId, selectedKeys: nextSelected };
    });
  }, [inventoryKeys, inventoryReady, loaded, storageKeys?.targets, userId]);
  const setTargetChecked = useCallback((key, checked) => {
    if (!inventoryKeys.has(key)) return;
    updateSelected((next) => {
      if (checked) next.add(key); else next.delete(key);
      return next;
    });
  }, [inventoryKeys, updateSelected]);

  const setHostChecked = useCallback((keysOrHostId, checked) => {
    let keys = keysOrHostId;
    if (typeof keysOrHostId === 'string' || typeof keysOrHostId === 'number') {
      keys = rconHosts.find((host) => String(host.id) === String(keysOrHostId))
        ?.instances.filter((instance) => instance.eligible).map((instance) => instance.key) ?? [];
    }
    updateSelected((next) => {
      for (const key of keys) {
        if (!eligibleKeys.has(key)) continue;
        if (checked) next.add(key); else next.delete(key);
      }
      return next;
    });
  }, [eligibleKeys, rconHosts, updateSelected]);
  const selectAllEligible = useCallback(() => {
    updateSelected((next) => new Set([...next, ...eligibleKeys]));
  }, [eligibleKeys, updateSelected]);

  const selectNone = useCallback(() => updateSelected(() => new Set()), [updateSelected]);

  const toggleHostExpanded = useCallback((hostId) => {
    if (!hostIds.has(hostId)) return;
    setStored((previous) => {
      const base = previous.userId === userId ? previous : loaded;
      const next = inventoryReady
        ? new Set([...base.expandedHostIds].filter((id) => hostIds.has(id)))
        : new Set(base.expandedHostIds);
      if (next.has(hostId)) next.delete(hostId); else next.add(hostId);
      writeSet(storageKeys?.expanded, next);
      return { ...base, userId, expandedHostIds: next };
    });
  }, [hostIds, inventoryReady, loaded, storageKeys?.expanded, userId]);

  const setAllHostsExpanded = useCallback((expanded) => {
    setStored((previous) => {
      const base = previous.userId === userId ? previous : loaded;
      const next = expanded ? new Set(hostIds) : new Set();
      writeSet(storageKeys?.expanded, next);
      return { ...base, userId, expandedHostIds: next };
    });
  }, [hostIds, loaded, storageKeys?.expanded, userId]);

  return {
    selectedKeys,
    expandedHostIds,
    // True only after both inventories loaded successfully; false preserves unverified persisted IDs.
    inventoryReady,
    setTargetChecked,
    setHostChecked,
    selectAllEligible,
    selectNone,
    toggleHostExpanded,
    setAllHostsExpanded,
  };
}

export default useGlobalRconPreferences;
