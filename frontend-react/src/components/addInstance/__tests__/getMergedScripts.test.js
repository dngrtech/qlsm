import { describe, it, expect } from 'vitest';

/**
 * Unit tests for the getMergedScripts logic used in AddInstanceForm.
 *
 * The helper merges `scripts` (base/loaded content) with `editedScripts`
 * (user modifications), filters out null placeholders (not-yet-fetched files),
 * and returns null when scriptsLoaded is false or no content remains.
 *
 * We test the merge logic directly rather than rendering the full form
 * component, which has heavy dependencies (CodeMirror, API calls, etc.).
 */

// Pure implementation matching the extracted getMergedScripts useCallback body
function getMergedScripts(scriptsLoaded, scripts, editedScripts) {
    const base = scriptsLoaded ? scripts : {};
    const merged = { ...base, ...editedScripts };
    const filtered = Object.fromEntries(
        Object.entries(merged).filter(([, content]) => content != null)
    );
    return Object.keys(filtered).length > 0 ? filtered : null;
}

describe('getMergedScripts', () => {
    it('returns null when scripts are not loaded and no editedScripts', () => {
        const result = getMergedScripts(false, { 'a.py': 'code' }, {});
        expect(result).toBeNull();
    });

    it('includes editedScripts even when scriptsLoaded is false', () => {
        // User uploaded files before the tree loaded — uploads must not be dropped
        const result = getMergedScripts(false, { 'a.py': 'code' }, { 'uploaded.py': 'upload_code' });
        expect(result).toEqual({ 'uploaded.py': 'upload_code' });
    });

    it('returns null when all entries are null placeholders', () => {
        const scripts = { 'balance.py': null, 'ban.py': null };
        const result = getMergedScripts(true, scripts, {});
        expect(result).toBeNull();
    });

    it('returns null when both scripts and editedScripts are empty', () => {
        const result = getMergedScripts(true, {}, {});
        expect(result).toBeNull();
    });

    it('returns base scripts that have loaded content', () => {
        const scripts = {
            'balance.py': 'print("balance")',
            'ban.py': null, // not yet loaded
        };
        const result = getMergedScripts(true, scripts, {});
        expect(result).toEqual({ 'balance.py': 'print("balance")' });
    });

    it('merges editedScripts on top of base scripts', () => {
        const scripts = {
            'balance.py': 'original',
            'ban.py': 'ban_code',
        };
        const editedScripts = {
            'balance.py': 'modified',
        };
        const result = getMergedScripts(true, scripts, editedScripts);
        expect(result).toEqual({
            'balance.py': 'modified',
            'ban.py': 'ban_code',
        });
    });

    it('includes user-uploaded scripts not in base', () => {
        const scripts = { 'balance.py': 'code' };
        const editedScripts = { 'custom_plugin.py': 'custom_code' };
        const result = getMergedScripts(true, scripts, editedScripts);
        expect(result).toEqual({
            'balance.py': 'code',
            'custom_plugin.py': 'custom_code',
        });
    });

    it('filters out null entries from editedScripts', () => {
        const scripts = { 'a.py': 'code_a' };
        const editedScripts = { 'b.py': null };
        const result = getMergedScripts(true, scripts, editedScripts);
        expect(result).toEqual({ 'a.py': 'code_a' });
    });

    it('editedScripts null overrides base script (removes it)', () => {
        const scripts = { 'balance.py': 'original' };
        const editedScripts = { 'balance.py': null };
        const result = getMergedScripts(true, scripts, editedScripts);
        // balance.py was overridden with null → filtered out → empty → null
        expect(result).toBeNull();
    });

    it('preserves empty-string content (loaded but empty file)', () => {
        const scripts = { 'empty.py': '' };
        const result = getMergedScripts(true, scripts, {});
        expect(result).toEqual({ 'empty.py': '' });
    });

    it('handles a realistic preset-loaded scenario with mixed state', () => {
        // Simulates: preset loaded default scripts, user ticked some,
        // uploaded a custom plugin, edited one base plugin
        const scripts = {
            'balance.py': 'print("balance")',
            'ban.py': 'print("ban")',
            'essentials.py': null,       // checked but not yet fetched
            'motd.py': 'print("motd")',
        };
        const editedScripts = {
            'ban.py': 'print("ban v2")',           // user edited
            'my_custom.py': 'print("custom")',     // user uploaded
        };
        const result = getMergedScripts(true, scripts, editedScripts);
        expect(result).toEqual({
            'balance.py': 'print("balance")',
            'ban.py': 'print("ban v2")',           // edited version wins
            'motd.py': 'print("motd")',
            'my_custom.py': 'print("custom")',     // uploaded included
            // essentials.py excluded (null placeholder)
        });
    });
});
