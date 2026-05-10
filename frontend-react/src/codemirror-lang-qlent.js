import { StreamLanguage } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';

const QUOTED_STRING = /"(?:[^"\\]|\\.)*"/;
const BLANK_OR_COMMENT = /^\s*(?:\/\/.*)?$/;
const OPEN_ENTITY = /^\s*\{\s*(?:(?:\/\/).*)?$/;
const CLOSE_ENTITY = /^\s*\}\s*(?:(?:\/\/).*)?$/;
const KEY_VALUE_PAIR = /^\s*"(?:[^"\\]|\\.)*"\s+"(?:[^"\\]|\\.)*"\s*(?:(?:\/\/).*)?$/;

export const qlentLanguage = StreamLanguage.define({
  startState: function () {
    return {
      afterKey: false,
    };
  },
  token: function (stream, state) {
    if (stream.sol()) {
      state.afterKey = false;
    }

    if (stream.eatSpace()) {
      return null;
    }

    if (stream.match('//')) {
      stream.skipToEnd();
      return 'comment';
    }

    if (stream.match('{') || stream.match('}')) {
      state.afterKey = false;
      return 'operator';
    }

    if (stream.match(QUOTED_STRING)) {
      if (state.afterKey) {
        state.afterKey = false;
        return 'string';
      }
      state.afterKey = true;
      return 'attributeName';
    }

    stream.next();
    return 'invalid';
  },
  languageData: {
    commentTokens: { line: '//' },
  },
  tokenTable: {
    comment: t.lineComment,
    operator: t.operator,
    attributeName: t.attributeName,
    string: t.string,
    invalid: t.invalid,
  },
});

export const qlentLinter = (view) => {
  const diagnostics = [];
  let entityDepth = 0;

  for (let n = 1; n <= view.state.doc.lines; n++) {
    const line = view.state.doc.line(n);
    const text = line.text;

    if (BLANK_OR_COMMENT.test(text)) {
      continue;
    }

    if (OPEN_ENTITY.test(text)) {
      if (entityDepth > 0) {
        diagnostics.push({
          from: line.from + text.indexOf('{'),
          to: line.from + text.indexOf('{') + 1,
          severity: 'error',
          message: 'Nested entity blocks are not allowed.',
        });
      } else {
        entityDepth += 1;
      }
      continue;
    }

    if (CLOSE_ENTITY.test(text)) {
      if (entityDepth === 0) {
        diagnostics.push({
          from: line.from + text.indexOf('}'),
          to: line.from + text.indexOf('}') + 1,
          severity: 'error',
          message: 'Closing brace has no matching opening brace.',
        });
      } else {
        entityDepth -= 1;
      }
      continue;
    }

    if (KEY_VALUE_PAIR.test(text)) {
      if (entityDepth === 0) {
        diagnostics.push({
          from: line.from,
          to: line.to,
          severity: 'error',
          message: 'Entity key/value pairs must be inside braces.',
        });
      }
      continue;
    }

    const firstContent = text.search(/\S/);
    diagnostics.push({
      from: line.from + Math.max(firstContent, 0),
      to: line.to,
      severity: 'error',
      message: 'Expected {, }, // comment, or a quoted "key" "value" pair.',
    });
  }

  if (entityDepth > 0) {
    diagnostics.push({
      from: view.state.doc.length,
      to: view.state.doc.length,
      severity: 'error',
      message: 'Missing closing brace for entity block.',
    });
  }

  return diagnostics;
};
