import { EditorView } from '@codemirror/view';

/**
 * Custom CodeMirror theme for RCON/Terminal consoles.
 * Provides a dark, transparent background with specific styling for Quake Live colors.
 */
export const rconTheme = EditorView.theme({
    '&': {
        height: '100%',
        backgroundColor: 'transparent !important',
        fontSize: '13.5px',
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Source Code Pro', 'Cascadia Code', 'Consolas', monospace",
        lineHeight: '1.6',
    },
    '& .cm-scroller': {
        backgroundColor: 'transparent !important',
        overflow: 'auto',
    },
    '& .cm-content': {
        backgroundColor: 'transparent !important',
        caretColor: '#528bff',
        padding: '8px 0',
    },
    '& .cm-gutters': {
        backgroundColor: 'transparent !important',
        borderRight: '1px solid rgba(255,255,255,0.08)',
        color: 'rgba(255,255,255,0.2)',
    },
    '& .cm-gutter': {
        backgroundColor: 'transparent !important',
    },
    '& .cm-activeLineGutter': {
        backgroundColor: 'rgba(255, 255, 255, 0.05) !important',
    },
    '& .cm-activeLine': {
        backgroundColor: 'rgba(255, 255, 255, 0.03) !important',
    },
    '& .cm-line': {
        color: '#abb2bf', // Warm off-white matching oneDark foreground
    },
    // Search panel styling
    '& .cm-panels': { backgroundColor: '#1e1e1e', zIndex: '100' },
    '& .cm-panels-top': { borderBottom: '1px solid #444' },
    '& .cm-search input': {
        backgroundColor: '#333', color: '#fff', border: '1px solid #555',
        borderRadius: '3px', padding: '2px 6px'
    },
    '& .cm-search button': {
        backgroundColor: '#444', color: '#fff', border: '1px solid #555',
        borderRadius: '3px', padding: '2px 8px', marginLeft: '4px'
    },
    // Cursor styles for readOnly
    '& .cm-cursor': { borderLeftColor: '#528bff' },
    '& .cm-selectionBackground': { backgroundColor: 'rgba(82, 139, 255, 0.2) !important' },
    '&.cm-focused .cm-selectionBackground': { backgroundColor: 'rgba(82, 139, 255, 0.3) !important' },
});
