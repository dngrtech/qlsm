import { describe, expect, it } from 'vitest';
import { validateManifestPlugins, issueCounts } from '../pluginManifestValidation';

describe('validateManifestPlugins', () => {
  it('finds no issues for a well-formed plugin', () => {
    const issues = validateManifestPlugins([{
      filename: 'afkplus.py',
      label: 'AFK Plus',
      description: 'Moves AFK players to spectator.',
      runtime: 'minqlx',
      requires_qlsm_version: '1.36.0',
      cvars: [{ cvar: 'qlx_afk_warning_seconds', label: 'Warning after', type: 'number', default: 10, min: 1, description: 'Seconds.' }],
      commands: [{ name: 'akv', description: 'Show version.' }],
    }]);
    expect(issues).toEqual([]);
  });

  it('errors on a filename qlsm would silently drop', () => {
    const issues = validateManifestPlugins([{ filename: 'not a module name.py' }]);
    expect(issues).toEqual(expect.arrayContaining([
      expect.objectContaining({ severity: 'error', index: 0 }),
    ]));
  });

  it('errors on missing filename', () => {
    const issues = validateManifestPlugins([{ label: 'No filename' }]);
    expect(issueCounts(issues).errors).toBeGreaterThan(0);
  });

  it('errors on duplicate filenames', () => {
    const issues = validateManifestPlugins([
      { filename: 'afkplus.py', label: 'A' },
      { filename: 'afkplus.py', label: 'B' },
    ]);
    expect(issues.some((i) => i.severity === 'error' && /appears 2 times/.test(i.message))).toBe(true);
  });

  it('errors when cvars/commands is present but not a list', () => {
    const issues = validateManifestPlugins([{ filename: 'x.py', cvars: 'oops' }]);
    expect(issues.some((i) => i.severity === 'error' && /"cvars" must be a list/.test(i.message))).toBe(true);
  });

  it('warns, but does not error, on a missing label/description', () => {
    const issues = validateManifestPlugins([{ filename: 'x.py' }]);
    expect(issueCounts(issues).errors).toBe(0);
    expect(issueCounts(issues).warnings).toBeGreaterThan(0);
  });

  it('warns on a non-dotted-integer version string', () => {
    const issues = validateManifestPlugins([{ filename: 'x.py', requires_qlsm_version: 'v1.36-beta' }]);
    expect(issues.some((i) => i.severity === 'warning' && /isn't a dotted version number/.test(i.message))).toBe(true);
  });

  it('accepts a version string with any number of dotted integers', () => {
    const issues = validateManifestPlugins([{ filename: 'x.py', requires_qlsm_version: '1.36' }]);
    expect(issues.some((i) => /dotted version number/.test(i.message))).toBe(false);
  });

  it('warns when a cvar default type does not match its declared type', () => {
    const issues = validateManifestPlugins([{
      filename: 'x.py',
      cvars: [{ cvar: 'qlx_x', label: 'X', type: 'number', default: 'ten', description: 'd' }],
    }]);
    expect(issues.some((i) => i.severity === 'warning' && /default should be a number/.test(i.message))).toBe(true);
  });

  it('warns on an out-of-range command permission', () => {
    const issues = validateManifestPlugins([{
      filename: 'x.py',
      commands: [{ name: 'cmd', description: 'd', permission: 9 }],
    }]);
    expect(issues.some((i) => /"permission" should be an integer 0-5/.test(i.message))).toBe(true);
  });
});

describe('issueCounts', () => {
  it('splits errors and warnings', () => {
    expect(issueCounts([
      { severity: 'error', message: 'a' },
      { severity: 'warning', message: 'b' },
      { severity: 'warning', message: 'c' },
    ])).toEqual({ errors: 1, warnings: 2 });
  });
});
