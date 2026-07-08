import { List, Clock, DatabaseZap } from 'lucide-react';

/**
 * Shared filter option definitions for the instance-log and chat-log modals so
 * both surfaces expose identical filter modes, line counts, and time windows.
 */

// Filter mode options
export const FILTER_MODES = [
    { value: 'lines', label: 'Last N Lines', icon: List },
    { value: 'time', label: 'Time Range', icon: Clock },
    { value: 'all', label: 'All', icon: DatabaseZap },
];

// Line count options
export const LINE_OPTIONS = [100, 250, 500, 1000, 2500];

// Time range options (values are passed to `date -d`/journalctl `--since`)
export const TIME_OPTIONS = [
    { value: '15 minutes ago', label: '15 min' },
    { value: '30 minutes ago', label: '30 min' },
    { value: '1 hour ago', label: '1 hour' },
    { value: '3 hours ago', label: '3 hours' },
    { value: '12 hours ago', label: '12 hours' },
    { value: '24 hours ago', label: '24 hours' },
];

// Human-readable description of the active filter (shown in modal headers)
export function getFilterDescription(filterMode, lineCount, timeRange) {
    if (filterMode === 'lines') return `Last ${lineCount} lines`;
    if (filterMode === 'all') return 'All entries';
    const option = TIME_OPTIONS.find(o => o.value === timeRange);
    return option ? `Last ${option.label}` : timeRange;
}
