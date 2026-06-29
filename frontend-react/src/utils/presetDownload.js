import { downloadPreset } from '../services/api';

/**
 * Return a filesystem/browser-safe base filename for a preset download.
 * Mirrors the backend `_safe_export_filename` rules.
 */
export function safePresetDownloadName(name) {
  const safeName = String(name || '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^A-Za-z0-9._-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[.-]+|[.-]+$/g, '');
  return safeName || 'preset';
}

/**
 * Fetch a preset's export archive and trigger a browser download.
 * Throws on failure so the caller can surface the server message.
 */
export async function triggerPresetDownload(preset) {
  if (!preset?.id) return;

  const blob = await downloadPreset(preset.id);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${safePresetDownloadName(preset.name)}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}
