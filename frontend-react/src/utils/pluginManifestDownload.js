// Builds and triggers the browser download for a locally-edited
// qlsm-repository.json draft. Mirrors utils/presetDownload.js's
// createObjectURL/anchor-click mechanics.

// The current manifest format, and the first file fetch_manifest() tries. The
// older plugins-only qlsm-plugins.json is only read when this one is absent,
// so an export under the old name next to an existing qlsm-repository.json
// would never be read at all.
export const DEFAULT_MANIFEST_FILENAME = 'qlsm-repository.json';

const stripRowKey = (entry) => {
  const copy = { ...entry };
  delete copy._key;
  return copy;
};

/**
 * A plugin ready to write into the manifest: empty optional fields and empty
 * cvars/commands lists are left out entirely rather than written as '' or [],
 * matching the shape real repository manifests already use.
 */
export function cleanPluginForExport(p) {
  const out = { filename: p.filename || '' };
  if (p.label) out.label = p.label;
  if (p.description) out.description = p.description;
  if (p.runtime) out.runtime = p.runtime;
  if (p.requires_qlsm_version) out.requires_qlsm_version = p.requires_qlsm_version;
  // Not editable here, but carried through from the loaded file (see
  // pluginManifestDraft.js PLUGIN_PASSTHROUGH_FIELDS).
  if (p.version) out.version = p.version;
  if (p.sha256) out.sha256 = p.sha256;
  if (Array.isArray(p.depends_on) && p.depends_on.length) out.depends_on = p.depends_on;
  if (p.package_files && typeof p.package_files === 'object' && Object.keys(p.package_files).length) {
    out.package_files = p.package_files;
  }
  // `_key` is the editor's own row id (utils/pluginManifestDraft.js) and
  // must never reach the exported file.
  if (Array.isArray(p.cvars) && p.cvars.length) out.cvars = p.cvars.map(stripRowKey);
  if (Array.isArray(p.commands) && p.commands.length) out.commands = p.commands.map(stripRowKey);
  return out;
}

const ADDON_OPTIONAL_FIELDS = ['version', 'sha256', 'label', 'description', 'requires_qlsm_version'];

/**
 * An addon ready to write into the manifest's `addons` list. `id` and `zip`
 * are always written (they are the two fields qlsm requires); blank optional
 * fields are left out, like cleanPluginForExport does.
 */
export function cleanAddonForExport(a) {
  const out = { id: a.id || '', zip: a.zip || '' };
  ADDON_OPTIONAL_FIELDS.forEach((field) => {
    if (a[field]) out[field] = a[field];
  });
  return out;
}

/**
 * A safe qlsm-repository.json-style filename: falls back when blank, and always
 * ends in .json.
 *
 * The operator types this into the export box, so it is stripped to the same
 * character set as utils/presetDownload.js's safePresetDownloadName rather
 * than trusting the browser to make sense of a value like "../x".
 */
export function safeManifestFilename(name) {
  const base = String(name || '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^A-Za-z0-9._-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[.-]+|[.-]+$/g, '');
  if (!base) return DEFAULT_MANIFEST_FILENAME;
  return /\.json$/i.test(base) ? base : `${base}.json`;
}

/**
 * `addons` is written only when there are any, so a plugins-only repository
 * still exports the same `{"plugins": [...]}` shape it always had.
 */
export function manifestJsonBody(plugins, addons = []) {
  const body = { plugins: (plugins || []).map(cleanPluginForExport) };
  if (Array.isArray(addons) && addons.length) body.addons = addons.map(cleanAddonForExport);
  return JSON.stringify(body, null, 2);
}

export function triggerManifestDownload(filename, plugins, addons = []) {
  const blob = new Blob([manifestJsonBody(plugins, addons)], { type: 'application/json' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = safeManifestFilename(filename);
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}
