import { describe, it, expect } from 'vitest';
import { RUNTIME_OPTIONS, DEFAULT_RUNTIME, runtimeLabel } from '../runtimes';

describe('runtime constants', () => {
  it('defaults to minqlx', () => {
    expect(DEFAULT_RUNTIME).toBe('minqlx');
  });

  it('offers exactly the two runtimes, minqlx first', () => {
    expect(RUNTIME_OPTIONS.map(o => o.id)).toEqual(['minqlx', 'minqlxtended']);
  });

  it('labels every option and warns that the choice is permanent', () => {
    RUNTIME_OPTIONS.forEach(option => {
      expect(option.name).toBeTruthy();
      expect(option.description).toBeTruthy();
    });
  });

  it('falls back to minqlx for unknown or missing values', () => {
    expect(runtimeLabel('minqlxtended')).toBe('minqlxtended');
    expect(runtimeLabel(null)).toBe('minqlx');
    expect(runtimeLabel('garbage')).toBe('minqlx');
  });
});
