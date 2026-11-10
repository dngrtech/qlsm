// Checks a client-side draft of a repository manifest's plugin list against what the two real consumers actually do with it:
//   - ui/plugin_repositories.py fetch_manifest() (Sync/browse): silently
//     DROPS an entry whose filename fails FILENAME_RE, and drops the whole
//     `cvars`/`commands` field on an entry where it isn't a list. Those are
//     the only two ways an edit here can make plugin data disappear, so
//     they are the only `error`-level findings.
//   - the cvars/commands become a plugin's `.ql-plugin.json` pool sidecar on
//     download (build_inline_manifest) and are rendered by
//     PluginCvarsModal.jsx: nothing there is enforced server-side (plugin_
//     manifest.py calls this metadata "purely optional display/edit
//     enrichment"), so a rough edge just renders oddly rather than breaking
//     anything -- those are `warning`-level.
// The addon list has its own checks, validateManifestAddons() below.
//
// Mirrors ui/plugin_repositories.py's `_FILENAME_RE` exactly.
const FILENAME_RE = /^[A-Za-z0-9_-]+\.py$/;
// Mirrors PluginCvarsModal.jsx's three branches (bool / number / else-string).
export const KNOWN_CVAR_TYPES = ['string', 'number', 'bool'];
// Mirrors ui/plugin_repositories.py's _parse_dotted_version(): any number of
// dot-separated integers, not necessarily three.
const DOTTED_VERSION_RE = /^\d+(\.\d+)*$/;
// Mirrors ui/addons/manifest.py's ADDON_ID_RE / ADDON_ID_MAX, which
// ui/plugin_repositories.py _normalize_addons() applies to a repository's
// addon `id` (unstripped, like the backend).
const ADDON_ID_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const ADDON_ID_MAX = 64;
// Mirrors ui/plugin_repositories.py's _SHA256_RE, applied after the same
// strip + lowercase _optional_sha256() does.
const SHA256_RE = /^[0-9a-f]{64}$/;

function expectedDefaultType(cvarType) {
  if (cvarType === 'number') return 'number';
  if (cvarType === 'bool') return 'boolean';
  if (cvarType === 'string') return 'string';
  return null;
}

/**
 * @param {Array<object>} plugins - draft plugin entries (qlsm-plugins.json shape)
 * @returns {Array<{severity: 'error'|'warning', index?: number, message: string}>}
 */
export function validateManifestPlugins(plugins) {
  const issues = [];
  if (!Array.isArray(plugins)) return issues;

  // filename -> the row indexes using it, so a duplicate can be reported
  // against each row that has it rather than as a finding belonging to no
  // row at all (which the editor can't draw a marker for).
  const filenameRows = new Map();

  plugins.forEach((p, i) => {
    const label = p?.filename ? `#${i + 1} (${p.filename})` : `#${i + 1}`;

    if (!p?.filename || !FILENAME_RE.test(p.filename)) {
      issues.push({
        severity: 'error',
        index: i,
        message: `Plugin ${label}: filename must be a bare "name.py" (letters, digits, "_" and "-" only) — anything else is silently dropped when qlsm fetches this file.`,
      });
    } else {
      filenameRows.set(p.filename, [...(filenameRows.get(p.filename) || []), i]);
    }

    if (!p?.label) {
      issues.push({ severity: 'warning', index: i, message: `Plugin ${label}: no label set — qlsm shows the filename instead.` });
    }
    if (!p?.description) {
      issues.push({ severity: 'warning', index: i, message: `Plugin ${label}: no description set.` });
    }
    if (p?.requires_qlsm_version && !DOTTED_VERSION_RE.test(p.requires_qlsm_version)) {
      issues.push({
        severity: 'warning',
        index: i,
        message: `Plugin ${label}: "${p.requires_qlsm_version}" isn't a dotted version number (e.g. "1.36.0") — qlsm can't compare it, so the version check is silently skipped.`,
      });
    }

    ['cvars', 'commands'].forEach((field) => {
      if (p?.[field] !== undefined && !Array.isArray(p[field])) {
        issues.push({
          severity: 'error',
          index: i,
          message: `Plugin ${label}: "${field}" must be a list — qlsm drops this field entirely otherwise.`,
        });
      }
    });

    (Array.isArray(p?.cvars) ? p.cvars : []).forEach((c, j) => {
      const cvarLabel = `${label} → cvar ${j + 1}${c?.cvar ? ` (${c.cvar})` : ''}`;
      if (!c?.cvar) issues.push({ severity: 'warning', index: i, message: `${cvarLabel}: no "cvar" name set.` });
      if (!c?.label) issues.push({ severity: 'warning', index: i, message: `${cvarLabel}: no "label" set.` });
      if (c?.type && !KNOWN_CVAR_TYPES.includes(c.type)) {
        issues.push({
          severity: 'warning',
          index: i,
          message: `${cvarLabel}: type "${c.type}" isn't one qlsm's settings form recognizes (string, number, bool) — it renders as plain text.`,
        });
      }
      const expected = expectedDefaultType(c?.type);
      if (expected && c?.default !== undefined && typeof c.default !== expected) {
        issues.push({
          severity: 'warning',
          index: i,
          message: `${cvarLabel}: default should be a ${expected} to match type "${c.type}".`,
        });
      }
      if (c?.type !== 'number' && (c?.min !== undefined || c?.max !== undefined)) {
        issues.push({ severity: 'warning', index: i, message: `${cvarLabel}: "min"/"max" only apply when type is "number".` });
      }
    });

    (Array.isArray(p?.commands) ? p.commands : []).forEach((c, j) => {
      const cmdLabel = `${label} → command ${j + 1}${c?.name ? ` (${c.name})` : ''}`;
      if (!c?.name) issues.push({ severity: 'warning', index: i, message: `${cmdLabel}: no "name" set.` });
      if (c?.permission !== undefined) {
        const perm = c.permission;
        if (!Number.isInteger(perm) || perm < 0 || perm > 5) {
          issues.push({ severity: 'warning', index: i, message: `${cmdLabel}: "permission" should be an integer 0-5.` });
        }
      }
    });
  });

  filenameRows.forEach((rows, filename) => {
    if (rows.length > 1) {
      rows.forEach((i) => {
        issues.push({
          severity: 'error',
          index: i,
          message: `Plugin #${i + 1} (${filename}): "${filename}" appears ${rows.length} times — duplicate filenames collide in qlsm's plugin list.`,
        });
      });
    }
  });

  return issues;
}

