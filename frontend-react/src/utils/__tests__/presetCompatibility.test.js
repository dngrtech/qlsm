import { describe, expect, it } from 'vitest';
import {
  autoAcceptedPaths,
  combineAcceptedPaths,
  mergeReplacements,
  strippedWithReplacements,
} from '../presetCompatibility';

const presetData = {
  name: 'duel',
  scripts: { 'kept.py': 'ok' },
  checked_plugins: ['kept.py'],
  compatibility: {
    preset_runtime: 'minqlx',
    target_runtime: 'minqlxtended',
    stripped: [
      { path: 'myFun.py', verdict: 'incompatible', reasons: ['line 1: x'], replacement: 'myFun.py', originally_checked: true },
      { path: 'mybalance.py', verdict: 'incompatible', reasons: ['line 1: y'], replacement: null, originally_checked: false },
    ],
    replacements: { 'myFun.py': 'import minqlxtended\n', 'motd.py': 'import minqlxtended\n' },
    auto_accepted: ['motd.py'],
  },
};

describe('mergeReplacements', () => {
  it('merges an accepted replacement into scripts', () => {
    const merged = mergeReplacements(presetData, ['myFun.py']);
    expect(merged.scripts['myFun.py']).toBe('import minqlxtended\n');
  });

  it('ticks an accepted replacement the preset had enabled', () => {
    const merged = mergeReplacements(presetData, ['myFun.py']);
    expect(merged.checked_plugins).toContain('myFun.py');
  });

  it('does not enable an accepted replacement the preset had disabled', () => {
    // Accepting a replacement carries the FILE over; it does not switch the
    // plugin on. Enablement comes from the preset's own recorded selection.
    // Adding every accepted path to checked_plugins is what let a
    // cross-runtime load come up with plugins the preset never had enabled.
    const data = {
      ...presetData,
      compatibility: {
        ...presetData.compatibility,
        stripped: [
          { path: 'myFun.py', verdict: 'incompatible', reasons: ['line 1: x'], replacement: 'myFun.py', originally_checked: false },
        ],
      },
    };
    const merged = mergeReplacements(data, ['myFun.py']);
    expect(merged.scripts['myFun.py']).toBe('import minqlxtended\n');
    expect(merged.checked_plugins).toEqual(['kept.py']);
  });

  it('does not enable an auto-accepted replacement that is not in stripped', () => {
    // An auto-swapped plugin never reaches the dialog and keeps whatever tick
    // the backend already resolved for it in checked_plugins. Inferring
    // enablement from the accepted list here would re-enable the target
    // runtime's whole default catalog on every cross-runtime load.
    const merged = mergeReplacements(presetData, ['motd.py']);
    expect(merged.scripts['motd.py']).toBe('import minqlxtended\n');
    expect(merged.checked_plugins).toEqual(['kept.py']);
  });

  it('keeps a legacy preset\'s null selection null', () => {
    // null means "this preset pre-dates checked_plugins.json -- keep current
    // defaults", which applyPresetData branches on. Auto-accepted
    // replacements make the accepted list non-empty on virtually every
    // cross-runtime load, so returning [] here would hand every legacy preset
    // a deliberate-looking empty selection and load it with no plugins.
    const legacy = { ...presetData, checked_plugins: null };
    const merged = mergeReplacements(legacy, ['motd.py']);
    expect(merged.checked_plugins).toBeNull();
    expect(merged.scripts['motd.py']).toBe('import minqlxtended\n');
  });

  it('leaves scripts alone when nothing is accepted', () => {
    const merged = mergeReplacements(presetData, []);
    expect(Object.keys(merged.scripts)).toEqual(['kept.py']);
    expect(merged.checked_plugins).toEqual(['kept.py']);
  });

  it('ignores a path the backend never offered', () => {
    // Defends against a stale checkbox surviving a re-fetch. toBeUndefined()
    // alone can't tell "key absent" from "key present but undefined", so
    // assert on key presence and on checked_plugins directly -- the real
    // risk is a plugin file that doesn't exist on the instance getting
    // ticked as enabled.
    const merged = mergeReplacements(presetData, ['mybalance.py']);
    expect(Object.keys(merged.scripts)).toEqual(['kept.py']);
    expect('mybalance.py' in merged.scripts).toBe(false);
    expect(merged.checked_plugins).toEqual(['kept.py']);
  });

  it('does not duplicate a path already checked', () => {
    const data = { ...presetData, checked_plugins: ['kept.py', 'myFun.py'] };
    const merged = mergeReplacements(data, ['myFun.py']);
    expect(merged.checked_plugins.filter((p) => p === 'myFun.py')).toHaveLength(1);
  });

  it('does not mutate the input', () => {
    mergeReplacements(presetData, ['myFun.py']);
    expect(presetData.scripts['myFun.py']).toBeUndefined();
  });

  it('returns the input unchanged when there is no compatibility block', () => {
    const plain = { scripts: {}, checked_plugins: [] };
    expect(mergeReplacements(plain, ['anything.py'])).toBe(plain);
  });
});

describe('strippedWithReplacements', () => {
  it('lists only the entries a replacement exists for', () => {
    expect(strippedWithReplacements(presetData).map((e) => e.path)).toEqual(['myFun.py']);
  });

  it('is empty when there is no compatibility block', () => {
    expect(strippedWithReplacements({})).toEqual([]);
  });
});

describe('autoAcceptedPaths', () => {
  it('returns what the backend swapped without asking', () => {
    expect(autoAcceptedPaths(presetData)).toEqual(['motd.py']);
  });

  it('is empty when there is no compatibility block', () => {
    expect(autoAcceptedPaths({})).toEqual([]);
  });
});

describe('combineAcceptedPaths', () => {
  it('sends auto-accepted paths even when the operator ticked nothing', () => {
    // The no-dialog path calls this with no ticks at all. Dropping the
    // auto-accepted list there would leave _apply_runtime_filter deleting the
    // source files and writing nothing back.
    expect(combineAcceptedPaths(presetData)).toEqual(['motd.py']);
  });

  it('unions the operator\'s ticks with the automatic swaps', () => {
    expect(combineAcceptedPaths(presetData, ['myFun.py']).sort())
      .toEqual(['motd.py', 'myFun.py']);
  });

  it('does not duplicate a path present in both', () => {
    expect(combineAcceptedPaths(presetData, ['motd.py'])).toEqual(['motd.py']);
  });
});
