/**
 * Custom CodeMirror 6 language support for log files.
 * Provides syntax highlighting for:
 * - Timestamps (dates and times)
 * - Log levels (ERROR, WARNING, INFO, DEBUG)
 * - File paths
 * - Python tracebacks
 * - Line numbers
 */
import { StreamLanguage } from '@codemirror/language';
import { tags } from '@lezer/highlight';

// Define the log language parser
const logLanguage = StreamLanguage.define({
    name: 'log',

    token(stream) {
        // Skip whitespace
        if (stream.eatSpace()) return null;

        // Match log levels - ERROR (most important)
        if (stream.match(/\bERROR\b/i)) {
            return 'invalid'; // Red color
        }

        // Match log levels - WARNING/WARN
        if (stream.match(/\b(WARNING|WARN)\b/i)) {
            return 'keyword'; // Yellow/orange color
        }

        // Match log levels - INFO
        if (stream.match(/\bINFO\b/i)) {
            return 'string'; // Green color
        }

        // Match log levels - DEBUG
        if (stream.match(/\bDEBUG\b/i)) {
            return 'comment'; // Gray color
        }

        // Match timestamps like "Jan 28 17:44:04" or "2026-01-28" or "17:44:04"
        if (stream.match(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\b/)) {
            return 'number'; // Cyan/blue color
        }
        if (stream.match(/\b\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}:\d{2}(\.\d+)?)?\b/)) {
            return 'number';
        }

        // Match Python exception types
        if (stream.match(/\b\w+Error\b|\b\w+Exception\b|\bTraceback\b/)) {
            return 'invalid'; // Red color
        }

        // Match file paths with line numbers like "/path/to/file.py", line 337
        if (stream.match(/File\s+"[^"]+",\s+line\s+\d+/)) {
            return 'meta'; // Special color for file references
        }

        // Match quoted file paths
        if (stream.match(/"[^"]*\.(py|js|jsx|ts|tsx|cfg|txt|log|sh|yml|yaml)"/)) {
            return 'string'; // Green color
        }

        // Match line numbers "line 123" or "Line 123"
        if (stream.match(/\bline\s+\d+\b/i)) {
            return 'number';
        }

        // Match process IDs like [23157]:
        if (stream.match(/\[\d+\]:/)) {
            return 'comment';
        }

        // Match bracket tags like [minqlx.log_exception]
        if (stream.match(/\[[^\]]+\]/)) {
            return 'attributeName';
        }

        // Match hostnames (word at start after timestamp)
        if (stream.match(/^[a-zA-Z][\w-]+(?=\s)/)) {
            return 'typeName';
        }

        // Skip to next interesting character
        stream.next();
        return null;
    },

    languageData: {
        commentTokens: { line: '#' },
    },
    tokenTable: {
        invalid: tags.invalid,
        keyword: tags.keyword,
        string: tags.string,
        comment: tags.comment,
        number: tags.number,
        meta: tags.meta,
        attributeName: tags.attributeName,
        typeName: tags.typeName
    }
});

// Export the language support
export function log() {
    return logLanguage;
}

export { logLanguage };
