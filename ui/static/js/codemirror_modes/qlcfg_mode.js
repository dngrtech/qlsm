// Custom CodeMirror mode for Quake Live CFG files
CodeMirror.defineMode("qlcfg", function() {
  return {
    startState: function() {
      return {
        afterSet: false // True if 'set' was just processed, expecting a variable name
      };
    },
    token: function(stream, state) {
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
      if (stream.match(/\bset\b/i)) {
        state.afterSet = true;
        return "keyword";
      }

      // Variable name after 'set'
      if (state.afterSet) {
        if (stream.match(/[a-zA-Z_][a-zA-Z0-9_]*/)) {
          state.afterSet = false; // Reset after matching the variable
          return "variable-2"; // A common token type for distinct variables
        }
      }
      
      // If nothing else matches, advance the stream
      stream.next();
      return null;
    }
  };
});
