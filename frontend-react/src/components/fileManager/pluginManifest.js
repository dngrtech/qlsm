// Optional per-plugin metadata: <plugin>.ql-plugin.json next to <plugin>.py.
// The backend (script_routes.py) reads the sibling file and attaches its
// parsed content as `plugin_manifest` on the .py tree node — it never
// appears as its own row. Everything here is read-only display enrichment
// (cvars aside — see below); a plugin with no manifest still works exactly
// as a plain checkbox.
//
// Schema (all fields optional):
//   { label, description,
//     commands: [{ name, usage, permission, description }, ...],
//     cvars: [{ cvar, label, description, type, default, min, max }, ...] }
// `name` is what the player/admin types after ! (a plugin registering
// aliases, e.g. ("lobby", "servers"), gets one entry per alias so each shows
// up distinctly). `permission` is the minqlx permission level required
// (0 = anyone), omitted when the plugin doesn't gate the command.
// `cvars` declares the settings a plugin reads via get_cvar/set_cvar_once so
// the Plugins tab can offer a small edit form instead of hand-editing
// server.cfg. `cvar` is the actual cvar name; `type` is "bool" | "number" |
// "string" (anything else drops the entry); `min`/`max` only apply to
// "number". No plugin-to-plugin dependency graph — deliberately out of
// scope, real-world plugins essentially never need one.

export function getPluginManifest(item) {
  return item?.plugin_manifest && typeof item.plugin_manifest === 'object'
    ? item.plugin_manifest
    : null;
}

export function getPluginDisplayLabel(item) {
  const manifest = getPluginManifest(item);
  const label = manifest?.label;
  return typeof label === 'string' && label.trim() ? label.trim() : item?.name;
}

export function getPluginDescription(item) {
  const manifest = getPluginManifest(item);
  const description = manifest?.description;
  return typeof description === 'string' && description.trim() ? description.trim() : null;
}

// Commands the plugin registers, filtered/normalized to a safe shape. A
// malformed entry (missing name, wrong types) is dropped rather than
// thrown, since this only ever powers an advisory UI list.
export function getPluginCommands(item) {
  const manifest = getPluginManifest(item);
  const commands = manifest?.commands;
  if (!Array.isArray(commands)) return [];
  return commands
    .filter(c => c && typeof c === 'object' && typeof c.name === 'string' && c.name.trim())
    .map(c => ({
      name: c.name.trim(),
      usage: typeof c.usage === 'string' && c.usage.trim() ? c.usage.trim() : null,
      permission: Number.isInteger(c.permission) ? c.permission : null,
      description: typeof c.description === 'string' && c.description.trim() ? c.description.trim() : null,
    }));
}

const CVAR_TYPES = new Set(['bool', 'number', 'string']);

// Cvars the plugin exposes for editing, filtered/normalized to a safe shape.
// An entry missing a cvar name or with an unrecognized type is dropped
// rather than thrown, since a bad manifest should degrade to no edit form,
// not break the Plugins tab.
export function getPluginCvars(item) {
  const manifest = getPluginManifest(item);
  const cvars = manifest?.cvars;
  if (!Array.isArray(cvars)) return [];
  return cvars
    .filter(c => c && typeof c === 'object' && typeof c.cvar === 'string' && c.cvar.trim() && CVAR_TYPES.has(c.type))
    .map(c => {
      const cvar = c.cvar.trim();
      const label = typeof c.label === 'string' && c.label.trim() ? c.label.trim() : cvar;
      const description = typeof c.description === 'string' && c.description.trim() ? c.description.trim() : null;
      const min = c.type === 'number' && Number.isFinite(c.min) ? c.min : null;
      const max = c.type === 'number' && Number.isFinite(c.max) ? c.max : null;
      let defaultValue = null;
      if (c.type === 'bool' && typeof c.default === 'boolean') defaultValue = c.default;
      else if (c.type === 'number' && Number.isFinite(c.default)) defaultValue = c.default;
      else if (c.type === 'string' && typeof c.default === 'string') defaultValue = c.default;
      return { cvar, label, description, type: c.type, default: defaultValue, min, max };
    });
}

// One-line-per-command text block, for contexts (like a tooltip) that only
// render a plain string. `!name usage — description (perm N)`.
export function formatPluginCommandsText(item) {
  return getPluginCommands(item)
    .map(c => {
      const usage = c.usage ? ` ${c.usage}` : '';
      const perm = c.permission ? ` (perm ${c.permission})` : '';
      const desc = c.description ? ` — ${c.description}` : '';
      return `!${c.name}${usage}${desc}${perm}`;
    })
    .join('  ·  ');
}

// Every cvar the plugins of one server declare, for the config editor's
// autocomplete. Walks the Plugins tab's own file tree, so a plugin the
// operator uploaded counts exactly as much as a bundled one, and a plugin that
// is not on this server contributes nothing at all.
//
// `checkedPaths` are the plugins actually enabled (the ones that end up in
// qlx_plugins); their cvars are marked so the editor can offer them first.
export function collectPluginCvars(tree = [], checkedPaths = []) {
  const checked = checkedPaths instanceof Set ? checkedPaths : new Set(checkedPaths || []);
  const collected = [];
  const seen = new Set();

  const walk = (node) => {
    if (!node) return;
    if (node.type === 'folder') {
      (node.children || []).forEach(walk);
      return;
    }
    const path = node.path || node.name || '';
    if (!path.endsWith('.py')) return;
    const label = getPluginDisplayLabel(node);
    const enabled = checked.has(path);
    getPluginCvars(node).forEach((entry) => {
      const key = entry.cvar.toLowerCase();
      // A cvar shared by two plugins is listed once; an enabled plugin wins,
      // since that is the one actually reading it on this server.
      const existing = seen.has(key) ? collected.find(c => c.cvar.toLowerCase() === key) : null;
      if (existing) {
        if (enabled && !existing.enabled) Object.assign(existing, entry, { plugin: label, enabled });
        return;
      }
      seen.add(key);
      collected.push({ ...entry, plugin: label, enabled });
    });
  };
  (tree || []).forEach(walk);

  return collected;
}
