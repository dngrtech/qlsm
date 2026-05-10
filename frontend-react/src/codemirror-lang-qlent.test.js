import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';

import { qlentLinter } from './codemirror-lang-qlent';

function lint(doc) {
  return qlentLinter({
    state: EditorState.create({ doc }),
  });
}

describe('qlentLinter', () => {
  it('accepts entity blocks with quoted key/value pairs', () => {
    const diagnostics = lint(`{
"_lightmapscale" ".5"
"author" "Tom 'Phantazm11' Perryman"
"message" "Corrosion"
"classname" "worldspawn"
}`);

    expect(diagnostics).toEqual([]);
  });

  it('reports missing closing braces', () => {
    const diagnostics = lint(`{
"classname" "worldspawn"`);

    expect(diagnostics).toEqual([
      expect.objectContaining({
        severity: 'error',
        message: 'Missing closing brace for entity block.',
      }),
    ]);
  });

  it('reports malformed non-empty lines', () => {
    const diagnostics = lint(`{
classname worldspawn
}`);

    expect(diagnostics).toEqual([
      expect.objectContaining({
        severity: 'error',
        message: 'Expected {, }, // comment, or a quoted "key" "value" pair.',
      }),
    ]);
  });

  it('reports key/value pairs outside braces', () => {
    const diagnostics = lint('"classname" "worldspawn"');

    expect(diagnostics).toEqual([
      expect.objectContaining({
        severity: 'error',
        message: 'Entity key/value pairs must be inside braces.',
      }),
    ]);
  });
});
