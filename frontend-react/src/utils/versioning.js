export const CURRENT_VERSION = import.meta.env.VITE_QLSM_VERSION || '0.0.0';

export const DEFAULT_RELEASE_NOTES_URL = 'https://dngrtech.github.io/qlsm/releases/';
export const DEFAULT_VERSION_MANIFEST_URL =
  import.meta.env.VITE_QLSM_VERSION_MANIFEST_URL || 'https://raw.githubusercontent.com/dngrtech/qlsm/main/docs/user/version.json';

export function normalizeVersion(version) {
  if (typeof version !== 'string') {
    return '';
  }

  return version.trim().replace(/^v/i, '');
}

export function compareVersions(left, right) {
  const leftParts = normalizeVersion(left).split('.').map((part) => Number.parseInt(part, 10));
  const rightParts = normalizeVersion(right).split('.').map((part) => Number.parseInt(part, 10));

  for (let index = 0; index < 3; index += 1) {
    const leftValue = Number.isFinite(leftParts[index]) ? leftParts[index] : 0;
    const rightValue = Number.isFinite(rightParts[index]) ? rightParts[index] : 0;

    if (leftValue > rightValue) return 1;
    if (leftValue < rightValue) return -1;
  }

  return 0;
}

export function isNewerVersion(candidate, current = CURRENT_VERSION) {
  return compareVersions(candidate, current) > 0;
}

export function parseVersionManifest(manifest) {
  if (!manifest || typeof manifest !== 'object') {
    return null;
  }

  const latest = typeof manifest.latest === 'string' ? normalizeVersion(manifest.latest) : '';
  if (!latest) {
    return null;
  }

  const releaseNotesUrl =
    typeof manifest.releaseNotesUrl === 'string' && manifest.releaseNotesUrl.trim()
      ? manifest.releaseNotesUrl.trim()
      : DEFAULT_RELEASE_NOTES_URL;

  return {
    latest,
    releaseNotesUrl,
  };
}

export async function fetchLatestVersionInfo({
  fetchImpl = fetch,
  manifestUrl = DEFAULT_VERSION_MANIFEST_URL,
} = {}) {
  const response = await fetchImpl(manifestUrl, { cache: 'no-cache' });
  if (!response.ok) {
    throw new Error(`Version manifest request failed (${response.status})`);
  }

  const manifest = await response.json();
  const parsed = parseVersionManifest(manifest);
  if (!parsed) {
    throw new Error('Version manifest format is invalid');
  }

  return parsed;
}
