import { describe, expect, it } from 'vitest';
import {
  validateManifestPlugins, validateManifestAddons, isAcceptedAddonZip, issueCounts,
} from '../pluginManifestValidation';

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
    const dupes = issues.filter((i) => i.severity === 'error' && /appears 2 times/.test(i.message));
    // One per offending row, each carrying its index, so the editor can mark
    // both rows instead of reporting a finding that belongs to no row.
    expect(dupes.map((i) => i.index)).toEqual([0, 1]);
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

const SHA = 'a'.repeat(64);
const goodAddon = {
  id: 'my-addon',
  zip: 'addons/my-addon.zip',
  version: '1.2.0',
  sha256: SHA,
  label: 'My Addon',
  description: 'Does a thing.',
  requires_qlsm_version: '1.40.0',
};

describe('validateManifestAddons', () => {
  it('finds no issues for a well-formed addon', () => {
    expect(validateManifestAddons([goodAddon])).toEqual([]);
  });

  it('tags every issue as an addon issue with its row index', () => {
    const issues = validateManifestAddons([goodAddon, { id: '', zip: '' }]);
    expect(issues.length).toBeGreaterThan(0);
    issues.forEach((i) => {
      expect(i.kind).toBe('addon');
      expect(i.index).toBe(1);
    });
  });

  it.each([
    ['missing', undefined],
    ['empty', ''],
    ['uppercase', 'My-Addon'],
    ['double dash', 'my--addon'],
    ['leading dash', '-addon'],
    ['underscore', 'my_addon'],
    ['padded', ' my-addon'],
    ['too long', 'a'.repeat(65)],
  ])('errors on an id qlsm would drop (%s)', (_name, id) => {
    const issues = validateManifestAddons([{ ...goodAddon, id }]);
    expect(issues.some((i) => i.severity === 'error' && /id must be kebab-case/.test(i.message))).toBe(true);
  });

  it('accepts an id of exactly 64 characters', () => {
    expect(validateManifestAddons([{ ...goodAddon, id: 'a'.repeat(64) }])).toEqual([]);
  });

  it('errors on a zip qlsm would drop', () => {
    const issues = validateManifestAddons([{ ...goodAddon, zip: '../my-addon.zip' }]);
    expect(issues.some((i) => i.severity === 'error' && /zip must be a relative path/.test(i.message))).toBe(true);
  });

  it('errors on duplicate ids, once per row', () => {
    const issues = validateManifestAddons([goodAddon, { ...goodAddon, zip: 'other.zip' }]);
    const dupes = issues.filter((i) => i.severity === 'error' && /appears 2 times/.test(i.message));
    expect(dupes.map((i) => i.index)).toEqual([0, 1]);
  });

  it('errors on a sha256 qlsm would discard, but accepts one it normalizes', () => {
    const bad = validateManifestAddons([{ ...goodAddon, sha256: 'abc123' }]);
    expect(bad.some((i) => i.severity === 'error' && /sha256 must be 64 hex/.test(i.message))).toBe(true);
    // _optional_sha256() strips and lowercases before matching.
    expect(validateManifestAddons([{ ...goodAddon, sha256: ` ${'A'.repeat(64)} ` }])).toEqual([]);
  });

  it('only warns when the optional fields are missing', () => {
    const issues = validateManifestAddons([{ id: 'my-addon', zip: 'my-addon.zip' }]);
    expect(issueCounts(issues).errors).toBe(0);
    const messages = issues.map((i) => i.message).join('\n');
    expect(messages).toMatch(/no sha256 set/);
    expect(messages).toMatch(/no version set/);
    expect(messages).toMatch(/no label set/);
    expect(messages).toMatch(/no description set/);
  });

  it('treats a whitespace-only optional field as unset', () => {
    const issues = validateManifestAddons([{ ...goodAddon, label: '   ' }]);
    expect(issues.some((i) => /no label set/.test(i.message))).toBe(true);
  });

  it('warns on a non-dotted-integer requires_qlsm_version', () => {
    const issues = validateManifestAddons([{ ...goodAddon, requires_qlsm_version: 'v1.40' }]);
    expect(issues).toEqual([expect.objectContaining({ severity: 'warning', message: expect.stringMatching(/isn't a dotted version number/) })]);
  });
});

describe('isAcceptedAddonZip', () => {
  // Same cases ui/plugin_repositories.py _zip_path() accepts and rejects.
  it.each([
    'my-addon.zip',
    'addons/my-addon.zip',
    'MY-ADDON.ZIP',
    '  addons/my-addon.zip  ',
    'addons\\my-addon.zip',
    'addons//my-addon.zip',
  ])('accepts %j', (zip) => {
    expect(isAcceptedAddonZip(zip)).toBe(true);
  });

  it.each([
    undefined,
    '',
    '   ',
    'my-addon.tar.gz',
    '/abs/my-addon.zip',
    '\\abs\\my-addon.zip',
    '../my-addon.zip',
    'addons/./my-addon.zip',
    'C:/my-addon.zip',
  ])('rejects %j', (zip) => {
    expect(isAcceptedAddonZip(zip)).toBe(false);
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
