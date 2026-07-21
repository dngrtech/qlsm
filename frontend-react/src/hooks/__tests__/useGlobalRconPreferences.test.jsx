import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useGlobalRconPreferences } from '../useGlobalRconPreferences';

const auth = vi.hoisted(() => ({ user: { id: 7 } }));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ currentUser: auth.user }) }));

const hosts = [{ id: 1, name: 'One' }, { id: 2, name: 'Two' }];
const instances = [
  { id: 11, host_id: 1, name: 'A', status: 'running', zmq_rcon_port: 27960 },
  { id: 12, host_id: 1, name: 'B', status: 'stopped', zmq_rcon_port: 27961 },
  { id: 21, host_id: 2, name: 'C', status: 'updated', zmq_rcon_port: 27962 },
];
const targetKey = (user = 7) => `qlsm-global-rcon-targets-${user}`;
const expandedKey = (user = 7) => `qlsm-global-rcon-expanded-hosts-${user}`;

function renderPreferences(props = { hosts, instances, inventoryReady: true }) {
  return renderHook(({ value }) => useGlobalRconPreferences(value), { initialProps: { value: props } });
}

describe('useGlobalRconPreferences', () => {
  beforeEach(() => {
    auth.user = { id: 7 };
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('restores exact per-user keys synchronously and defaults to no targets', () => {
    localStorage.setItem(targetKey(), JSON.stringify(['1:11']));
    localStorage.setItem(expandedKey(), JSON.stringify([1]));
    const { result } = renderPreferences();
    expect(result.current.selectedKeys).toEqual(new Set(['1:11']));
    expect(result.current.expandedHostIds).toEqual(new Set([1]));

    localStorage.clear();
    const fresh = renderPreferences();
    expect(fresh.result.current.selectedKeys.size).toBe(0);
  });

  it('degrades safely for malformed JSON and storage exceptions', () => {
    localStorage.setItem(targetKey(), '{broken');
    expect(renderPreferences().result.current.selectedKeys.size).toBe(0);
    const getSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied'); });
    const { result } = renderPreferences();
    expect(result.current.expandedHostIds.size).toBe(0);
    getSpy.mockRestore();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('denied'); });
    act(() => result.current.setTargetChecked('1:11', true));
    expect(result.current.selectedKeys).toEqual(new Set(['1:11']));
  });

  it('prunes deleted targets/hosts but remembers temporarily ineligible selections', () => {
    localStorage.setItem(targetKey(), JSON.stringify(['1:11', '1:12', '9:99']));
    localStorage.setItem(expandedKey(), JSON.stringify([1, 9]));
    const { result } = renderPreferences();
    expect(result.current.selectedKeys).toEqual(new Set(['1:11', '1:12']));
    expect(result.current.expandedHostIds).toEqual(new Set([1]));
    expect(JSON.parse(localStorage.getItem(targetKey()))).toEqual(['1:11', '1:12']);
  });

  it('retains restored preferences without touching storage until inventory is ready', () => {
    localStorage.setItem(targetKey(), JSON.stringify(['1:11']));
    localStorage.setItem(expandedKey(), JSON.stringify([1]));
    const setSpy = vi.spyOn(Storage.prototype, 'setItem');
    const { result, rerender } = renderPreferences({ hosts: [], instances: [], inventoryReady: false });

    expect(result.current.inventoryReady).toBe(false);
    expect(result.current.selectedKeys).toEqual(new Set(['1:11']));
    expect(result.current.expandedHostIds).toEqual(new Set([1]));
    expect(setSpy).not.toHaveBeenCalled();

    rerender({ value: { hosts, instances, inventoryReady: true } });
    expect(result.current.inventoryReady).toBe(true);
    expect(result.current.selectedKeys).toEqual(new Set(['1:11']));
    expect(result.current.expandedHostIds).toEqual(new Set([1]));
    expect(setSpy).not.toHaveBeenCalled();
  });

  it('does not prune during prolonged error-like not-ready inventory', () => {
    localStorage.setItem(targetKey(), JSON.stringify(['1:11']));
    localStorage.setItem(expandedKey(), JSON.stringify([1]));
    const setSpy = vi.spyOn(Storage.prototype, 'setItem');
    const { result, rerender } = renderPreferences({ hosts: [], instances: [], inventoryReady: false });

    rerender({ value: { hosts: [], instances: [], inventoryReady: false } });
    expect(result.current.selectedKeys).toEqual(new Set(['1:11']));
    expect(result.current.expandedHostIds).toEqual(new Set([1]));
    expect(setSpy).not.toHaveBeenCalled();
  });

  it('prunes and persists restored preferences when a ready inventory is genuinely empty', () => {
    localStorage.setItem(targetKey(), JSON.stringify(['1:11']));
    localStorage.setItem(expandedKey(), JSON.stringify([1]));
    const setSpy = vi.spyOn(Storage.prototype, 'setItem');
    const { result, rerender } = renderPreferences({ hosts: [], instances: [], inventoryReady: false });

    rerender({ value: { hosts: [], instances: [], inventoryReady: true } });
    expect(result.current.selectedKeys).toEqual(new Set());
    expect(result.current.expandedHostIds).toEqual(new Set());
    expect(setSpy).toHaveBeenCalledTimes(2);
    expect(JSON.parse(localStorage.getItem(targetKey()))).toEqual([]);
    expect(JSON.parse(localStorage.getItem(expandedKey()))).toEqual([]);
  });

  it('persists immutable checkbox and expansion changes immediately while leaving new instances unchecked', () => {
    const { result, rerender } = renderPreferences();
    const initial = result.current.selectedKeys;
    act(() => result.current.setTargetChecked('1:11', true));
    expect(result.current.selectedKeys).not.toBe(initial);
    expect(JSON.parse(localStorage.getItem(targetKey()))).toEqual(['1:11']);
    act(() => result.current.toggleHostExpanded(2));
    expect(JSON.parse(localStorage.getItem(expandedKey()))).toEqual([2]);

    rerender({ value: { hosts, instances: [...instances, { id: 22, host_id: 2, status: 'running', zmq_rcon_port: 27963 }], inventoryReady: true } });
    expect(result.current.selectedKeys.has('2:22')).toBe(false);
  });

  it('supports eligible-only host/all operations and Select None clears unavailable memories', () => {
    const { result } = renderPreferences();
    act(() => result.current.setTargetChecked('1:12', true));
    act(() => result.current.setHostChecked(new Set(['1:11']), true));
    expect(result.current.selectedKeys).toEqual(new Set(['1:12', '1:11']));
    act(() => result.current.setHostChecked(new Set(['1:11']), false));
    expect(result.current.selectedKeys).toEqual(new Set(['1:12']));
    act(() => result.current.selectAllEligible());
    expect(result.current.selectedKeys).toEqual(new Set(['1:12', '1:11', '2:21']));
    act(() => result.current.selectNone());
    expect(result.current.selectedKeys.size).toBe(0);
  });

  it('reinitializes A to B without writing A state under B', () => {
    localStorage.setItem(targetKey(8), JSON.stringify(['2:21']));
    const { result, rerender } = renderPreferences();
    act(() => result.current.setTargetChecked('1:11', true));
    auth.user = { id: 8 };
    rerender({ value: { hosts, instances, inventoryReady: true } });
    expect(result.current.selectedKeys).toEqual(new Set(['2:21']));
    expect(JSON.parse(localStorage.getItem(targetKey(8)))).toEqual(['2:21']);
    expect(JSON.parse(localStorage.getItem(targetKey(7)))).toEqual(['1:11']);
  });

  it('changes users synchronously during loading without writing A preferences under B', () => {
    localStorage.setItem(targetKey(7), JSON.stringify(['1:11']));
    localStorage.setItem(targetKey(8), JSON.stringify(['2:21']));
    const setSpy = vi.spyOn(Storage.prototype, 'setItem');
    const { result, rerender } = renderPreferences({ hosts: [], instances: [], inventoryReady: false });

    auth.user = { id: 8 };
    rerender({ value: { hosts: [], instances: [], inventoryReady: false } });
    expect(result.current.selectedKeys).toEqual(new Set(['2:21']));
    expect(JSON.parse(localStorage.getItem(targetKey(7)))).toEqual(['1:11']);
    expect(JSON.parse(localStorage.getItem(targetKey(8)))).toEqual(['2:21']);
    expect(setSpy).not.toHaveBeenCalled();
  });
});
