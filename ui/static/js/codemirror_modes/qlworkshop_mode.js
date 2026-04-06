// Custom CodeMirror mode for Quake Live workshop.txt files
CodeMirror.defineMode("qlworkshop", function() {
  return {
    token: function(stream, state) {
      // Handle comments first
      if (stream.sol() && stream.peek() === "#") {
        stream.skipToEnd();
        return "comment";
      }

      // Handle blank lines or lines with only whitespace
      if (stream.sol() && stream.match(/^\s*$/, true)) { // Consume the whitespace if it's the whole line
        return null; // No style for blank lines
      }

      // Check for leading space error (if not blank line)
      if (stream.sol() && stream.peek() === " ") {
          stream.skipToEnd(); // Consume rest of line
          return "error"; // Leading space is error
      }

      // If we get here, line is not comment, not blank, and doesn't start with space.
      // It should contain only digits.
      var lineContentMatch = stream.match(/^[0-9]+$/, false); // Peek: Check if the rest of the line is ONLY digits
      
      if (lineContentMatch) {
          // It looks like a valid number line, consume the number part
          stream.match(/^[0-9]+/); // Consume the number
          // Check if anything remains on the line (e.g., trailing space, other chars)
          if (!stream.eol()) {
              stream.skipToEnd(); // Consume the rest
              return "error"; // Trailing characters/spaces are an error
          }
          // If we reached EOL exactly after the number, it's valid
          return "number"; // Valid number line
      } else {
          // Line contains non-digits or internal spaces or other invalid format
          stream.skipToEnd(); // Consume the whole invalid line
          return "error";
      }
    }
  };
});
