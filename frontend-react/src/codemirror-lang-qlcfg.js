import { StreamLanguage } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';
import { autocompletion } from '@codemirror/autocomplete';

export const qlcfgLanguage = StreamLanguage.define({
  startState: function () {
    return {
      afterSet: false // True if 'set' was just processed, expecting a variable name
    };
  },
  token: function (stream, state) {
    if (stream.sol()) { // Start of line
      state.afterSet = false;
    }

    // Comments
    if (stream.match("//")) {
      stream.skipToEnd();
      return "comment";
    }

    // Strings
    if (stream.match(/"(?:[^\\]|\\.)*?"/)) {
      return "string";
    }

    // 'set' keyword
    if (stream.match(/\bset\b/i)) { // Use regex for whole word, case-insensitive match
      state.afterSet = true;
      return "keyword";
    }

    // Variable name after 'set'
    if (state.afterSet) {
      if (stream.match(/[a-zA-Z_][a-zA-Z0-9_]*/)) {
        state.afterSet = false; // Reset after matching the variable
        return "variableName"; // CodeMirror 6 uses camelCase for token types more often
      }
    }

    // If nothing else matches, advance the stream
    stream.next();
    return null;
  },
  languageData: {
    commentTokens: { line: "//" }
  },
  tokenTable: {
    comment: t.lineComment,
    string: t.string,
    keyword: t.keyword,
    variableName: t.variableName
  }
});

// Cvars managed by the app — setting these manually has no effect
const MANAGED_CVARS = {
  sv_servertype: 'Managed by the 99k LAN rate toggle. Default: 2 (99k LAN rate OFF).',
  sv_lanforcerate: 'Managed by the 99k LAN rate toggle. Default: 0 (99k LAN rate OFF).',
  net_ip: 'Forced to "" by the app (binds all interfaces, required for 99k LAN rate).',
  net_strict: 'Forced to 1 by the app.',
  qlx_redisaddress: 'Forced by the app. TCP hosts: 127.0.0.1:6379. Socket-enabled hosts: /var/run/redis/redis.sock.',
  qlx_redisunixsocket: 'Forced by the app. Set to 1 on socket-enabled hosts; omitted on TCP hosts.',
  qlx_redispassword: 'Forced by the app (self-host only).',
  qlx_redisdatabase: 'Managed by the app. Derived from instance port.',
  fs_homepath: 'Managed by the app.',
  qlx_pluginspath: 'Managed by the app.',
  zmq_rcon_enable: 'Managed by the app.',
  zmq_rcon_port: 'Managed by the app.',
  zmq_rcon_password: 'Managed by the app.',
  zmq_stats_port: 'Managed by the app.',
  zmq_stats_password: 'Managed by the app.',
  net_port: null, // Message depends on context — see linter
  qlx_plugins: 'Managed via the Plugins tab in the UI.',
};

// Strip values from managed cvars in a server.cfg string (set cvar "value" → set cvar "")
const MANAGED_CVAR_SET = new Set(Object.keys(MANAGED_CVARS));
export const stripManagedCvars = (cfg) => {
  if (!cfg) return cfg;
  return cfg.replace(
    /^(\s*seta?\s+)(\S+)(\s+")(.*?)(".*)/gim,
    (full, prefix, cvar, mid, _value, suffix) =>
      MANAGED_CVAR_SET.has(cvar.toLowerCase()) ? `${prefix}${cvar}${mid}${suffix}` : full
  );
};

// Factory function to create the linter with access to available ports and an error reporting callback
export const createQlCfgLinter = (availablePorts = [], onLintResults = () => { }) => {
  // The actual linter function returned by the factory
  return (view) => {
    let diagnostics = [];
    const setCvarRegex = /^\s*seta?\s+(\S+)/i; // Captures the cvar name after 'set' or 'seta'

    for (let n = 1; n <= view.state.doc.lines; n++) {
      const line = view.state.doc.line(n);
      const text = line.text; // Use full line text to get accurate positions

      // Check for managed cvars (info diagnostics) — runs first to skip
      // error-level checks (e.g. net_port validation) for app-managed cvars
      const cvarMatch = text.match(setCvarRegex);
      if (cvarMatch) {
        const cvarName = cvarMatch[1];
        const cvarKey = cvarName.toLowerCase();
        let infoMessage = MANAGED_CVARS[cvarKey];
        if (cvarKey === 'net_port') {
          infoMessage = availablePorts.length > 0
            ? 'Managed by the port selection above.'
            : 'Set during deployment and cannot be changed.';
        }
        if (infoMessage) {
          const cvarStartPos = line.from + text.indexOf(cvarName);
          diagnostics.push({
            from: cvarStartPos,
            to: cvarStartPos + cvarName.length,
            severity: 'info',
            message: `This cvar will be ignored. ${infoMessage}`,
          });
          continue;
        }
      }
    }
    // Report linting results (true if errors exist, false otherwise)
    const hasErrors = diagnostics.some(d => d.severity === 'error');
    onLintResults(hasErrors);
    return diagnostics;
  };
};

