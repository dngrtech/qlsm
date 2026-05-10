# Ent CodeMirror Highlighting Design

## Goal

Add syntax highlighting and lint diagnostics for uploaded `.ent` config files in the React CodeMirror editor.

## Approach

Create a dedicated CodeMirror 6 stream language for Quake entity files because `.ent` content is not JSON: entity attributes are adjacent quoted key/value strings without colons or commas. The mode will highlight braces as operators, keys as attribute names, values as strings, comments as line comments, and malformed tokens as invalid.

Add a small linter that reports unbalanced entity braces and non-empty lines that are not entity braces, comments, or `"key" "value"` pairs. The linter is advisory inside the editor and does not change backend upload or save validation.

## Integration

Route `.ent` files through the new language and linter in the config file managers used by Add Instance and Edit Instance. Expanded editors receive the same language and linter through the existing file-manager callbacks.

## Testing

Add focused unit tests for the `.ent` linter and routing tests in the Add Instance and Edit Instance component suites. Run the affected frontend tests with Vitest.
