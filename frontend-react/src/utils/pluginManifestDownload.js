// Builds and triggers the browser download for a locally-edited
// qlsm-plugins.json draft. Mirrors utils/presetDownload.js's
// createObjectURL/anchor-click mechanics.

/**
 * A plugin ready to write into qlsm-plugins.json: empty optional fields and
 * empty cvars/commands lists are left out entirely rather than written as ''
 * or [], matching the shape real qlsm-plugins.json files already use.
 */
export function cleanPluginForExport(p) {
  const out = { filename: p.filename || '' };
  if (p.label) out.label = p.label;
  if (p.description) out.description = p.description;
  if (p.runtime) out.runtime = p.runtime;
  if (p.requires_qlsm_version) out.requires_qlsm_version = p.requires_qlsm_version;
  if (Array.isArray(p.cvars) && p.cvars.length) out.cvars = p.cvars;
  if (Array.isArray(p.commands) && p.commands.length) out.commands = p.commands;
  return out;
}

/** A safe qlsm-plugins.json-style filename: falls back when blank, always ends in .json. */
export function safeManifestFilename(name) {
  const trimmed = String(name || '').trim();
  const base = trimmed || 'qlsm-plugins.json';
  return /\.json$/i.test(base) ? base : `${base}.json`;
}

export function manifestJsonBody(plugins) {
  return JSON.stringify({ plugins: (plugins || []).map(cleanPluginForExport) }, null, 2);
}

export function triggerManifestDownload(filename, plugins) {
  const blob = new Blob([manifestJsonBody(plugins)], { type: 'application/json' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = safeManifestFilename(filename);
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}
