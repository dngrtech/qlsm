import { useEffect, useMemo, useRef, useState } from 'react';
import { getInstanceRanks } from '../services/api';

const POLL_INTERVAL_MS = 30000;

/**
 * Ratings for the currently connected players, on its own cadence.
 *
 * Independent of the 15s live-status poll on purpose: an outbound call to a
 * third-party service must never ride on every Live Status refresh. 30s against
 * the backend's 60s cache TTL keeps poll >= TTL/2, so a cache hit is the common
 * case.
 *
 * @param {number|null} instanceId
 * @param {string[]} steamIds - connected players' steam ids
 * @param {{enabled: boolean}} options - enabled is REQUIRED, not an
 *   optimization: LiveServerStatusModal is mounted unconditionally in two
 *   places and visibility is controlled only by its isOpen prop.
 */
export function useRankData(instanceId, steamIds, { enabled = true } = {}) {
  const [ranks, setRanks] = useState({});
  // Starts FALSE. The modal renders before the first /ranks response resolves,
  // so an initial `true` shows the header and a column of dashes on every
  // instance that has no provider — which is every instance on day one — and
  // then removes them a moment later. That is exactly the flash the spec's
  // "hidden entirely, not shown full of dashes" rule exists to prevent. The
  // cost is one render without a column before a configured instance's first
  // response, which is the correct direction to be wrong in.
  const [configured, setConfigured] = useState(false);
  const stopPollingRef = useRef(false);

  // A stable primitive, not the array. sortedPlayers is a useMemo over
  // serverStatus.players, which useServerStatus replaces on a 15s interval — an
  // array here re-fires the effect on every parent render and the throttle
  // this whole design rests on quietly evaporates.
  const steamIdsKey = useMemo(
    () => [...new Set((steamIds || []).map(String))].sort().join(','),
    [steamIds],
  );

  // Keyed on instanceId ALONE — never on steamIdsKey. `configured: false` is a
  // property of the instance, not of who happens to be connected, so clearing
  // the latch on a join or leave turns "one request for the life of the drawer"
  // into one request per roster change. The cost is that a provider configured
  // while the drawer is open is not picked up until it is reopened, which is
  // the right behaviour for a config change.
  //
  // The same effect resets the DATA. Without it, instance A's column and
  // numbers survive into instance B's first render, and a player on both
  // servers carries A's rating into B's table.
  useEffect(() => {
    stopPollingRef.current = false;
    setRanks({});
    setConfigured(false);
  }, [instanceId]);

  useEffect(() => {
    if (!enabled || !instanceId || !steamIdsKey) {
      return undefined;
    }

    let cancelled = false;

    const fetchOnce = async () => {
      if (stopPollingRef.current) return;
      try {
        const result = await getInstanceRanks(instanceId, steamIdsKey);
        if (cancelled) return;
        setRanks(result.ranks);
        setConfigured(result.configured);
        if (!result.configured) {
          // An instance that will never have a provider costs one request,
          // not one every 30s for the life of the drawer.
          stopPollingRef.current = true;
        }
      } catch (error) {
        if (cancelled) return;
        if (error?.response?.status === 404) {
          // The instance was deleted while its drawer is open. Stop, rather
          // than polling a dead instance every 30s for the life of the drawer.
          setConfigured(false);
          stopPollingRef.current = true;
          return;
        }
        // Keep the last good data: a failed poll means no fresh ranks, not a
        // reason to blank a table the operator is reading. `configured` is
        // deliberately left UNTOUCHED — forcing it true here would render a
        // provider column on an instance that may have none.
      }
    };

    fetchOnce();
    const timer = setInterval(fetchOnce, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [instanceId, steamIdsKey, enabled]);

  return { ranks, configured };
}
