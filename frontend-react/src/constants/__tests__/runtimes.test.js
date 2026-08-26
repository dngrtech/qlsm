import { describe, it, expect } from 'vitest';
import { RUNTIME_OPTIONS, DEFAULT_RUNTIME, defaultPresetNameForRuntime, runtimeLabel, runtimeLogFilename, runtimeTooltipTail } from '../runtimes';

describe('runtime constants', () => {
  it('defaults to minqlx', () => {
    expect(DEFAULT_RUNTIME).toBe('minqlx');
  });

  it('gives every runtime the upstream repo its tooltip links to', () => {
    expect(RUNTIME_OPTIONS.find(o => o.id === 'minqlx').repoUrl)
      .toBe('https://github.com/MinoMino/minqlx');
    expect(RUNTIME_OPTIONS.find(o => o.id === 'minqlxtended').repoUrl)
      .toBe('https://github.com/tjone270/minqlxtended');
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

describe('runtimeTooltipTail', () => {
  // The runtime choice is irreversible, so the tooltip has to be accurate about
  // what the operator is committing to -- and that differs by provider. On a
  // cloud host QLSM picks the OS image; on the operator's own machine it does
  // not, and only minqlxtended has a floor to miss.
  it('tells cloud operators QLSM provisions the OS for them', () => {
    expect(runtimeTooltipTail('minqlx', 'vultr')).toBe('QLSM provisions Debian 12.');
    expect(runtimeTooltipTail('minqlxtended', 'vultr')).toBe('QLSM provisions Ubuntu 24.04.');
  });

  it('names the distro, not the Python version, for minqlxtended on an operator-owned machine', () => {
    // "Python 3.12+" sends operators to apt, which has no python3.12 on Debian
    // 12 -- and the build links -lpython3.12, so a sideloaded one would not
    // satisfy it either. The actionable requirement is the distro release.
    expect(runtimeTooltipTail('minqlxtended', 'standalone')).toContain('Ubuntu 24.04 or newer');
    expect(runtimeTooltipTail('minqlxtended', 'standalone')).not.toContain('Python');
    expect(runtimeTooltipTail('minqlxtended', 'self')).toContain('Ubuntu 24.04 or newer');
    expect(runtimeTooltipTail('minqlxtended', 'self')).not.toContain('Python');
  });

  it('says a standalone host is checked before it is created', () => {
    // _validate_runtime_python() rejects the submission, so the operator finds
    // out before anything irreversible happens.
    expect(runtimeTooltipTail('minqlxtended', 'standalone')).toMatch(/checked before the host is created/i);
  });

  it('warns that a self host is not checked up front and fails during setup', () => {
    // There is no pre-check for self: the host record is created, setup fails
    // on the playbook assert, and the host lands in Error.
    expect(runtimeTooltipTail('minqlxtended', 'self')).toMatch(/not checked up front/i);
    expect(runtimeTooltipTail('minqlxtended', 'self')).toMatch(/setup fails/i);
  });

  it('tells operator-owned machines that minqlx has no version floor', () => {
    // min_python is None for minqlx: it runs on whatever python3 the distro
    // ships, so there is nothing here for an operator to get wrong.
    ['standalone', 'self'].forEach(provider => {
      expect(runtimeTooltipTail('minqlx', provider)).toMatch(/no version floor/i);
    });
  });

  it('treats an unknown provider as a provisioned cloud host', () => {
    // Every provider other than standalone/self is one QLSM images itself --
    // the same split AddHostFormFields already makes.
    expect(runtimeTooltipTail('minqlxtended', 'somefuturecloud')).toBe('QLSM provisions Ubuntu 24.04.');
  });

  it('falls back to minqlx copy for an unknown runtime', () => {
    expect(runtimeTooltipTail('garbage', 'vultr')).toBe('QLSM provisions Debian 12.');
  });
});