// ---------------------------------------------------------------------------
// Completion data
//
// Two sources, neither of them a list typed out by hand in this file:
//
//   * engine/server cvars and console commands come from the backend
//     (GET /api/cvar-catalog -> ui/data/ql_cvar_catalog.json, built by
//     scripts/gen_cvar_catalog.py from a listcvars dump of a real QLDS, the
//     annotated example server.cfg and the game's own factory definitions).
//     Every entry carries the source of its description so the tooltip can say
//     how much the wording is worth.
//
//   * qlx_* cvars come from the plugins of the server being edited: the
//     Plugins tab already loads a manifest per plugin, and whoever renders an
//     editor registers a provider that reads them out of that tree. A plugin
//     that is not on this server contributes nothing, and a plugin the
//     operator uploaded themselves contributes as much as a bundled one.
//
// Both are set from React (see hooks/useCvarAutocomplete.js). CodeMirror
// builds its extensions once, so the completion source reads this module
// state when it runs rather than closing over a snapshot.
// ---------------------------------------------------------------------------

let engineCatalog = { cvars: [], commands: [], gametypes: [], sources: {} };
const pluginCvarProviders = [];

export function setCvarCatalog(catalog) {
  engineCatalog = {
    cvars: Array.isArray(catalog?.cvars) ? catalog.cvars : [],
    commands: Array.isArray(catalog?.commands) ? catalog.commands : [],
    gametypes: Array.isArray(catalog?.gametypes) ? catalog.gametypes : [],
    sources: catalog?.sources || {},
  };
}

export function getCvarCatalog() {
  return engineCatalog;
}

// Registers a function returning the plugin cvars of the server currently
// being edited. Returns an unregister callback; the most recently registered
// provider wins, so a modal opened on top of a form doesn't inherit the
// form's plugins.
export function registerPluginCvarProvider(provider) {
  pluginCvarProviders.push(provider);
  return () => {
    const at = pluginCvarProviders.indexOf(provider);
    if (at !== -1) pluginCvarProviders.splice(at, 1);
  };
}

function currentPluginCvars() {
  for (let i = pluginCvarProviders.length - 1; i >= 0; i -= 1) {
    const cvars = pluginCvarProviders[i]();
    if (Array.isArray(cvars)) return cvars;
  }
  return [];
}

// Tooltip body. A plain string would lose the source line and the bit table,
// so completions render a small DOM node instead.
function renderInfo({ description, sourceNote, meta, bits, examples }) {
  return () => {
    const root = document.createElement('div');
    root.className = 'cm-cvar-info';
    const add = (text, className) => {
      if (!text) return;
      const line = document.createElement('div');
      if (className) line.className = className;
      line.textContent = text;
      root.appendChild(line);
    };
    add(description, 'cm-cvar-info-description');
    add(meta, 'cm-cvar-info-meta');
    if (bits?.length) {
      const table = document.createElement('div');
      table.className = 'cm-cvar-info-bits';
      bits.forEach(([value, label]) => {
        const row = document.createElement('div');
        row.textContent = `${value} — ${label}`;
        table.appendChild(row);
      });
      root.appendChild(table);
    }
    if (examples?.length) add(`Used by factories: ${examples.join(', ')}`, 'cm-cvar-info-meta');
    add(sourceNote, 'cm-cvar-info-source');
    return root;
  };
}

function managedOption(cvar, message) {
  return {
    label: cvar,
    detail: 'app-managed',
    type: 'variable',
    boost: 40,
    info: renderInfo({
      description: message ? `Managed by the app. ${message}` : 'Managed by the app.',
      sourceNote: 'Source: behaviour of this app.',
    }),
  };
}

