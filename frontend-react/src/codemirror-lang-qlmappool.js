import { StreamLanguage } from '@codemirror/language';
import { tags as t } from '@lezer/highlight'; // Import Lezer tags

// Custom CodeMirror 6 mode for Quake Live Mappool files (mappool.txt)
// Adapted from the CodeMirror 5 qlmappool_mode.js
export const qlmappoolLanguage = StreamLanguage.define({
  startState: function() {
    // Stages: init, expecting_pipe, after_pipe, after_factory, error_after_pipe, line_error
    return { stage: "init" };
  },
  token: function(stream, state) {
    if (state.stage === "line_error") {
      stream.skipToEnd();
      return "error"; // Use string token
    }

    if (stream.sol()) {
      state.stage = "init"; // Reset stage at the beginning of a new line
    }

    switch (state.stage) {
      case "init":
        // Check for lines starting with a space that are not entirely spaces
        if (stream.sol() && stream.peek() === " ") {
          const lineContent = stream.string.slice(stream.pos);
          if (lineContent.trim() !== "" && lineContent[0] === " ") {
             // Line starts with space but is not empty after trimming initial spaces
             // This was an error condition in the original CM5 mode.
             // However, if it's just indentation before a comment or valid content, it might be okay.
             // For now, let's stick to original logic: if it starts with space and isn't *only* spaces, it's an error.
             let isOnlySpaces = true;
             for (let i = 0; i < lineContent.length; i++) {
                 if (lineContent[i] !== ' ') {
                     isOnlySpaces = false;
                     break;
                 }
             }
             if (!isOnlySpaces && stream.string.trim() !== "") { // if it's not just spaces and not an effectively empty line
                state.stage = "line_error";
                stream.skipToEnd();
                return "error"; // Use string token
             }
          }
        }
        stream.eatSpace(); // Consume leading spaces

        if (stream.peek() === "#") {
          stream.skipToEnd();
          return "comment"; // Use string token
        }
        if (stream.eol()) {
          return null; // Empty line or line with only spaces
        }

        // Regex for map name: one or more non-|#\s characters.
        // It should not consume trailing spaces here.
        const mapNameRegex = /[^|#\s]+/; 
        if (stream.match(mapNameRegex)) {
          state.stage = "expecting_pipe";
          return "variableName"; // Use string token (CM6 style)
        }
        
        // If nothing matched, it's an error
        state.stage = "line_error";
        stream.next(); // Consume one char
        return "error"; // Use string token

      case "expecting_pipe":
        stream.eatSpace(); // Allow spaces between map name and pipe
        if (stream.peek() === "|") {
          stream.next(); // Consume pipe
          state.stage = "after_pipe";
          return "operator"; // Use string token
        } else if (stream.eol()) {
          return null; // Map name alone is not an error yet, could be an incomplete line
        } else if (stream.peek() === "#") {
          stream.skipToEnd();
          return "comment"; // Use string token
        }
        // Anything else after map name and spaces (if not pipe or comment) is an error
        state.stage = "line_error";
        stream.next();
        return "error"; // Use string token

      case "after_pipe":
        stream.eatSpace(); // Allow spaces between pipe and factory
        if (stream.peek() === "#") {
            stream.skipToEnd();
            return "comment"; // Use string token
        }
        if (stream.eol()) {
            return null; // map_name| is not an error yet, could be incomplete
        }

        // Regex for factory ID: one or more non-#\s characters.
        const factoryRegex = /[^#\s]+/;
        if (stream.match(factoryRegex)) {
          state.stage = "after_factory";
          return "string"; // Use string token
        }
        
        // Invalid char instead of factory or comment
        state.stage = "line_error";
        stream.next();
        return "error"; // Use string token
        
      case "after_factory":
        stream.eatSpace(); // Consume spaces after factory ID
        if (stream.peek() === "#") {
          stream.skipToEnd();
          return "comment"; // Use string token
        }
        if (stream.eol()) {
          return null; // Valid end of line
        }
        // Anything else after factory and spaces (if not comment) is an error
        state.stage = "line_error";
        stream.next();
        return "error"; // Use string token
    }

    // Fallback for unhandled states or characters
    if (!stream.eol()) {
      state.stage = "line_error";
      stream.next();
      return "error"; // Use string token
    }
    return null;
  },
  meta: {
    lineComment: '#'
  },
  tokenTable: {
    comment: t.lineComment,
    error: t.invalid,
    variableName: t.variableName, // Map name
    operator: t.operator,       // Pipe symbol
    string: t.string          // Factory ID
  }
});
