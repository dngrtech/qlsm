import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useRankData } from '../useRankData';
import * as api from '../../services/api';

vi.mock('../../services/api');

describe('useRankData', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(api.getInstanceRanks).mockReset();
    vi.mocked(api.getInstanceRanks).mockResolvedValue({ ranks: {}, configured: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('does not fetch when disabled', () => {
    // LiveServerStatusModal is mounted UNCONDITIONALLY in two places
    // (ServersPage.jsx:401, InstanceDetailsModal.jsx:528) with visibility
    // controlled only by isOpen. Without this guard the hook runs while the
    // drawer is closed, and twice when the details modal sits behind it.
    renderHook(() => useRankData(1, ['76561198000000001'], { enabled: false }));
    expect(api.getInstanceRanks).not.toHaveBeenCalled();
  });

  it('fetches once when enabled', async () => {
    renderHook(() => useRankData(1, ['76561198000000001'], { enabled: true }));
    await waitFor(() => expect(api.getInstanceRanks).toHaveBeenCalledTimes(1));
    expect(api.getInstanceRanks).toHaveBeenCalledWith(1, '76561198000000001');
  });

  it('does not refetch when the array identity changes but contents do not', async () => {
    // sortedPlayers is a useMemo over serverStatus.players, which
    // useServerStatus replaces every 15s. An array in the dependency list
    // re-fires the effect on every parent render and the 30s throttle — which
    // the entire caching design rests on — quietly evaporates.
    const { rerender } = renderHook(
      ({ ids }) => useRankData(1, ids, { enabled: true }),
      { initialProps: { ids: ['76561198000000001', '76561198000000002'] } },
    );
    await waitFor(() => expect(api.getInstanceRanks).toHaveBeenCalledTimes(1));
    rerender({ ids: ['76561198000000002', '76561198000000001'] });
    await act(async () => {});
    expect(api.getInstanceRanks).toHaveBeenCalledTimes(1);
  });

  it('refetches when a player actually joins', async () => {
    const { rerender } = renderHook(
      ({ ids }) => useRankData(1, ids, { enabled: true }),
      { initialProps: { ids: ['76561198000000001'] } },
    );
    await waitFor(() => expect(api.getInstanceRanks).toHaveBeenCalledTimes(1));
    rerender({ ids: ['76561198000000001', '76561198000000003'] });
    await waitFor(() => expect(api.getInstanceRanks).toHaveBeenCalledTimes(2));
  });

  it('polls every 30 seconds', async () => {
    renderHook(() => useRankData(1, ['76561198000000001'], { enabled: true }));
    await waitFor(() => expect(api.getInstanceRanks).toHaveBeenCalledTimes(1));
    await act(async () => { vi.advanceTimersByTime(30000); });
    await waitFor(() => expect(api.getInstanceRanks).toHaveBeenCalledTimes(2));
  });

  it('stops polling once the server reports configured false', async () => {
    vi.mocked(api.getInstanceRanks).mockResolvedValue({ ranks: {}, configured: false });
    const { result } = renderHook(
      () => useRankData(1, ['76561198000000001'], { enabled: true }));
    await waitFor(() => expect(result.current.configured).toBe(false));
    await act(async () => { vi.advanceTimersByTime(90000); });
    // One request for the life of the drawer, not one every 30s.
    expect(api.getInstanceRanks).toHaveBeenCalledTimes(1);
  });

  it('does not re-arm the stop latch when the roster changes', async () => {
    // configured:false is a property of the INSTANCE, not of who happens to be
    // connected. Keying the latch reset on steamIdsKey turns the stated "one
    // request" into one request per join or leave, which on a populated server
    // is frequent. Effects run in declaration order, so the reset would land
    // before the fetch effect re-subscribes and the new request would go out.
    vi.mocked(api.getInstanceRanks).mockResolvedValue({ ranks: {}, configured: false });
    const { result, rerender } = renderHook(
      ({ ids }) => useRankData(1, ids, { enabled: true }),
      { initialProps: { ids: ['76561198000000001'] } },
    );
    await waitFor(() => expect(result.current.configured).toBe(false));
    rerender({ ids: ['76561198000000001', '76561198000000003'] });
    await act(async () => { vi.advanceTimersByTime(30000); });
    expect(api.getInstanceRanks).toHaveBeenCalledTimes(1);
  });

  it('reports configured false on the first render, before any response', async () => {
    // The spec's rule is "hidden entirely, not shown full of dashes". The modal
    // renders before the first /ranks response resolves, so an initial `true`
    // shows a header and a column of dashes on every instance that has no
    // provider — which is every instance on day one — then removes them.
    const { result } = renderHook(
      () => useRankData(1, ['76561198000000001'], { enabled: true }));
    expect(result.current.configured).toBe(false);
    await act(async () => {});
  });

  it('clears ranks and configured when the instance changes', async () => {
    // One LiveServerStatusModal is mounted per page (ServersPage.jsx:401) and
    // the instance prop is swapped. Without a reset, instance A's column and
    // numbers survive into instance B's first render, and a player on both
    // servers carries A's rating into B's table — a WRONG number rather than a
    // missing one, and the one failure here an operator cannot spot by looking.
    vi.mocked(api.getInstanceRanks).mockResolvedValue({
      ranks: { '76561198000000001': { display: '1650' } }, configured: true,
    });
    const { result, rerender } = renderHook(
      ({ id }) => useRankData(id, ['76561198000000001'], { enabled: true }),
      { initialProps: { id: 1 } },
    );
    await waitFor(() => expect(result.current.configured).toBe(true));
    vi.mocked(api.getInstanceRanks).mockImplementation(() => new Promise(() => {}));  // never resolves
    rerender({ id: 2 });
    expect(result.current.ranks).toEqual({});
    expect(result.current.configured).toBe(false);
  });

  it('returns empty data on every render of a new instance while its request is pending', async () => {
    vi.mocked(api.getInstanceRanks).mockResolvedValueOnce({
      ranks: { '76561198000000001': { display: '1650' } }, configured: true,
    }).mockImplementation(() => new Promise(() => {}));
    const renders = [];
    const { result, rerender } = renderHook(
      ({ id }) => {
        const data = useRankData(id, ['76561198000000001'], { enabled: true });
        renders.push({ id, ...data });
        return data;
      },
      { initialProps: { id: 1 } },
    );
    await waitFor(() => expect(result.current.configured).toBe(true));
    expect(result.current.ranks['76561198000000001'].display).toBe('1650');

    rerender({ id: 2 });

    expect(api.getInstanceRanks).toHaveBeenLastCalledWith(2, '76561198000000001');
    const nextInstanceRenders = renders.filter(({ id }) => id === 2);
    expect(nextInstanceRenders.length).toBeGreaterThan(0);
    for (const data of nextInstanceRenders) {
      expect(data.ranks).toEqual({});
      expect(data.configured).toBe(false);
    }
  });

  it('treats a 404 as unconfigured and stops polling', async () => {
    // get_ranks 404s on an instance deleted while its drawer is open. Without
    // this the catch would keep polling a dead instance every 30s for the life
    // of the drawer.
    const notFound = Object.assign(new Error('not found'), {
      response: { status: 404 },
    });
    vi.mocked(api.getInstanceRanks).mockRejectedValue(notFound);
    const { result } = renderHook(
      () => useRankData(1, ['76561198000000001'], { enabled: true }));
    await waitFor(() => expect(api.getInstanceRanks).toHaveBeenCalledTimes(1));
    await act(async () => { vi.advanceTimersByTime(90000); });
    expect(api.getInstanceRanks).toHaveBeenCalledTimes(1);
    expect(result.current.configured).toBe(false);
  });

  it('keeps the last good ranks and configured when a poll fails', async () => {
    vi.mocked(api.getInstanceRanks).mockReset()
      .mockResolvedValueOnce({ ranks: { a: { display: '1650' } }, configured: true })
      .mockRejectedValueOnce(new Error('down'));
    const { result } = renderHook(
      () => useRankData(1, ['76561198000000001'], { enabled: true }));
    await waitFor(() => expect(result.current.ranks.a.display).toBe('1650'));
    await act(async () => { vi.advanceTimersByTime(30000); });
    expect(result.current.ranks.a.display).toBe('1650');
    // The catch leaves configured ALONE. Forcing it true here would render a
    // provider column on an instance that may have none.
    expect(result.current.configured).toBe(true);
  });

  it('does not fetch with an empty roster', () => {
    renderHook(() => useRankData(1, [], { enabled: true }));
    expect(api.getInstanceRanks).not.toHaveBeenCalled();
  });
});
