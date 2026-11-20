// Pure helpers for the declarative panel contract. No React, no network --
// this is the part that is easiest to get subtly wrong and cheapest to test.

export const SCOPE_HOST = 'host';
export const SCOPE_INSTANCE = 'instance';
export const SCOPE_GLOBAL = 'global';

// Which scope each mount point acts on. A host menu entry is always about
// that host; an instance tab is always about that instance. Deriving it from
// the mount point rather than letting the manifest declare it removes a whole
// class of "addon asked for the wrong scope" bugs.
export const MOUNT_SCOPES = {
  host_menu: SCOPE_HOST,
  instance_menu: SCOPE_INSTANCE,
  instance_tabs: SCOPE_INSTANCE,
  settings_section: SCOPE_GLOBAL,
  page: SCOPE_GLOBAL,
  live_status_columns: SCOPE_INSTANCE,
  // The instance does not exist yet; the tab is about the host picked in the
  // Add Instance form, which is what its `load` route can name.
  add_instance_tabs: SCOPE_HOST,
};

/**
 * Split "GET hosts/{host_id}" into { method, path }.
 * A route with no verb defaults to GET, which is what most `load` routes are.
 */
export function parseRoute(route) {
  if (typeof route !== 'string' || !route.trim()) return null;
  const trimmed = route.trim();
  // Plain spaces only, matching _split_route() in ui/addons/manifest.py: the
  // manifest validator checks the path this returns, so both must split alike.
  const match = trimmed.match(/^(GET|POST|PUT|PATCH|DELETE) +(.*)$/i);
  if (match) {
    return { method: match[1].toUpperCase(), path: match[2].trim() };
  }
  return { method: 'GET', path: trimmed };
}

/**
 * Substitute {host_id} / {instance_id} / {scope_id} / {addon_id} in a path.
 *
 * An unknown placeholder is left as-is rather than replaced with "undefined":
 * a URL containing a literal {foo} fails loudly at the backend, whereas
 * ".../undefined" looks like a real request and can hit the wrong row.
 */
export function fillPath(path, { scope, scopeId, addonId } = {}) {
  if (typeof path !== 'string') return '';
  const values = {
    scope_id: scopeId,
    addon_id: addonId,
    host_id: scope === SCOPE_HOST ? scopeId : undefined,
    instance_id: scope === SCOPE_INSTANCE ? scopeId : undefined,
  };
  return path.replace(/\{(\w+)\}/g, (whole, key) => {
    const value = values[key];
    return value === undefined || value === null ? whole : String(value);
  });
}

/** parseRoute + fillPath in one step. Returns null when there is no route. */
export function resolveRoute(route, context) {
  const parsed = parseRoute(route);
  if (!parsed) return null;
  return { method: parsed.method, path: fillPath(parsed.path, context) };
}

/**
 * Normalize one manifest field into what the form renderer needs.
 * Anything with an unusable type is dropped, matching how the backend's
 * manifest validator and the existing plugin-cvars form both behave: a bad
 * entry is skipped, never thrown.
 */
const FIELD_TYPES = ['bool', 'number', 'string', 'secret', 'select'];

export function normalizeFields(fields) {
  if (!Array.isArray(fields)) return [];
  return fields
    .filter(f => f && typeof f === 'object')
    .filter(f => typeof f.key === 'string' && f.key.trim())
    .filter(f => FIELD_TYPES.includes(f.type))
    .map(f => ({
      key: f.key.trim(),
      type: f.type,
      label: typeof f.label === 'string' && f.label.trim() ? f.label.trim() : f.key.trim(),
      description: typeof f.description === 'string' ? f.description : '',
      placeholder: typeof f.placeholder === 'string' ? f.placeholder : '',
      min: typeof f.min === 'number' ? f.min : undefined,
      max: typeof f.max === 'number' ? f.max : undefined,
      options: f.type === 'select' && Array.isArray(f.options) ? f.options : undefined,
      // Carried through deliberately: without it an unset number field starts
      // at 0, which for a field declared `min: 1` is invalid the moment the
      // form renders -- the operator sees a validation error they never caused.
      default: Object.prototype.hasOwnProperty.call(f, 'default') ? f.default : undefined,
    }));
}

/** Starting form state for a field set, given whatever the API returned. */
export function initialValues(fields, loaded) {
  const source = loaded && typeof loaded === 'object' ? loaded : {};
  const out = {};
  for (const field of fields) {
    const value = source[field.key];
    const fallback = field.default;
    if (value !== undefined && value !== null) {
      out[field.key] = field.type === 'bool' ? Boolean(value) : value;
    } else if (fallback !== undefined && fallback !== null) {
      out[field.key] = field.type === 'bool' ? Boolean(fallback) : fallback;
    } else if (field.type === 'bool') {
      out[field.key] = false;
    } else if (field.type === 'number') {
      out[field.key] = 0;
    } else {
      out[field.key] = '';
    }
  }
  return out;
}

/**
 * Client-side check mirroring the backend's own coercion rules.
 *
 * Deliberately a mirror, not the authority: the backend validates every write
 * regardless. This exists so a typo shows up under the field instead of as a
 * round-trip 400 -- the same split the repo already uses for host-name and
 * LAN-rate validation.
 */
export function validateValues(fields, values) {
  const errors = {};
  for (const field of fields) {
    const value = values[field.key];
    if (field.type !== 'number') continue;
    if (value === '' || value === null || value === undefined) {
      errors[field.key] = 'Required';
      continue;
    }
    const number = Number(value);
    if (Number.isNaN(number)) {
      errors[field.key] = 'Must be a number';
    } else if (field.min !== undefined && number < field.min) {
      errors[field.key] = `Must be at least ${field.min}`;
    } else if (field.max !== undefined && number > field.max) {
      errors[field.key] = `Must be at most ${field.max}`;
    }
  }
  return errors;
}

/** Coerce form state into the JSON the backend expects. */
export function serializeValues(fields, values) {
  const out = {};
  for (const field of fields) {
    const value = values[field.key];
    if (field.type === 'bool') out[field.key] = Boolean(value);
    else if (field.type === 'number') out[field.key] = Number(value);
    else out[field.key] = value ?? '';
  }
  return out;
}
