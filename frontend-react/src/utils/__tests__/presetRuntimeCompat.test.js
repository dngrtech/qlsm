import { describe, it, expect } from 'vitest';
import {
  presetRuntimeMatches,
  presetRuntimeStripWarning,
} from '../presetRuntimeCompat';

describe('preset runtime compatibility', () => {
  it('accepts a matching runtime', () => {
    expect(presetRuntimeMatches({ runtime: 'minqlx' }, { runtime: 'minqlx' })).toBe(true);
    expect(presetRuntimeMatches({ runtime: 'minqlxtended' }, { runtime: 'minqlxtended' })).toBe(true);
  });

  it('rejects a mismatched runtime in both directions', () => {
    expect(presetRuntimeMatches({ runtime: 'minqlx' }, { runtime: 'minqlxtended' })).toBe(false);
    expect(presetRuntimeMatches({ runtime: 'minqlxtended' }, { runtime: 'minqlx' })).toBe(false);
  });

  it('treats a missing runtime as minqlx on both sides', () => {
    expect(presetRuntimeMatches({}, {})).toBe(true);
    expect(presetRuntimeMatches({}, { runtime: 'minqlx' })).toBe(true);
    expect(presetRuntimeMatches({}, { runtime: 'minqlxtended' })).toBe(false);
  });

  it('does not block when the host is not yet known', () => {
    // The Add Instance form renders before a host is chosen; blocking every
    // preset at that point would be a worse lie than showing them all.
    expect(presetRuntimeMatches({ runtime: 'minqlx' }, null)).toBe(true);
    expect(presetRuntimeMatches({ runtime: 'minqlx' }, undefined)).toBe(true);
  });

  it('names both runtimes in the strip warning', () => {
    const message = presetRuntimeStripWarning(
      { runtime: 'minqlx' },
      { runtime: 'minqlxtended' },
    );
    expect(message).toMatch(/minqlx/);
    expect(message).toMatch(/minqlxtended/);
  });

  it('returns an empty message when compatible', () => {
    expect(presetRuntimeStripWarning({ runtime: 'minqlx' }, { runtime: 'minqlx' })).toBe('');
  });
});
