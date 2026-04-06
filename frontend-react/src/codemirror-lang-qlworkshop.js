import { StreamLanguage } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';



// Custom CodeMirror 6 mode for Quake Live workshop.txt files
// Each line should be a Steam Workshop ID (number) or a comment.
// TEST: HMR should detect this change
export const qlworkshopLanguage = StreamLanguage.define({
  startState: function () {
    return { stage: "init" }; // Possible stages: init, after_number
  },
  token: function (stream, state) {
    if (stream.sol()) {
      state.stage = "init"; // Reset stage at the beginning of a new line
    }

    switch (state.stage) {
      case "init":
        // Handle comments first
        if (stream.match("\\\\") || stream.peek() === "#") { // Check for \\ or #
          stream.skipToEnd();
          return "comment";
        }

        // Handle blank lines or lines with only whitespace (after stripping initial spaces)
        if (stream.match(/^\s*$/, false)) { // Peek to see if it's all spaces
          if (stream.match(/^\s*$/)) { // Consume if it is
            return null;
          }
        }

        // Check for leading space error (if not blank line and not comment)
        // This implies stream.sol() was true, and stream.peek() was ' '
        // but it wasn't an all-whitespace line.
        if (stream.pos === 0 && stream.string[0] === ' ' && stream.string.trim() !== '') {
          stream.skipToEnd();
          return "invalid";
        }

        stream.eatSpace(); // Eat any leading spaces if not handled by above

        if (stream.eol()) return null; // Line became empty after eating spaces

        // Match digits for Workshop ID
        if (stream.match(/^[0-9]+/)) {
          state.stage = "after_number";
          return "workshopID"; // Will be mapped to t.number
        }

        // If nothing valid is found at the start of content
        stream.skipToEnd();
        return "invalid";

      case "after_number":
        // After a number, we expect either EOL or a comment.
        // Spaces are allowed before the comment.
        stream.eatSpace();
        if (stream.match("\\\\") || stream.peek() === "#") { // Check for \\ or #
          stream.skipToEnd();
          state.stage = "init"; // Reset for next line
          return "comment";
        }
        if (stream.eol()) {
          state.stage = "init"; // Reset for next line
          return null;
        }
        // Anything else after a number (and optional spaces) is an error
        stream.skipToEnd();
        state.stage = "init"; // Reset for next line
        return "invalid";
    }

    // Fallback for any unhandled scenario (should ideally not be reached)
    stream.skipToEnd();
    return "invalid";
  },
  // Map token types returned by the token function to Lezer highlight tags
  tokenTable: {
    comment: t.lineComment,
    workshopID: t.number,
    invalid: t.invalid
  },
  meta: {
    lineComment: '\\\\'
  }
});

// Optional linter for workshop.txt files
export const qlWorkshopLinter = (view) => {
  let diagnostics = [];
  for (let n = 1; n <= view.state.doc.lines; n++) {
    const line = view.state.doc.line(n);
    const text = line.text;
    const trimmedText = text.trim();

    // Skip empty lines and full-line comments
    if (trimmedText === '' || trimmedText.startsWith('#') || trimmedText.startsWith('\\\\')) {
      continue;
    }

    // Workshop IDs should start with numbers (no leading spaces), followed by optional spaces and \\ comment
    const validLineRegex = /^[0-9]+(\s*\\\\.*)?$/;

    if (!validLineRegex.test(text)) {
      diagnostics.push({
        from: line.from,
        to: line.to,
        severity: 'error',
        message: 'TEST: This should show if the linter is working - Expected: WORKSHOP_ID (numbers only)',
      });
    }
  }
  return diagnostics;
};
