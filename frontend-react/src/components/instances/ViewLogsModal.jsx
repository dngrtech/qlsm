import React, { useState, useEffect, Fragment } from 'react';
import { Dialog, Transition, RadioGroup } from '@headlessui/react';
import { X, RefreshCw, Terminal, AlertCircle, Clock, List } from 'lucide-react';
import CodeMirrorEditor from '../CodeMirrorEditor';
import { logLanguage } from '../../utils/logLanguage';
import { fetchInstanceRemoteLogs } from '../../services/api';

/**
 * Modal for viewing QLDS instance logs fetched from the remote server.
 * Uses CodeMirror in read-only mode with search functionality.
 * Supports filtering by time range or line count.
 */

// Filter mode options
const FILTER_MODES = [
    { value: 'lines', label: 'Last N Lines', icon: List },
    { value: 'time', label: 'Time Range', icon: Clock },
];

// Line count options
const LINE_OPTIONS = [100, 250, 500, 1000, 2500];

// Time range options
const TIME_OPTIONS = [
    { value: '15 minutes ago', label: '15 min' },
    { value: '30 minutes ago', label: '30 min' },
    { value: '1 hour ago', label: '1 hour' },
    { value: '3 hours ago', label: '3 hours' },
    { value: '12 hours ago', label: '12 hours' },
    { value: '24 hours ago', label: '24 hours' },
];

