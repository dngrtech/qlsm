import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanPluginForExport, manifestJsonBody, safeManifestFilename, triggerManifestDownload } from '../pluginManifestDownload';

describe('cleanPluginForExport', () => {
  it('keeps only filename when everything else is blank', () => {
    expect(cleanPluginForExport({ filename: 'x.py', label: '', description: '', runtime: '', requires_qlsm_version: '', cvars: [], commands: [] }))
      .toEqual({ filename: 'x.py' });
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

describe('safeManifestFilename', () => {
  it('falls back to qlsm-plugins.json when blank', () => {
    expect(safeManifestFilename('')).toBe('qlsm-plugins.json');
    expect(safeManifestFilename('   ')).toBe('qlsm-plugins.json');
  });

  it('appends .json when missing', () => {
    expect(safeManifestFilename('my-plugins')).toBe('my-plugins.json');
  });

  it('leaves an existing .json extension alone', () => {
    expect(safeManifestFilename('my-plugins.json')).toBe('my-plugins.json');
  });
});

describe('manifestJsonBody', () => {
  it('wraps the cleaned plugins in a {plugins: [...]} object', () => {
    const body = manifestJsonBody([{ filename: 'x.py', label: '', description: '', runtime: '', requires_qlsm_version: '', cvars: [], commands: [] }]);
    expect(JSON.parse(body)).toEqual({ plugins: [{ filename: 'x.py' }] });
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
