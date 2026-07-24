import { describe, expect, it } from 'vitest';

import { getExtension } from '../fileManagerUtils';

describe('getExtension', () => {
  it('returns the lowercased extension including the dot', () => {
    expect(getExtension('server.CFG')).toBe('.cfg');
    expect(getExtension('a/b/map.Ent')).toBe('.ent');
  });

  it('returns empty string when there is no dot', () => {
    expect(getExtension('README')).toBe('');
  });
});