function ViewLogsModal({ isOpen, onClose, instance }) {
    const [logs, setLogs] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Filter state
    const [filterMode, setFilterMode] = useState('lines');
    const [lineCount, setLineCount] = useState(500);
    const [timeRange, setTimeRange] = useState('1 hour ago');

    // Fetch logs when modal opens or filter changes
    const fetchLogs = async () => {
        if (!instance?.id) return;

        setIsLoading(true);
        setError(null);

        try {
            const data = await fetchInstanceRemoteLogs(instance.id, {
                filterMode,
                since: timeRange,
                lines: lineCount,
            });
            setLogs(data.logs || '-- No entries --');
        } catch (err) {
            console.error('Error fetching remote logs:', err);
            setError(err?.message || err?.error?.message || 'Failed to fetch logs from the remote server.');
            setLogs('');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen && instance?.id) {
            fetchLogs();
        }
        // Reset state when modal closes
        if (!isOpen) {
            setLogs('');
            setError(null);
        }
    }, [isOpen, instance?.id]);

    // Scroll to bottom of logs after load
    useEffect(() => {
        if (!isLoading && logs) {
            // Small delay to ensure CodeMirror has rendered
            const timer = setTimeout(() => {
                const cmEditor = document.querySelector('.view-logs-modal .cm-editor .cm-scroller');
                if (cmEditor) {
                    cmEditor.scrollTop = cmEditor.scrollHeight;
                }
            }, 100);
            return () => clearTimeout(timer);
        }
    }, [logs, isLoading]);

    // Get current filter description
    const getFilterDescription = () => {
        if (filterMode === 'lines') {
            return `Last ${lineCount} lines`;
        } else {
            const option = TIME_OPTIONS.find(o => o.value === timeRange);
            return option ? `Last ${option.label}` : timeRange;
        }
    };

    return (
        <Transition appear show={isOpen} as={Fragment}>
            <Dialog as="div" className="relative z-50" onClose={onClose}>
                <Transition.Child
                    as={Fragment}
                    enter="ease-out duration-300"
                    enterFrom="opacity-0"
                    enterTo="opacity-100"
                    leave="ease-in duration-200"
                    leaveFrom="opacity-100"
                    leaveTo="opacity-0"
                >
                    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
                </Transition.Child>

                <div className="fixed inset-0 overflow-y-auto">
                    <div className="flex min-h-full items-center justify-center p-4 text-center">
                        <Transition.Child
                            as={Fragment}
                            enter="ease-out duration-300"
                            enterFrom="opacity-0 scale-95"
                            enterTo="opacity-100 scale-100"
                            leave="ease-in duration-200"
                            leaveFrom="opacity-100 scale-100"
                            leaveTo="opacity-0 scale-95"
                        >
                            <Dialog.Panel className="view-logs-modal w-full transform overflow-hidden rounded-xl bg-theme-raised border border-theme-strong text-left align-middle shadow-xl transition-all flex flex-col relative" style={{ height: '80vh', maxWidth: '1400px' }}>
                                {/* Accent line at top */}
                                <div className="accent-line-top" />

                                {/* Header */}
                                <div className="flex items-center justify-between px-6 py-4 border-b border-theme flex-shrink-0 relative">
                                    <div className="flex items-center gap-3">
                                        <div className="logs-modal-icon-wrapper">
                                            <div className="logs-modal-icon-glow" />
                                            <Terminal className="logs-modal-icon" strokeWidth={2.5} />
                                        </div>
                                        <div>
                                            <Dialog.Title
                                                as="h3"
                                                className="font-display text-lg font-bold tracking-wide text-theme-primary uppercase"
                                            >
                                                Instance Logs
                                            </Dialog.Title>
                                            <p className="font-mono text-xs text-theme-secondary mt-0.5">
                                                {instance?.name} <span className="text-theme-muted">•</span> Port {instance?.port} <span className="text-theme-muted">•</span> {getFilterDescription()}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={fetchLogs}
                                            disabled={isLoading}
                                            className="logs-modal-refresh-btn"
                                        >
                                            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} strokeWidth={2} />
                                            <span>Refresh</span>
                                        </button>
                                        <button
                                            onClick={onClose}
                                            className="logs-modal-close-btn"
                                        >
                                            <X className="h-5 w-5" strokeWidth={2} />
                                        </button>
                                    </div>
                                </div>

                                {/* Filter Controls */}
                                <div className="px-6 py-3 border-b border-theme bg-theme-elevated flex-shrink-0">
                                    <div className="flex flex-wrap items-center gap-4">
                                        {/* Filter Mode Toggle */}
                                        <div className="flex items-center gap-2">
                                            <span className="label-tech">Filter by:</span>
                                            <RadioGroup value={filterMode} onChange={setFilterMode} className="flex gap-1">
                                                {FILTER_MODES.map((mode) => (
                                                    <RadioGroup.Option
                                                        key={mode.value}
                                                        value={mode.value}
                                                        className={({ checked }) =>
                                                            `logs-modal-filter-option ${checked ? 'logs-modal-filter-option-active' : ''}`
                                                        }
                                                    >
                                                        <mode.icon className="h-3.5 w-3.5" strokeWidth={2} />
                                                        {mode.label}
                                                    </RadioGroup.Option>
                                                ))}
                                            </RadioGroup>
                                        </div>

                                        {/* Line Count Options */}
                                        {filterMode === 'lines' && (
                                            <div className="flex items-center gap-2">
                                                <span className="label-tech">Lines:</span>
                                                <div className="flex gap-1">
                                                    {LINE_OPTIONS.map((count) => (
                                                        <button
                                                            key={count}
                                                            onClick={() => setLineCount(count)}
                                                            className={`logs-modal-value-btn ${lineCount === count ? 'logs-modal-value-btn-active' : ''}`}
                                                        >
                                                            {count}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Time Range Options */}
                                        {filterMode === 'time' && (
                                            <div className="flex items-center gap-2">
                                                <span className="label-tech">Time:</span>
                                                <div className="flex gap-1">
                                                    {TIME_OPTIONS.map((option) => (
                                                        <button
                                                            key={option.value}
                                                            onClick={() => setTimeRange(option.value)}
                                                            className={`logs-modal-value-btn ${timeRange === option.value ? 'logs-modal-value-btn-active' : ''}`}
                                                        >
                                                            {option.label}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Apply Button */}
                                        <button
                                            onClick={fetchLogs}
                                            disabled={isLoading}
                                            className="logs-modal-apply-btn"
                                        >
                                            Apply
                                        </button>
                                    </div>
                                </div>

                                {/* Content */}
                                <div className="flex-1 p-4 overflow-hidden bg-theme-base">
                                    {isLoading ? (
                                        <div className="logs-modal-loading-state">
                                            <div className="logs-modal-spinner-wrapper">
                                                <RefreshCw className="logs-modal-spinner" strokeWidth={2} />
                                            </div>
                                            <p className="font-mono text-sm text-theme-secondary uppercase tracking-wide">Fetching logs from remote server...</p>
                                        </div>
                                    ) : error ? (
                                        <div className="logs-modal-error-state">
                                            <AlertCircle className="h-10 w-10 mb-4" style={{ color: 'var(--accent-danger)' }} strokeWidth={2} />
                                            <p className="font-display text-lg font-bold uppercase tracking-wide" style={{ color: 'var(--accent-danger)' }}>Error Fetching Logs</p>
                                            <p className="text-sm text-theme-secondary mt-2 max-w-md text-center">{error}</p>
                                            <button
                                                onClick={fetchLogs}
                                                className="logs-modal-retry-btn"
                                            >
                                                Try Again
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="h-full flex flex-col">
                                            <div className="flex items-center gap-2 mb-3 px-2">
                                                <div className="logs-modal-tip-icon">
                                                    <Terminal className="h-3 w-3" strokeWidth={2.5} />
                                                </div>
                                                <p className="font-mono text-xs text-theme-secondary">
                                                    Press <kbd className="logs-modal-kbd">Ctrl+F</kbd> to search
                                                </p>
                                            </div>
                                            <div className="flex-1 border-2 border-theme-strong rounded-lg overflow-hidden logs-modal-editor-container">
                                                <CodeMirrorEditor
                                                    value={logs}
                                                    onChange={() => { }} // No-op for read-only
                                                    language={logLanguage}
                                                    height="100%"
                                                    readOnly={true}
                                                />
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </Dialog.Panel>
                        </Transition.Child>
                    </div>
                </div>
            </Dialog>
        </Transition>
    );
}

export default ViewLogsModal;
