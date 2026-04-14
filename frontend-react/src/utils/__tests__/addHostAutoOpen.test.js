import { beforeEach, describe, expect, it } from 'vitest';

import {
  armAutoOpenAddHost,
  clearAutoOpenAddHost,
  shouldAutoOpenAddHost,
} from '../addHostAutoOpen';

describe('addHostAutoOpen', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('prefers route state when present', () => {
    expect(shouldAutoOpenAddHost({ openAddHost: true })).toBe(true);
  });

  it('reads and clears the session marker', () => {
    armAutoOpenAddHost();
    expect(shouldAutoOpenAddHost(null)).toBe(true);

    clearAutoOpenAddHost();
    expect(shouldAutoOpenAddHost(null)).toBe(false);
  });
});