// Mirrors ui/plugin_repositories.py's _zip_path(): true when the backend
// keeps the entry's `zip`, false when it returns None and drops the entry.
export function isAcceptedAddonZip(value) {
  if (typeof value !== 'string' || !value.trim()) return false;
  const path = value.trim().replace(/\\/g, '/');
  if (path.startsWith('/') || !path.toLowerCase().endsWith('.zip')) return false;
  const parts = path.split('/').filter(Boolean);
  return !parts.some((part) => part === '.' || part === '..' || part.includes(':'));
}

// _optional_str(): a whitespace-only value counts as unset.
const isBlank = (value) => typeof value !== 'string' || !value.trim();

/**
 * Checks a draft of the manifest's `addons` list against what
 * ui/plugin_repositories.py does with it. Same severity rule as the plugin
 * checks: `error` only where the next sync loses data -- an entry
 * _normalize_addons() drops (bad id, bad zip), a second entry with an id
 * already used (the install route and the repository card both look addons
 * up by id, so only the first can ever be installed), and a `sha256` that
 * _optional_sha256() discards, which also means the .zip is installed
 * without its hash check. Everything else is `warning`.
 *
 * Every issue carries `kind: 'addon'` so the editor can tell an addon row's
 * index apart from a plugin row's.
 *
 * @param {Array<object>} addons - draft addon entries
 * @returns {Array<{severity: 'error'|'warning', kind: 'addon', index: number, message: string}>}
 */
export function validateManifestAddons(addons) {
  const issues = [];
  if (!Array.isArray(addons)) return issues;

  const push = (severity, index, message) => issues.push({ severity, kind: 'addon', index, message });
  const idRows = new Map();

  addons.forEach((a, i) => {
    const label = a?.id ? `#${i + 1} (${a.id})` : `#${i + 1}`;
    const id = a?.id;

    if (typeof id !== 'string' || id.length > ADDON_ID_MAX || !ADDON_ID_RE.test(id)) {
      push('error', i, `Addon ${label}: id must be kebab-case (lowercase letters, digits, single dashes), at most ${ADDON_ID_MAX} characters — anything else is silently dropped when qlsm fetches this file.`);
    } else {
      idRows.set(id, [...(idRows.get(id) || []), i]);
    }

    if (!isAcceptedAddonZip(a?.zip)) {
      push('error', i, `Addon ${label}: zip must be a relative path to a .zip file (no leading "/", no "." or ".." parts, no ":") — the entry is silently dropped otherwise.`);
    }

    if (isBlank(a?.sha256)) {
      push('warning', i, `Addon ${label}: no sha256 set — qlsm installs the .zip without checking it.`);
    } else if (!SHA256_RE.test(a.sha256.trim().toLowerCase())) {
      push('error', i, `Addon ${label}: sha256 must be 64 hex characters — qlsm discards it otherwise, and installs the .zip without checking it.`);
    }

    if (isBlank(a?.version)) {
      push('warning', i, `Addon ${label}: no version set — qlsm can't tell whether the installed copy is up to date.`);
    }
    if (isBlank(a?.label)) {
      push('warning', i, `Addon ${label}: no label set — qlsm shows the id instead.`);
    }
    if (isBlank(a?.description)) {
      push('warning', i, `Addon ${label}: no description set.`);
    }
    if (!isBlank(a?.requires_qlsm_version) && !DOTTED_VERSION_RE.test(a.requires_qlsm_version)) {
      push('warning', i, `Addon ${label}: "${a.requires_qlsm_version}" isn't a dotted version number (e.g. "1.36.0") — qlsm can't compare it, so the version check is silently skipped.`);
    }
  });

  idRows.forEach((rows, id) => {
    if (rows.length > 1) {
      rows.forEach((i) => {
        push('error', i, `Addon #${i + 1} (${id}): "${id}" appears ${rows.length} times — qlsm only ever installs the first entry with that id.`);
      });
    }
  });

  return issues;
}

export function issueCounts(issues) {
  let errors = 0;
  let warnings = 0;
  issues.forEach((iss) => { if (iss.severity === 'error') errors += 1; else warnings += 1; });
  return { errors, warnings };
}