function pluginOption(entry) {
  const bounds = [
    entry.default === null || entry.default === undefined ? null : `default ${entry.default}`,
    entry.min === null || entry.min === undefined ? null : `min ${entry.min}`,
    entry.max === null || entry.max === undefined ? null : `max ${entry.max}`,
  ].filter(Boolean).join(', ');
  return {
    label: entry.cvar,
    detail: entry.enabled ? `${entry.plugin} (enabled)` : `${entry.plugin} (not enabled)`,
    type: 'variable',
    boost: entry.enabled ? 99 : 60,
    info: renderInfo({
      description: entry.description || `Setting of the ${entry.plugin} plugin.`,
      meta: [entry.type, bounds].filter(Boolean).join(' · ') || null,
      sourceNote: entry.enabled
        ? `Source: manifest of ${entry.plugin}, enabled on this server.`
        : `Source: manifest of ${entry.plugin}, present on this server but not enabled.`,
    }),
  };
}

function engineOption(entry) {
  const sourceLabel = engineCatalog.sources?.[entry.source];
  return {
    label: entry.name,
    detail: entry.group || 'cvar',
    type: 'variable',
    boost: 0,
    info: renderInfo({
      description: entry.description || 'No description recorded for this cvar.',
      bits: entry.bitmask?.bits,
      examples: entry.examples,
      sourceNote: sourceLabel ? `Source: ${sourceLabel}.` : null,
    }),
  };
}

// Order: plugin cvars of this server first (enabled ones at the top), then the
// cvars this app manages itself, then everything the engine registers. Within
// each block a name that starts with what was typed beats one that merely
// contains it.
export function cvarCompletionOptions(prefix) {
  const lower = (prefix || '').toLowerCase();
  const matches = name => !lower || name.toLowerCase().includes(lower);
  const seen = new Set();
  const options = [];
  const push = (name, build) => {
    const key = name.toLowerCase();
    if (seen.has(key) || !matches(name)) return;
    seen.add(key);
    const option = build();
    if (lower && key.startsWith(lower)) option.boost = (option.boost || 0) + 10;
    options.push(option);
  };

  currentPluginCvars().forEach(entry => push(entry.cvar, () => pluginOption(entry)));
  Object.entries(MANAGED_CVARS).forEach(([cvar, message]) => push(cvar, () => managedOption(cvar, message)));
  engineCatalog.cvars.forEach(entry => push(entry.name, () => engineOption(entry)));

  return options.sort((left, right) => (right.boost || 0) - (left.boost || 0));
}

export function commandCompletionOptions(prefix) {
  const lower = (prefix || '').toLowerCase();
  return engineCatalog.commands
    .filter(command => command.name.toLowerCase().includes(lower))
    .map(command => ({
      label: command.name,
      detail: 'command',
      type: 'keyword',
      boost: command.name.toLowerCase().startsWith(lower) ? 10 : 0,
      info: renderInfo({
        description: command.description,
        sourceNote: 'Source: verified Quake Live console command reference.',
      }),
    }));
}

// Suggests cvar names right after `set ` / `seta `, or console commands at the
// start of a line. Returns null inside comments so it stays out of the way
// while editing a value.
function qlCfgCompletionSource(context) {
  const line = context.state.doc.lineAt(context.pos);
  const before = line.text.slice(0, context.pos - line.from);
  if (/\/\//.test(before)) return null; // past a comment marker on this line

  const setMatch = before.match(/^\s*seta?\s+(\S*)$/i);
  if (setMatch) {
    const word = context.matchBefore(/\S*/);
    const options = cvarCompletionOptions(setMatch[1]);
    if (options.length === 0) return null;
    return { from: word ? word.from : context.pos, options, filter: false };
  }

  const bareWordMatch = before.match(/^\s*(\S*)$/);
  if (bareWordMatch) {
    const word = context.matchBefore(/\S*/);
    const options = commandCompletionOptions(bareWordMatch[1]);
    if (options.length === 0) return null;
    return { from: word ? word.from : context.pos, options, filter: false };
  }

  return null;
}

export const qlCfgCompletion = autocompletion({ override: [qlCfgCompletionSource] });
