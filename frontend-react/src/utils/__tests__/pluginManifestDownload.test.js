import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanAddonForExport, cleanPluginForExport, manifestJsonBody, safeManifestFilename, triggerManifestDownload,
} from '../pluginManifestDownload';
import { blankAddon, buildAddonDraft, buildManifestDraft } from '../pluginManifestDraft';

describe('cleanPluginForExport', () => {
  it('keeps only filename when everything else is blank', () => {
    expect(cleanPluginForExport({ filename: 'x.py', label: '', description: '', runtime: '', requires_qlsm_version: '', cvars: [], commands: [] }))
      .toEqual({ filename: 'x.py' });
  });

  it('strips the editor\'s internal _key from cvars and commands', () => {
    const cleaned = cleanPluginForExport({
      _key: 'plugin-0',
      filename: 'x.py',
      cvars: [{ _key: 'cvar-1', cvar: 'qlx_x', label: 'X' }],
      commands: [{ _key: 'command-2', name: 'x' }],
    });
    expect(cleaned).toEqual({
      filename: 'x.py',
      cvars: [{ cvar: 'qlx_x', label: 'X' }],
      commands: [{ name: 'x' }],
    });
    expect(JSON.stringify(cleaned)).not.toContain('_key');
  });

  it('includes populated fields and non-empty cvars/commands', () => {
    const plugin = {
      filename: 'x.py',
      label: 'X',
      description: 'desc',
      runtime: 'minqlx',
      requires_qlsm_version: '1.36.0',
      cvars: [{ cvar: 'qlx_x', label: 'X', type: 'string', default: '', description: 'd' }],
      commands: [{ name: 'x', description: 'd' }],
    };
    expect(cleanPluginForExport(plugin)).toEqual(plugin);
  });
});

describe('cleanAddonForExport', () => {
  it('keeps id and zip, and leaves blank optional fields out', () => {
    expect(cleanAddonForExport(blankAddon())).toEqual({ id: '', zip: '' });
    expect(cleanAddonForExport({ ...blankAddon(), id: 'my-addon', zip: 'my-addon.zip', version: '1.0.0' }))
      .toEqual({ id: 'my-addon', zip: 'my-addon.zip', version: '1.0.0' });
  });

  it('never writes the editor\'s internal _key', () => {
    expect(JSON.stringify(cleanAddonForExport(blankAddon()))).not.toContain('_key');
  });
});

describe('safeManifestFilename', () => {
  it('falls back to qlsm-repository.json when blank', () => {
    expect(safeManifestFilename('')).toBe('qlsm-repository.json');
    expect(safeManifestFilename('   ')).toBe('qlsm-repository.json');
  });

  it('appends .json when missing', () => {
    expect(safeManifestFilename('my-plugins')).toBe('my-plugins.json');
  });

  it('leaves an existing .json extension alone', () => {
    expect(safeManifestFilename('my-plugins.json')).toBe('my-plugins.json');
  });

  it('strips path separators and other unsafe characters', () => {
    expect(safeManifestFilename('../../etc/passwd')).toBe('etc-passwd.json');
    expect(safeManifestFilename('my plugins!.json')).toBe('my-plugins-.json');
  });

  it('falls back when nothing safe is left', () => {
    expect(safeManifestFilename('///')).toBe('qlsm-repository.json');
  });
});

describe('manifestJsonBody', () => {
  it('wraps the cleaned plugins in a {plugins: [...]} object', () => {
    const body = manifestJsonBody([{ filename: 'x.py', label: '', description: '', runtime: '', requires_qlsm_version: '', cvars: [], commands: [] }]);
    expect(JSON.parse(body)).toEqual({ plugins: [{ filename: 'x.py' }] });
  });
});

describe('manifestJsonBody with addons', () => {
  it('adds an addons list only when there are addons', () => {
    expect(JSON.parse(manifestJsonBody([], []))).toEqual({ plugins: [] });
    const body = JSON.parse(manifestJsonBody([], [{ ...blankAddon(), id: 'a', zip: 'a.zip' }]));
    expect(body).toEqual({ plugins: [], addons: [{ id: 'a', zip: 'a.zip' }] });
  });
});

// What the editor loads is fetch_manifest() output (repo.plugins / repo.addons),
// so loading it and exporting straight away must give back what the
// repository's file said, minus the nulls/empties qlsm fills in for unset fields.
describe('draft round trip', () => {
  it('writes back plugin fields the editor has no inputs for', () => {
    const repoPlugins = [{
      filename: 'match_restore.py',
      label: 'Match Restore',
      description: null,
      runtime: 'minqlx',
      version: '2.1.0',
      sha256: 'b'.repeat(64),
      requires_qlsm_version: null,
      depends_on: ['chat_rcon_acl.py'],
      package_files: { 'restore/__init__.py': 'c'.repeat(64) },
      version_risk: { level: 'none' },
    }, {
      filename: 'plain.py', label: null, description: null, runtime: null, version: null,
      sha256: null, requires_qlsm_version: null, depends_on: [], package_files: {},
    }];
    expect(JSON.parse(manifestJsonBody(buildManifestDraft(repoPlugins))).plugins).toEqual([{
      filename: 'match_restore.py',
      label: 'Match Restore',
      runtime: 'minqlx',
      version: '2.1.0',
      sha256: 'b'.repeat(64),
      depends_on: ['chat_rcon_acl.py'],
      package_files: { 'restore/__init__.py': 'c'.repeat(64) },
    }, { filename: 'plain.py' }]);
  });

  it('writes back every addon field', () => {
    const repoAddons = [{
      id: 'my-addon', zip: 'my-addon.zip', label: 'My Addon', description: 'd', version: '1.2.0',
      sha256: 'd'.repeat(64), requires_qlsm_version: '1.40.0', version_risk: { level: 'none' },
    }, {
      id: 'bare', zip: 'bare.zip', label: null, description: null, version: null, sha256: null, requires_qlsm_version: null,
    }];
    expect(JSON.parse(manifestJsonBody([], buildAddonDraft(repoAddons))).addons).toEqual([{
      id: 'my-addon', zip: 'my-addon.zip', version: '1.2.0', sha256: 'd'.repeat(64),
      label: 'My Addon', description: 'd', requires_qlsm_version: '1.40.0',
    }, { id: 'bare', zip: 'bare.zip' }]);
  });
});

describe('triggerManifestDownload', () => {
  beforeEach(() => {
    window.URL.createObjectURL = vi.fn(() => 'blob:manifest');
    window.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    delete window.URL.createObjectURL;
    delete window.URL.revokeObjectURL;
  });

  it('downloads the cleaned manifest under the given filename', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    triggerManifestDownload('my-plugins', [{ filename: 'x.py', label: '', description: '', runtime: '', requires_qlsm_version: '', cvars: [], commands: [] }]);

    expect(clickSpy).toHaveBeenCalledTimes(1);
    const anchor = clickSpy.mock.instances[0];
    expect(anchor.download).toBe('my-plugins.json');
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:manifest');

    clickSpy.mockRestore();
  });
});
