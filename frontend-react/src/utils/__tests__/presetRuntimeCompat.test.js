import { describe, it, expect } from 'vitest';
import {
  isPresetRuntimeCompatible,
  presetRuntimeMismatchMessage,
} from '../presetRuntimeCompat';

describe('preset runtime compatibility', () => {
  it('accepts a matching runtime', () => {
    expect(isPresetRuntimeCompatible({ runtime: 'minqlx' }, { runtime: 'minqlx' })).toBe(true);
    expect(isPresetRuntimeCompatible({ runtime: 'minqlxtended' }, { runtime: 'minqlxtended' })).toBe(true);
  });

  it('rejects a mismatched runtime in both directions', () => {
    expect(isPresetRuntimeCompatible({ runtime: 'minqlx' }, { runtime: 'minqlxtended' })).toBe(false);
    expect(isPresetRuntimeCompatible({ runtime: 'minqlxtended' }, { runtime: 'minqlx' })).toBe(false);
  });

  it('treats a missing runtime as minqlx on both sides', () => {
    expect(isPresetRuntimeCompatible({}, {})).toBe(true);
    expect(isPresetRuntimeCompatible({}, { runtime: 'minqlx' })).toBe(true);
    expect(isPresetRuntimeCompatible({}, { runtime: 'minqlxtended' })).toBe(false);
  });

  it('does not block when the host is not yet known', () => {
    // The Add Instance form renders before a host is chosen; blocking every
    // preset at that point would be a worse lie than showing them all.
    expect(isPresetRuntimeCompatible({ runtime: 'minqlx' }, null)).toBe(true);
    expect(isPresetRuntimeCompatible({ runtime: 'minqlx' }, undefined)).toBe(true);
  });

  it('names both runtimes in the mismatch message', () => {
    const message = presetRuntimeMismatchMessage(
      { runtime: 'minqlx' },
      { runtime: 'minqlxtended' },
    );
    expect(message).toMatch(/minqlx/);
    expect(message).toMatch(/minqlxtended/);
  });

  it('returns an empty message when compatible', () => {
    expect(presetRuntimeMismatchMessage({ runtime: 'minqlx' }, { runtime: 'minqlx' })).toBe('');
  });
});
