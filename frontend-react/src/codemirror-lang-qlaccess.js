import { StreamLanguage } from '@codemirror/language';
import { Tag, tags as t } from '@lezer/highlight'; // Import Tag and standard tags

// Define custom tags for specific keywords
export const modTag = Tag.define();
export const adminTag = Tag.define();
export const banTag = Tag.define();

// Custom CodeMirror 6 mode for Quake Live Access files (access.txt)
// Format: STEAM_ID|LEVEL // optional comment
// STEAM_ID: 7 followed by 16 digits
// LEVEL: 0-5, mod, admin, ban (case-insensitive)
export const qlaccessLanguage = StreamLanguage.define({
  startState: function() {
    // Stages: init, expecting_pipe, after_pipe, after_level, line_error
    return { stage: "init" };
  },
  token: function(stream, state) {
    if (state.stage === "line_error") {
      stream.skipToEnd();
      return "invalid"; // This token type won't be styled unless mapped in tokenTable
    }

    if (stream.sol()) {
      state.stage = "init";
    }

    switch (state.stage) {
      case "init":
        if (stream.sol() && stream.peek() === " ") {
          const lineContent = stream.string.slice(stream.pos);
          if (lineContent.trim() !== "" && lineContent[0] === " ") {
             let isOnlySpaces = true;
             for (let i = 0; i < lineContent.length; i++) {
                 if (lineContent[i] !== ' ') {
                     isOnlySpaces = false;
                     break;
                 }
             }
             if (!isOnlySpaces && stream.string.trim() !== "") {
                state.stage = "line_error";
                stream.skipToEnd();
                return "invalid";
             }
          }
        }
        stream.eatSpace();

        if (stream.match("#")) {
          stream.skipToEnd();
          return "comment"; // Will be mapped to t.lineComment
        }
        if (stream.eol()) {
          return null;
        }

        // SteamID should be all digits
        const steamIDRegex = /[0-9]+/;
        if (stream.match(steamIDRegex)) {
          state.stage = "expecting_pipe";
          return "steamID"; // Will be mapped to t.number
        }
        
        state.stage = "line_error";
        stream.next();
        return "invalid";

      case "expecting_pipe":
        stream.eatSpace();
        if (stream.peek() === "|") {
          stream.next();
          state.stage = "after_pipe";
          return "pipeOperator"; // Will be mapped to t.operator
        } else if (stream.eol()) {
          return null;
        } else if (stream.match("#")) {
          stream.skipToEnd();
          return "comment";
        }
        state.stage = "line_error";
        stream.next();
        return "invalid";

      case "after_pipe":
        stream.eatSpace();
        if (stream.match("#")) {
            stream.skipToEnd();
            return "comment";
        }
        if (stream.eol()) {
            return null;
        }

        const levelRegex = /^(?:[0-5]|mod|admin|ban)\b/i;
        const match = stream.match(levelRegex, true);
        if (match) {
          state.stage = "after_level";
          const matchedValue = match[0].toLowerCase();
          if (matchedValue.match(/^[0-5]$/)) {
            return "levelNumber"; // Will be mapped to t.number
          } else if (matchedValue === "ban") {
            return "banKeyword"; // Mapped to banTag
          } else if (matchedValue === "mod") {
            return "modKeyword"; // Mapped to modTag
          } else if (matchedValue === "admin") {
            return "adminKeyword"; // Mapped to adminTag
          }
        }
        
        state.stage = "line_error";
        stream.next();
        return "invalid";
        
      case "after_level":
        stream.eatSpace();
        if (stream.match("#")) {
          stream.skipToEnd();
          return "comment";
        }
        if (stream.eol()) {
          return null;
        }
        state.stage = "line_error";
        stream.next();
        return "invalid";
    }

    if (!stream.eol()) {
      state.stage = "line_error";
      stream.next();
      return "invalid";
    }
    return null;
  },
  // Map token types returned by the token function to Lezer highlight tags
  tokenTable: {
    comment: t.lineComment,
    steamID: t.number, // Style SteamIDs as numbers
    pipeOperator: t.operator,
    levelNumber: t.number, // Style numeric levels as numbers
    banKeyword: banTag,
    modKeyword: modTag,
    adminKeyword: adminTag,
    invalid: t.invalid, // Style invalid parts with a standard invalid tag
  },
  meta: {
    lineComment: '#'
  }
});

export const qlAccessLinter = (view) => {
  let diagnostics = [];
  for (let n = 1; n <= view.state.doc.lines; n++) { // Iterate from line 1 to total lines
    const line = view.state.doc.line(n);
    const text = line.text.trim();

    if (text === '' || text.startsWith('#')) { // Skip empty lines and comments
      continue;
    }

    // More lenient linting during editing
    // Check for specific error conditions rather than requiring a complete valid line

    // 1. Check for invalid SteamID format (must contain only digits)
    if (text.length > 0 && !text.startsWith('#')) {
      // If there's a pipe, check the part before it
      const parts = text.split('|');
      const steamIDPart = parts[0].trim();
      
      // Only check if there's content to check
      if (steamIDPart.length > 0) {
        // SteamID should contain only digits
        if (/[^0-9]/.test(steamIDPart)) {
          diagnostics.push({
            from: line.from, // Start of the line
            to: line.from + steamIDPart.length + (text.indexOf(steamIDPart)),
            severity: 'error',
            message: 'SteamID must contain only digits',
          });
        }
      }

      // 2. If there's a level part (after the pipe), check if it's valid
      if (parts.length > 1) {
        let levelPart = parts[1].trim();
        
        // Remove any comment
        if (levelPart.includes('#')) {
          levelPart = levelPart.split('#')[0].trim();
        }
        
        // Only check if there's content to check
        if (levelPart.length > 0) {
          // Level should be 0-5, mod, admin, or ban
          const validLevelRegex = /^(?:[0-5]|mod|admin|ban)$/i;
          if (!validLevelRegex.test(levelPart)) {
            // Find the position of the level part in the original text
            const levelStartPos = text.indexOf('|') + 1 + text.substring(text.indexOf('|') + 1).indexOf(levelPart);
            
            diagnostics.push({
              from: line.from + levelStartPos,
              to: line.from + levelStartPos + levelPart.length,
              severity: 'error',
              message: 'Level must be 0-5, mod, admin, or ban',
            });
          }
        }
      }
    }
  }
  return diagnostics;
};
