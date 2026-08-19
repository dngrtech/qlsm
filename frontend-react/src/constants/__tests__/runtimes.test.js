import { describe, it, expect } from 'vitest';
import { RUNTIME_OPTIONS, DEFAULT_RUNTIME, defaultPresetNameForRuntime, runtimeLabel, runtimeLogFilename } from '../runtimes';

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

  it('maps each runtime to the live log filename it writes', () => {
    expect(runtimeLogFilename('minqlx')).toBe('minqlx.log');
    expect(runtimeLogFilename('minqlxtended')).toBe('minqlxtended.log');
  });

  it('falls back to the minqlx log filename for unknown or missing runtimes', () => {
    expect(runtimeLogFilename(null)).toBe('minqlx.log');
    expect(runtimeLogFilename('garbage')).toBe('minqlx.log');
  });
});

describe('defaultPresetNameForRuntime', () => {
  it('returns the minqlx builtin preset for minqlx', () => {
    expect(defaultPresetNameForRuntime('minqlx')).toBe('default');
  });

  it('returns the minqlxtended builtin preset for minqlxtended', () => {
    expect(defaultPresetNameForRuntime('minqlxtended')).toBe('default-minqlxtended');
  });

  it('falls back to the minqlx preset for null, unknown or missing values', () => {
    // A host row that predates the runtime column reads null, and nothing but
    // minqlx has ever existed. Mirrors normalize_runtime() in ui/runtime.py.
    expect(defaultPresetNameForRuntime(null)).toBe('default');
    expect(defaultPresetNameForRuntime(undefined)).toBe('default');
    expect(defaultPresetNameForRuntime('nonsense')).toBe('default');
  });
});
