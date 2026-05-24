import { describe, expect, it, vi } from 'vitest';
import {
  compareVersions,
  fetchLatestVersionInfo,
  isNewerVersion,
  normalizeVersion,
  parseVersionManifest,
} from '../versioning';

describe('versioning', () => {
  it('normalizes version strings', () => {
    expect(normalizeVersion(' v1.8.5 ')).toBe('1.8.5');
    expect(normalizeVersion('V2.0.0')).toBe('2.0.0');
    expect(normalizeVersion(null)).toBe('');
  });

  it('compares semantic version numbers with optional v prefixes', () => {
    expect(compareVersions('v1.8.6', '1.8.5')).toBe(1);
    expect(compareVersions('1.8.5', '1.8.6')).toBe(-1);
    expect(compareVersions('1.8', '1.8.0')).toBe(0);
  });

  it('detects newer versions', () => {
    expect(isNewerVersion('1.9.0', '1.8.5')).toBe(true);
    expect(isNewerVersion('1.8.5', '1.8.5')).toBe(false);
  });

  it('parses a valid latest-version manifest', () => {
    expect(parseVersionManifest({
      latest: 'v1.9.0',
      releaseNotesUrl: 'https://example.test/releases',
    })).toEqual({
      latest: '1.9.0',
      releaseNotesUrl: 'https://example.test/releases',
    });
  });

  it('rejects invalid latest-version manifests', () => {
    expect(parseVersionManifest({ latest: '' })).toBeNull();
    expect(parseVersionManifest(null)).toBeNull();
  });

  it('loads latest-version info from a manifest endpoint', async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        latest: '1.9.0',
        releaseNotesUrl: '/docs/releases',
      }),
    }));

    await expect(fetchLatestVersionInfo({ fetchImpl, manifestUrl: '/version.json' })).resolves.toEqual({
      latest: '1.9.0',
      releaseNotesUrl: '/docs/releases',
    });
    expect(fetchImpl).toHaveBeenCalledWith('/version.json', { cache: 'no-store' });
  });
});
