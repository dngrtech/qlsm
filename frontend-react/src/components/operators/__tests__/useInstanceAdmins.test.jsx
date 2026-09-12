import { useState } from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { expect, it, vi, beforeEach } from 'vitest';
import useInstanceAdmins from '../useInstanceAdmins';

const getInstanceAdmins = vi.fn();
vi.mock('../../../services/api', () => ({
  getInstanceAdmins: (...args) => getInstanceAdmins(...args),
}));

beforeEach(() => getInstanceAdmins.mockReset());

// The parent owns the list, so every test renders the hook the way the real
// callers do: entries in state, onChange writing it back.
function renderAdmins(props = {}) {
  const onChange = vi.fn();
  const view = renderHook(
    ({ entries }) => useInstanceAdmins({ instanceId: 1, active: true, entries, onChange, ...props }),
    { initialProps: { entries: null } },
  );
  const rerenderWith = (entries) => view.rerender({ entries });
  onChange.mockImplementation((next) => rerenderWith(next));
  return { ...view, onChange, rerenderWith };
}

it('marks a stored row matching the server as managed', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }],
    live: { '76561198012345678': 3 },
    managed: ['76561198012345678'],
    live_error: null,
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  expect(result.current.rows[0]).toMatchObject({ steamId: '76561198012345678', level: 3, state: 'managed' });
});

it('marks a stored row the server does not have as pending', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }],
    live: {}, managed: [], live_error: null,
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(result.current.rows[0].state).toBe('pending'));
});

it('marks a level only the server has as live-only', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [], live: { '76561198087654321': 5 }, managed: [], live_error: null,
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(result.current.rows[0]).toMatchObject({
    steamId: '76561198087654321', level: 5, state: 'live-only',
  }));
});

it('marks a managed SteamID with no stored row as will-be-revoked', async () => {
  // QLSM pushed this level once and lost the row -- the next save resets it to 0,
  // so it must not be labelled "set in-game, left alone".
  getInstanceAdmins.mockResolvedValue({
    stored: [], live: { '76561198087654321': 5 },
    managed: ['76561198087654321'], live_error: null,
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(result.current.rows[0].state).toBe('will-be-revoked'));
});

it('labels every row unknown when the live read failed', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }],
    live: null, managed: null,
    live_error: 'The server is unreachable, so in-game levels could not be read.',
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(result.current.liveError).toMatch(/unreachable/));
  expect(result.current.rows).toHaveLength(1);
  expect(result.current.rows[0].state).toBe('unknown');
});

it('ignores a live key at level 0', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [], live: { '76561198087654321': 0 }, managed: [], live_error: null,
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(getInstanceAdmins).toHaveBeenCalled());
  expect(result.current.rows).toEqual([]);
});

it('lets a stored level-0 row settle as managed', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 0 }],
    live: { '76561198012345678': 0 }, managed: ['76561198012345678'], live_error: null,
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(result.current.rows[0].state).toBe('managed'));
});

it('reports nothing upward until a mutator runs', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }],
    live: {}, managed: [], live_error: null,
  });
  const { result, onChange } = renderAdmins();
  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  expect(onChange).not.toHaveBeenCalled();
  expect(result.current.dirty).toBe(false);
});

it('adopting a live-only row makes it pending and dirty', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [], live: { '76561198087654321': 5 }, managed: [], live_error: null,
  });
  const { result, onChange } = renderAdmins();
  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  act(() => result.current.adoptAdmin('76561198087654321'));
  expect(onChange).toHaveBeenCalledWith([{ steam_id64: '76561198087654321', level: 5 }]);
  expect(result.current.rows[0].state).toBe('pending');
  expect(result.current.dirty).toBe(true);
});

it('removing a row drops it from the entries', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }], live: {}, managed: [], live_error: null,
  });
  const { result, onChange } = renderAdmins();
  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  act(() => result.current.removeAdmin('76561198012345678'));
  expect(onChange).toHaveBeenCalledWith([]);
  expect(result.current.rows).toHaveLength(0);
});

it('refresh keeps unsaved edits', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }], live: {}, managed: [], live_error: null,
  });
  const { result } = renderAdmins();
  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  act(() => result.current.removeAdmin('76561198012345678'));
  await act(async () => { await result.current.refresh(); });
  expect(result.current.rows).toHaveLength(0);
  expect(result.current.dirty).toBe(true);
});

it('reports the loaded stored list through onLoaded without marking it dirty', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }], live: {}, managed: [], live_error: null,
  });
  const onLoaded = vi.fn();
  const { result } = renderHook(() => useInstanceAdmins({
    instanceId: 1, active: true, entries: null, onChange: () => {}, onLoaded,
  }));
  await waitFor(() => expect(onLoaded).toHaveBeenCalledWith(
    [{ steam_id64: '76561198012345678', level: 3 }],
  ));
  expect(result.current.dirty).toBe(false);
});

it('fetches once even when onLoaded is an inline callback recreated every render', async () => {
  getInstanceAdmins.mockResolvedValue({
    stored: [{ steam_id64: '76561198012345678', level: 3 }], live: {}, managed: [], live_error: null,
  });
  // A real caller closes over parent state, so onLoaded is a fresh function
  // identity on every render -- exactly like the onChange harness above, this
  // wires the parent's setState back into a rerender to prove the fetch effect
  // does not key off that identity.
  function Wrapper() {
    const [presetSource, setPresetSource] = useState(null);
    const hook = useInstanceAdmins({
      instanceId: 1,
      active: true,
      entries: null,
      onChange: () => {},
      onLoaded: (loaded) => setPresetSource(loaded),
    });
    return { ...hook, presetSource };
  }
  const { result } = renderHook(() => Wrapper());
  await waitFor(() => expect(result.current.presetSource).toEqual(
    [{ steam_id64: '76561198012345678', level: 3 }],
  ));
  expect(getInstanceAdmins).toHaveBeenCalledTimes(1);
});

it('does not read live state when inactive', async () => {
  const { result } = renderHook(() => useInstanceAdmins({
    instanceId: null,
    active: false,
    entries: [{ steam_id64: '76561198012345678', level: 2 }],
    onChange: () => {},
  }));
  expect(getInstanceAdmins).not.toHaveBeenCalled();
  expect(result.current.rows).toEqual([
    { steamId: '76561198012345678', level: 2, state: 'unknown' },
  ]);
});
