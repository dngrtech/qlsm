import { describe, expect, it } from 'vitest';
import { EditorState } from '@codemirror/state';
import { CompletionContext } from '@codemirror/autocomplete';
import { operatorCompletionSource } from '../codemirror-lang-qlaccess';
import { setOperatorsCache } from '../utils/operatorsCache';

function contextFor(text) {
  const state = EditorState.create({ doc: text });
  return new CompletionContext(state, text.length, true);
}

describe('operatorCompletionSource', () => {
  it('completes a bare SteamID, with no numeric level', () => {
    setOperatorsCache([
      { name: 'Vex', steam_id64: '76561198012345678', default_level: 5 },
    ]);

    const result = operatorCompletionSource(contextFor(''));
    const completion = result.options[0];

    // The save path strips "<steamid>|<0-5>", so suggesting it would have
    // the editor offer text that silently vanishes on Save.
    expect(completion.apply).toBe('76561198012345678');
    expect(String(completion.apply)).not.toMatch(/\|/);
  });
});
