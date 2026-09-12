import { EditorState } from '@codemirror/state';
import { CompletionContext } from '@codemirror/autocomplete';
import { beforeEach, describe, expect, it } from 'vitest';

import { setCvarCatalog } from './codemirror-lang-qlcfg';
import { jsonContextAt, qlFactoriesCompletionSource } from './codemirror-lang-qlfactories';

const CATALOG = {
  sources: { factories: "the game's own factory definitions" },
  commands: [],
  gametypes: ['ca', 'ctf', 'duel', 'race'],
  cvars: [
    { name: 'g_startingWeapons', group: 'gameplay', description: 'Weapon bitmask.', source: 'factories', factory: true },
    { name: 'g_respawn_delay_min', group: 'gameplay', description: 'Lower bound.', source: 'factories', factory: true },
    { name: 'sv_hostname', group: 'server', description: 'Server name.', source: 'server.cfg' },
  ],
};

function complete(doc) {
  const state = EditorState.create({ doc });
  return qlFactoriesCompletionSource(new CompletionContext(state, doc.length, true));
}

beforeEach(() => {
  setCvarCatalog(CATALOG);
});

describe('jsonContextAt', () => {
  it('knows when the cursor sits inside a cvars block', () => {
    const doc = '[{"id":"x","cvars":{"g_';
    expect(jsonContextAt(doc, doc.length).objectKey).toBe('cvars');
  });

  it('knows when it is back at the factory level', () => {
    const doc = '[{"id":"x","cvars":{"g_gravity":"800"},"ba';
    expect(jsonContextAt(doc, doc.length).objectKey).toBe(null);
  });

  it('is not fooled by braces inside strings', () => {
    const doc = '[{"description":"{not a block}","ti';
    expect(jsonContextAt(doc, doc.length).objectKey).toBe(null);
  });
});

describe('qlFactoriesCompletionSource', () => {
  it('suggests cvar names inside the cvars block, the ones real factories use first', () => {
    const labels = complete('[{"id":"x","cvars":{"').options.map(o => o.label);
    expect(labels).toContain('g_startingWeapons');
    expect(labels.indexOf('g_startingWeapons')).toBeLessThan(labels.indexOf('sv_hostname'));
  });

  it('suggests factory keys at the factory level', () => {
    expect(complete('[{"ba').options.map(o => o.label)).toContain('basegt');
  });

  it('suggests base gametypes as the value of basegt', () => {
    const labels = complete('[{"basegt": "c').options.map(o => o.label);
    expect(labels).toEqual(expect.arrayContaining(['ca', 'ctf']));
  });

  it('replaces only the text inside the quotes', () => {
    const doc = '[{"cvars":{"g_re';
    expect(complete(doc).from).toBe(doc.lastIndexOf('"') + 1);
  });

  it('stays quiet outside a string', () => {
    expect(complete('[{"cvars":{')).toBe(null);
  });

  it('offers nothing for a value that is not a known enum', () => {
    expect(complete('[{"title": "My ')).toBe(null);
  });
});
