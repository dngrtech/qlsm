/**
 * CodeMirror 6 extension for RCON console output styling.
 *
 * Provides two layers of decoration:
 *  1. Quake color codes (^0-^9) — hide markers, color following text
 *  2. Semantic coloring — timestamps, commands, Steam IDs, server info
 */

import { ViewPlugin, Decoration } from '@codemirror/view';
import { RangeSetBuilder } from '@codemirror/state';

// Quake color code → CSS color (tuned for dark backgrounds)
const QUAKE_COLORS = {
    '0': '#abb2bf', // Default/reset (maps to base text color on dark bg, NOT black)
    '1': '#ff4444', // Red
    '2': '#44ff44', // Green
    '3': '#ffff44', // Yellow
    '4': '#6688ff', // Blue (brightened)
    '5': '#44ffff', // Cyan
    '6': '#ff44ff', // Magenta
    '7': '#e0e0e0', // White
    '8': '#ff9933', // Orange
    '9': '#aaaaaa', // Gray
};

// Semantic color palette
const SEMANTIC_COLORS = {
    timestamp: '#6b7ea0',     // Muted steel blue for timestamps
    command: '#61afef',       // Bright blue for user commands  
    commandPrefix: '#98c379', // Green for the > prefix
    steamId: '#c678dd',       // Purple for Steam IDs (long numeric)
    ipAddress: '#56b6c2',     // Teal for IP:port
    serverLabel: '#e5c07b',   // Gold for labels like "map:", "num"
    separator: '#4b5263',     // Dim for separator lines (---)
};

// Patterns
const TIMESTAMP_RE = /\[[\d:]+\s*[AP]M\]/g;
const COMMAND_LINE_RE = /^(\[[\d:]+\s*[AP]M\]\s*)(> .+)$/;
const STEAMID_RE = /\b(7656\d{13,})\b/g;
const IP_PORT_RE = /\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+)\b/g;
const SEPARATOR_RE = /^(\[[\d:]+\s*[AP]M\]\s*)(---[\s\-]+.*)$/;
const QUAKE_CODE_RE = /\^([0-9])/g;

/**
 * Build all decorations for the editor view.
 */
function buildDecorations(view) {
    const builder = new RangeSetBuilder();
    const doc = view.state.doc;

    for (let i = 1; i <= doc.lines; i++) {
        const line = doc.line(i);
        const text = line.text;
        const decos = []; // Collect {from, to, deco} and sort before adding

        // --- 1. Timestamp coloring ---
        TIMESTAMP_RE.lastIndex = 0;
        let m;
        while ((m = TIMESTAMP_RE.exec(text)) !== null) {
            decos.push({
                from: line.from + m.index,
                to: line.from + m.index + m[0].length,
                deco: Decoration.mark({ attributes: { style: `color: ${SEMANTIC_COLORS.timestamp}` } }),
            });
        }

        // --- 2. Command line coloring (> prefix) ---
        const cmdMatch = COMMAND_LINE_RE.exec(text);
        if (cmdMatch) {
            const prefixStart = line.from + cmdMatch[1].length;
            // Color the "> " prefix green
            decos.push({
                from: prefixStart,
                to: prefixStart + 2,
                deco: Decoration.mark({ attributes: { style: `color: ${SEMANTIC_COLORS.commandPrefix}; font-weight: bold` } }),
            });
            // Color the command text blue
            decos.push({
                from: prefixStart + 2,
                to: line.to,
                deco: Decoration.mark({ attributes: { style: `color: ${SEMANTIC_COLORS.command}` } }),
            });
        }

        // --- 3. Separator lines ---
        const sepMatch = SEPARATOR_RE.exec(text);
        if (sepMatch) {
            decos.push({
                from: line.from + sepMatch[1].length,
                to: line.to,
                deco: Decoration.mark({ attributes: { style: `color: ${SEMANTIC_COLORS.separator}` } }),
            });
        }

        // --- 4. Steam ID coloring ---
        STEAMID_RE.lastIndex = 0;
        while ((m = STEAMID_RE.exec(text)) !== null) {
            decos.push({
                from: line.from + m.index,
                to: line.from + m.index + m[1].length,
                deco: Decoration.mark({ attributes: { style: `color: ${SEMANTIC_COLORS.steamId}` } }),
            });
        }

        // --- 5. IP:port coloring ---
        IP_PORT_RE.lastIndex = 0;
        while ((m = IP_PORT_RE.exec(text)) !== null) {
            decos.push({
                from: line.from + m.index,
                to: line.from + m.index + m[1].length,
                deco: Decoration.mark({ attributes: { style: `color: ${SEMANTIC_COLORS.ipAddress}` } }),
            });
        }

        // --- 6. Quake color codes (^0-^9) ---
        QUAKE_CODE_RE.lastIndex = 0;
        let lastColorEnd = null;
        let lastColor = null;

        while ((m = QUAKE_CODE_RE.exec(text)) !== null) {
            const from = line.from + m.index;
            const to = from + 2;

            // Close previous color span
            if (lastColor !== null && lastColorEnd !== null && lastColorEnd < from) {
                decos.push({
                    from: lastColorEnd,
                    to: from,
                    deco: Decoration.mark({ attributes: { style: `color: ${lastColor}` } }),
                });
            }

            // Hide the ^X code
            decos.push({ from, to, deco: Decoration.replace({}) });

            lastColor = QUAKE_COLORS[m[1]] || '#e0e0e0';
            lastColorEnd = to;
        }

        // Color from last code to end of line
        if (lastColor !== null && lastColorEnd !== null && lastColorEnd < line.to) {
            decos.push({
                from: lastColorEnd,
                to: line.to,
                deco: Decoration.mark({ attributes: { style: `color: ${lastColor}` } }),
            });
        }

        // Sort by start position (required by RangeSetBuilder)
        decos.sort((a, b) => a.from - b.from || a.to - b.to);
        for (const d of decos) {
            builder.add(d.from, d.to, d.deco);
        }
    }

    return builder.finish();
}

/**
 * CodeMirror ViewPlugin that provides RCON output decorations.
 */
const quakeColorPlugin = ViewPlugin.define(
    (view) => ({
        decorations: buildDecorations(view),
        update(update) {
            if (update.docChanged || update.viewportChanged) {
                this.decorations = buildDecorations(update.view);
            }
        },
    }),
    {
        decorations: (v) => v.decorations,
    }
);

export { quakeColorPlugin };
