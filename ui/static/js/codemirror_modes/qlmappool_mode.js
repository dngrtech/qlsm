// Custom CodeMirror mode for Quake Live Mappool files
CodeMirror.defineMode("qlmappool", function() {
  return {
    startState: function() {
      // Stages: init, expecting_pipe, after_pipe, after_factory, error_after_pipe, line_error
      // Renamed after_map to expecting_pipe for clarity with qlaccess logic
      return { stage: "init" };
    },
    token: function(stream, state) {
      if (state.stage === "line_error") {
        stream.skipToEnd();
        return "error";
      }

      if (stream.sol()) {
        state.stage = "init";
      }

      switch (state.stage) {
        case "init":
          if (stream.sol() && stream.peek() === " ") {
            var lineIsOnlySpaces = true;
            for (var i = stream.pos; i < stream.string.length; i++) {
              if (stream.string[i] !== " ") { lineIsOnlySpaces = false; break; }
            }
            if (!lineIsOnlySpaces) {
              state.stage = "line_error"; stream.skipToEnd(); return "error";
            }
          }
          stream.eatSpace();

          if (stream.peek() === "#") {
            stream.skipToEnd(); return "comment";
          }
          if (stream.eol()) {
            return null;
          }

          var mapNameRegex = /[^|#\s](?:[^|#]*[^|#\s])?|[^|#\s]/;
          var mapNameMatch = stream.match(mapNameRegex, false); // Peek
          if (mapNameMatch) {
            var mapNameContent = mapNameMatch[0];
            var lookaheadPos = stream.pos + mapNameContent.length;
            var lookaheadStream = new CodeMirror.StringStream(stream.string, stream.tabSize, stream.lineOracle);
            lookaheadStream.pos = lookaheadPos;
            lookaheadStream.eatSpace(); // See if only spaces follow

            if (lookaheadStream.eol()) { // Map name is alone on line (incomplete)
              stream.match(mapNameContent);
              state.stage = "expecting_pipe";
              return "variable"; // Not an error yet
            }
            var charAfterMap = stream.string[stream.pos + mapNameContent.length];
            if (charAfterMap === "|") { // Pipe immediately follows
              stream.match(mapNameContent);
              state.stage = "expecting_pipe"; // Will consume pipe in next state
              return "variable";
            } else { // Map name not followed by pipe or EOL (after spaces)
              stream.match(mapNameContent);
              state.stage = "line_error";
              return "error"; // Map name itself is part of an error
            }
          }
          state.stage = "line_error"; stream.next(); return "error";

        case "expecting_pipe": // Was 'after_map'
          // No eatSpace here, pipe must be immediate from map name logic
          if (stream.peek() === "|") {
            stream.next(); // Consume pipe
            if (stream.peek() === " ") { // Space after pipe is error
              state.stage = "error_after_pipe"; // Specific error state
              return "operator";
            }
            state.stage = "after_pipe";
            return "operator";
          } else if (stream.eol()) {
            return null; // Incomplete line (mapname), not an error yet
          } else { // Invalid char instead of pipe
            state.stage = "line_error"; stream.next(); return "error";
          }

        case "error_after_pipe": // Consume the space that caused the error
            stream.next(); // Consume the space
            state.stage = "line_error";
            return "error";

        case "after_pipe": // Expecting factory immediately
          // No eatSpace here, factory must be immediate
          var factoryRegex = /[^#\s][^#]*/; // Factory name can be simple
          var factoryMatch = stream.match(factoryRegex, false); // Peek
          if (factoryMatch) {
            var factoryContent = factoryMatch[0];
            var restOfLineAfterFactory = stream.string.substring(stream.pos + factoryContent.length);
            if (restOfLineAfterFactory.match(/^\s*(#.*)?$/)) { // EOL or spaces then #comment
              stream.match(factoryContent);
              state.stage = "after_factory";
              return "string-2"; // Factory ID
            } else { // Junk after factory
              stream.match(factoryContent);
              state.stage = "line_error";
              return "string-2"; // Factory tokenized, rest is error
            }
          } else if (stream.eol()) {
            return null; // Incomplete (mapname|), not an error yet
          } else { // Invalid char instead of factory
            state.stage = "line_error"; stream.next(); return "error";
          }
          
        case "after_factory": // Expecting EOL or #comment
          stream.eatSpace();
          if (stream.peek() === "#") {
            stream.skipToEnd(); return "comment";
          }
          if (stream.eol()) {
            return null;
          }
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
