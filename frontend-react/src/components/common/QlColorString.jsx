import React, { useMemo } from 'react';

// Quake 3 / Quake Live color codes
const QL_COLORS = {
    '0': '#000000', // Black
    '1': '#ff0000', // Red
    '2': '#00ff00', // Green
    '3': '#ffff00', // Yellow
    '4': '#3b82f6', // Light Blue
    '5': '#00ffff', // Cyan
    '6': '#ff00ff', // Magenta
    '7': '#ffffff', // White
    '8': '#ff7f00', // Orange
    '9': '#7f7f7f', // Grey
};

export default function QlColorString({ text, className = '' }) {
    const segments = useMemo(() => {
        if (!text) return [];

        const result = [];
        let currentColor = ''; // Default color inherited from parent

        // Split by the caret symbol
        const parts = text.split('^');

        // The first part never has a color code before it
        if (parts[0]) {
            result.push({ text: parts[0], color: currentColor });
        }

        for (let i = 1; i < parts.length; i++) {
            const part = parts[i];

            if (part.length === 0) {
                // If it was ^^, it might just be a literal caret depending on the engine, 
                // but usually QL just skips it. We'll add a literal caret.
                if (i < parts.length - 1) {
                    result.push({ text: '^', color: currentColor });
                }
                continue;
            }

            const code = part.charAt(0);

            if (QL_COLORS[code]) {
                currentColor = QL_COLORS[code];
                const textPortion = part.substring(1);
                if (textPortion) {
                    result.push({ text: textPortion, color: currentColor });
                }
            } else {
                // Not a valid color code, treat the ^ and the character as literal text
                result.push({ text: '^' + part, color: currentColor });
            }
        }

        return result;
    }, [text]);

    if (!text) return null;

    return (
        <span className={className}>
            {segments.map((segment, index) => (
                <span
                    key={index}
                    style={segment.color ? { color: segment.color } : {}}
                >
                    {segment.text}
                </span>
            ))}
        </span>
    );
}
