import { StreamLanguage } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';

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
  net_strict: 'Forced to 1 by the app.',
  qlx_serverbrandname: 'Derived from the sv_hostname value.',
  qlx_redisdatabase: 'Managed by the app.',
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
    /^(\s*set\s+)(\S+)(\s+")(.*?)(".*)/gim,
    (full, prefix, cvar, mid, _value, suffix) =>
      MANAGED_CVAR_SET.has(cvar.toLowerCase()) ? `${prefix}${cvar}${mid}${suffix}` : full
  );
};

// Factory function to create the linter with access to available ports and an error reporting callback
export const createQlCfgLinter = (availablePorts = [], onLintResults = () => { }) => {
  // The actual linter function returned by the factory
  return (view) => {
    let diagnostics = [];
    const setCvarRegex = /^\s*set\s+(\S+)/i; // Captures the cvar name after 'set'

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
