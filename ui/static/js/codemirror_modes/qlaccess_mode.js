// Custom CodeMirror mode for Quake Live Access files (steamid|level)
CodeMirror.defineMode("qlaccess", function() {
  return {
    startState: function() {
      // Stages: init, expecting_pipe, after_pipe, after_level, error_after_pipe, line_error
      return { stage: "init" };
    },
    token: function(stream, state) {
      // If already decided the line is an error, consume the rest
      if (state.stage === "line_error") {
        stream.skipToEnd();
        return "error";
      }

      if (stream.sol()) {
        state.stage = "init"; // Reset stage only if not already in error
      }

      switch (state.stage) {
        case "init":
          // Handle leading space error
          if (stream.sol() && stream.peek() === " ") {
            var lineIsOnlySpaces = true;
            for (var i = stream.pos; i < stream.string.length; i++) {
              if (stream.string[i] !== " ") { lineIsOnlySpaces = false; break; }
            }
            if (!lineIsOnlySpaces) {
              state.stage = "line_error"; stream.skipToEnd(); return "error";
            }
            // If only spaces, consume below and return null
          }
          stream.eatSpace(); // Consume leading/inter-token spaces if allowed by state

          // Handle comments
          if (stream.peek() === "#") {
            stream.skipToEnd(); return "comment";
          }
          
          // Handle blank lines
          if (stream.eol()) {
              return null;
          }

          // Match SteamID
          var steamIDRegex = /7[0-9]{16}/;
          var steamIDMatch = stream.match(steamIDRegex, false); // Peek
          if (steamIDMatch) {
            // Check if it's the *only* thing on the line so far (ignoring spaces)
             var lookaheadPos = stream.pos + steamIDMatch[0].length;
             var lookaheadStream = new CodeMirror.StringStream(stream.string, stream.tabSize, stream.lineOracle);
             lookaheadStream.pos = lookaheadPos;
             lookaheadStream.eatSpace(); // See if only spaces follow
             
             if (lookaheadStream.eol()) { // SteamID is alone on line (potentially incomplete)
                 stream.match(steamIDRegex); // Consume it
                 state.stage = "expecting_pipe"; // Expect pipe next
                 return "number"; // Style as number, not error yet
             }
             // If something else follows, check if it's a pipe
             var charAfterID = stream.string[stream.pos + steamIDMatch[0].length];
             if (charAfterID === "|") { // Pipe immediately follows
                 stream.match(steamIDRegex);
                 state.stage = "expecting_pipe"; // Expect pipe next (will be consumed immediately)
                 return "number"; 
             } else { // SteamID not followed immediately by pipe
                 stream.match(steamIDRegex); // Consume ID
                 state.stage = "line_error"; // Invalid char follows ID
                 return "error"; // Mark ID as error
             }
          }
          
          // Invalid start of line (not comment, space error, blank, or SteamID)
          state.stage = "line_error"; stream.next(); return "error";

        case "expecting_pipe":
          if (stream.peek() === "|") {
            stream.next(); // Consume pipe
            if (stream.peek() === " ") { // Space after pipe is error
              state.stage = "error_after_pipe"; // Specific error state
              return "operator";
            }
            state.stage = "after_pipe"; // Ready to expect level
            return "operator";
          } else if (stream.eol()) {
            // Reached end of line after valid SteamID, but no pipe yet. Not an error.
            return null; 
          } else { // Invalid char instead of pipe
            state.stage = "line_error"; stream.next(); return "error";
          }
        
        case "error_after_pipe": // Consume the space that caused the error
            stream.next(); // Consume the space
            state.stage = "line_error"; // Now consume rest of line as error
            return "error";

        case "after_pipe": // Expecting level immediately
          var levelRegex = /^(?:[0-5]|mod|admin|ban)\b/i;
          var levelMatch = stream.match(levelRegex, true); // Consume
          if (levelMatch) {
            var levelContent = levelMatch[0];
            var restOfLineAfterLevel = stream.string.substring(stream.pos);
            // Check if only whitespace or comment follows
            if (restOfLineAfterLevel.match(/^\s*(#.*)?$/)) {
              state.stage = "after_level"; // Valid level found, expect comment/eol
              return levelContent.match(/^[0-5]$/) ? "number" : "keyword";
            } else { // Junk follows level
              state.stage = "line_error"; // Mark rest as error
              // Return level token first, error state will catch rest
              return levelContent.match(/^[0-5]$/) ? "number" : "keyword"; 
            }
          } else if (stream.eol()) {
             // Reached end of line after valid SteamID + Pipe, but no level yet. Not an error.
            return null; 
          } else { // Invalid char instead of level
            state.stage = "line_error"; stream.next(); return "error";
          }

        case "after_level": // Expecting EOL or #comment
          stream.eatSpace();
          if (stream.peek() === "#") {
            stream.skipToEnd(); return "comment";
          }
          if (stream.eol()) {
            return null; // Valid end of line
          }
          // Junk after valid level + spaces
          state.stage = "line_error"; stream.next(); return "error";
      }

      // Fallback for unhandled states or characters
      if (!stream.eol()) {
        state.stage = "line_error"; stream.next(); return "error";
      }
      return null;
    }
  };
});
