import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const refreshHosts = vi.fn();
let instancesState;

vi.mock('../useHosts', () => ({
  POLLABLE_HOST_STATUSES: [],
  useHosts: () => ({
    sortedHosts: [{ id: 1, name: 'h1', status: 'active' }],
    loading: false,
    error: null,
    refreshHosts,
  }),
}));

vi.mock('../useInstances', () => ({
  POLLABLE_INSTANCE_STATUSES: [],
  useInstances: () => instancesState,
}));

vi.mock('../useExpandState', () => ({
  useExpandState: () => ({
    expandedIds: new Set(),
    initExpanded: () => {},
    toggleExpand: () => {},
    expandAll: () => {},
    collapseAll: () => {},
  }),
}));

import { useServers } from '../useServers';

function instances(status) {
  return { instances: [{ id: 7, host_id: 1, status }], loading: false, error: null, refreshInstances: vi.fn() };
}

describe('useServers', () => {
  beforeEach(() => {
    refreshHosts.mockClear();
  });

  it('does not refetch hosts on the first instance load', () => {
    instancesState = instances('deploying');
    renderHook(() => useServers());
    expect(refreshHosts).not.toHaveBeenCalled();
  });

  it('refetches hosts when an instance status changes, so host eligibility stays fresh', () => {
    instancesState = instances('deploying');
    const { rerender } = renderHook(() => useServers());
    instancesState = instances('running');
    rerender();
    expect(refreshHosts).toHaveBeenCalledTimes(1);
    expect(refreshHosts).toHaveBeenCalledWith(false);
  });

  it('does not refetch hosts when instance statuses are unchanged', () => {
    instancesState = instances('running');
    const { rerender } = renderHook(() => useServers());
    instancesState = instances('running');
    rerender();
    expect(refreshHosts).not.toHaveBeenCalled();
  });
});
