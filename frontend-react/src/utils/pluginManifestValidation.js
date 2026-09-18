// Checks a client-side draft of a repository's `qlsm-plugins.json` plugin
// list against what the two real consumers actually do with it:
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
//
// Mirrors ui/plugin_repositories.py's `_FILENAME_RE` exactly.
const FILENAME_RE = /^[A-Za-z0-9_-]+\.py$/;
// Mirrors PluginCvarsModal.jsx's three branches (bool / number / else-string).
const KNOWN_CVAR_TYPES = ['string', 'number', 'bool'];
// Mirrors ui/plugin_repositories.py's _parse_dotted_version(): any number of
// dot-separated integers, not necessarily three.
const DOTTED_VERSION_RE = /^\d+(\.\d+)*$/;

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

  const filenameCounts = new Map();

  plugins.forEach((p, i) => {
    const label = p?.filename ? `#${i + 1} (${p.filename})` : `#${i + 1}`;

    if (!p?.filename || !FILENAME_RE.test(p.filename)) {
      issues.push({
        severity: 'error',
        index: i,
        message: `Plugin ${label}: filename must be a bare "name.py" (letters, digits, "_" and "-" only) — anything else is silently dropped when qlsm fetches this file.`,
      });
    } else {
      filenameCounts.set(p.filename, (filenameCounts.get(p.filename) || 0) + 1);
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

  filenameCounts.forEach((count, filename) => {
    if (count > 1) {
      issues.push({
        severity: 'error',
        message: `"${filename}" appears ${count} times — duplicate filenames collide in qlsm's plugin list.`,
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
