import { describe, expect, it } from 'vitest';
import { mergeReplacements, strippedWithReplacements } from '../presetCompatibility';

const presetData = {
  name: 'duel',
  scripts: { 'kept.py': 'ok' },
  checked_plugins: ['kept.py'],
  compatibility: {
    preset_runtime: 'minqlx',
    target_runtime: 'minqlxtended',
    stripped: [
      { path: 'myFun.py', verdict: 'incompatible', reasons: ['line 1: x'], replacement: 'myFun.py' },
      { path: 'mybalance.py', verdict: 'incompatible', reasons: ['line 1: y'], replacement: null },
    ],
    replacements: { 'myFun.py': 'import minqlxtended\n' },
  },
};

describe('mergeReplacements', () => {
  it('merges an accepted replacement into scripts', () => {
    const merged = mergeReplacements(presetData, ['myFun.py']);
    expect(merged.scripts['myFun.py']).toBe('import minqlxtended\n');
  });

  it('ticks the accepted replacement in checked_plugins', () => {
    const merged = mergeReplacements(presetData, ['myFun.py']);
    expect(merged.checked_plugins).toContain('myFun.py');
  });

  it('leaves scripts alone when nothing is accepted', () => {
    const merged = mergeReplacements(presetData, []);
    expect(Object.keys(merged.scripts)).toEqual(['kept.py']);
    expect(merged.checked_plugins).toEqual(['kept.py']);
  });

  it('ignores a path the backend never offered', () => {
    // Defends against a stale checkbox surviving a re-fetch.
    const merged = mergeReplacements(presetData, ['mybalance.py']);
    expect(merged.scripts['mybalance.py']).toBeUndefined();
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
