import React, { Fragment, useState, useEffect } from 'react';
import { Dialog, DialogBackdrop, Transition, Listbox } from '@headlessui/react';
import { X, RefreshCw, ChevronDown, Check, FileText, Terminal, AlertCircle } from 'lucide-react';
import CodeMirrorEditor from '../CodeMirrorEditor';
import LogFilterControls from './LogFilterControls';
import { getFilterDescription } from './logFilterOptions';
import { chatLogLanguage } from '../../utils/chatLogLanguage';
import { fetchInstanceChatLogs, listInstanceChatLogs } from '../../services/api';

/**
 * Modal for viewing QLDS instance chat logs fetched from the remote server.
 * Uses CodeMirror in read-only mode with search functionality.
 * Supports filtering by line count, time range, or all entries, and selecting
 * archived logs. Filters apply via the Apply button (not reactively); switching
 * the selected archive file reloads immediately.
 */

function ViewChatLogsModal({ isOpen, onClose, instance }) {
    const [logs, setLogs] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Filter state
    const [filterMode, setFilterMode] = useState('lines');
    const [lineCount, setLineCount] = useState(500);
    const [timeRange, setTimeRange] = useState('1 hour ago');

    // Archived logs state
    const [availableFiles, setAvailableFiles] = useState(['chat.log']);
    const [selectedFile, setSelectedFile] = useState('chat.log');
    const [isLoadingFiles, setIsLoadingFiles] = useState(false);

    // Fetch logs when modal opens or filter changes
    const fetchLogs = async () => {
        if (!instance?.id) return;

        setIsLoading(true);
        setError(null);

        try {
            const data = await fetchInstanceChatLogs(instance.id, {
                filterMode,
                since: timeRange,
                lines: lineCount,
                filename: selectedFile
            });
            setLogs(data.logs || '-- No entries --');
        } catch (err) {
            console.error('Error fetching chat logs:', err);
            setError(err?.message || err?.error?.message || 'Failed to fetch chat logs from the remote server.');
            setLogs('');
        } finally {
            setIsLoading(false);
        }
    };

    const fetchLogFiles = async () => {
        if (!instance?.id) return;
        setIsLoadingFiles(true);
        try {
            const data = await listInstanceChatLogs(instance.id);
            if (data.files && data.files.length > 0) {
                // Filter out artifacts like "chat.log."
                const validFiles = data.files.filter(f => f === 'chat.log' || /^chat\.log\.\d+$/.test(f.trim()));

                // Sort files: chat.log first, then chat.log.1, chat.log.2, ...
                const sortedFiles = validFiles.sort((a, b) => {
                    const sa = a.trim();
                    const sb = b.trim();
                    if (sa === 'chat.log') return -1;
                    if (sb === 'chat.log') return 1;

                    // Extract number from end of string
                    const getNum = (s) => {
                        const match = s.match(/chat\.log\.(\d+)$/);
                        return match ? parseInt(match[1], 10) : Number.MAX_SAFE_INTEGER;
                    };

                    return getNum(sa) - getNum(sb);
                });
                // Keep only the top 11 (chat.log + 10 archives)
                setAvailableFiles(sortedFiles.slice(0, 11));

                // If selected file is not in the new list, reset
                if (!sortedFiles.slice(0, 11).includes(selectedFile)) {
                    setSelectedFile(sortedFiles[0]); // Default to chat.log
                }
            } else {
                setAvailableFiles(['chat.log']);
            }
        } catch (err) {
            console.error("Failed to list chat logs:", err);
            // Fallback to just chat.log
            setAvailableFiles(['chat.log']);
        } finally {
            setIsLoadingFiles(false);
        }
    };

    useEffect(() => {
        if (isOpen && instance?.id) {
            setLogs('');
            setError(null);
            fetchLogFiles();
        } else {
            // Reset state when modal closes
            setLogs('');
            setError(null);
            setSelectedFile('chat.log');
            setAvailableFiles(['chat.log']);
            setFilterMode('lines');
            setTimeRange('1 hour ago');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, instance?.id]);

    // Auto-load on open and whenever the selected archive file changes. Filter
    // changes (mode/lines/time) apply via the Apply button, matching the
    // instance-logs modal.
    useEffect(() => {
        if (isOpen && instance?.id) {
            fetchLogs();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, instance?.id, selectedFile]);

    // Scroll to bottom of logs after load
    useEffect(() => {
        if (!isLoading && logs) {
            // Small delay to ensure CodeMirror has rendered
            const timer = setTimeout(() => {
                const cmEditor = document.querySelector('.view-chat-logs-modal .cm-editor .cm-scroller');
                if (cmEditor) {
                    cmEditor.scrollTop = cmEditor.scrollHeight;
                }
            }, 100);
            return () => clearTimeout(timer);
        }
    }, [logs, isLoading]);

    return (
        <Dialog open={isOpen} as="div" className="relative z-50" onClose={onClose}>
            <DialogBackdrop transition className="fixed inset-0 bg-black/60 backdrop-blur-sm transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

                <div className="fixed inset-0 overflow-y-auto">
                    <div className="flex min-h-full items-center justify-center p-4 text-center">
                            <Dialog.Panel transition className="view-chat-logs-modal w-full transform overflow-hidden rounded-xl bg-theme-raised border border-theme-strong text-left align-middle shadow-xl transition-all flex flex-col relative transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:scale-95" style={{ height: '80vh', maxWidth: '1400px' }}>
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
                                                Chat Logs
                                            </Dialog.Title>
                                            <p className="font-mono text-xs text-theme-secondary mt-0.5">
                                                {instance?.name} <span className="text-theme-muted">•</span> Port {instance?.port} <span className="text-theme-muted">•</span> {getFilterDescription(filterMode, lineCount, timeRange)}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-3">
                                        {/* File Selection Dropdown */}
                                        <div className="relative w-48">
                                            <Listbox value={selectedFile} onChange={setSelectedFile} disabled={isLoadingFiles}>
                                                <div className="relative mt-1">
                                                    <Listbox.Button className="relative w-full cursor-default rounded-lg bg-theme-base/50 py-2 pl-3 pr-10 text-left shadow-md focus:outline-none focus-visible:border-indigo-500 focus-visible:ring-2 focus-visible:ring-white/75 focus-visible:ring-offset-2 focus-visible:ring-offset-orange-300 sm:text-sm border border-white/10">
                                                        <span className="block truncate text-theme-primary">{selectedFile}</span>
                                                        <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                                                            <ChevronDown
                                                                className="h-4 w-4 text-gray-400"
                                                                aria-hidden="true"
                                                            />
                                                        </span>
                                                    </Listbox.Button>
                                                    <Transition
                                                        as={Fragment}
                                                        leave="transition ease-in duration-100"
                                                        leaveFrom="opacity-100"
                                                        leaveTo="opacity-0"
                                                    >
                                                        <Listbox.Options className="absolute mt-1 max-h-60 w-full overflow-auto rounded-md bg-theme-bg/95 backdrop-blur-md py-1 text-base shadow-lg ring-1 ring-black/5 focus:outline-none sm:text-sm z-50 border border-white/10 scrollbar-thick">
                                                            {availableFiles.map((file, fileIdx) => (
                                                                <Listbox.Option
                                                                    key={fileIdx}
                                                                    className={({ active }) =>
                                                                        `relative cursor-default select-none py-2 pl-10 pr-4 ${active ? 'bg-theme-secondary/20 text-theme-primary' : 'text-theme-secondary'
                                                                        }`
                                                                    }
                                                                    value={file}
                                                                >
                                                                    {({ selected }) => (
                                                                        <>
                                                                            <span
                                                                                className={`block truncate ${selected ? 'font-medium text-theme-primary' : 'font-normal'
                                                                                    }`}
                                                                            >
                                                                                {file}
                                                                            </span>
                                                                            {selected ? (
                                                                                <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-amber-500">
                                                                                    <Check className="h-4 w-4" aria-hidden="true" />
                                                                                </span>
                                                                            ) : <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-theme-muted">
                                                                                <FileText className="h-4 w-4" aria-hidden="true" />
                                                                            </span>}
                                                                        </>
                                                                    )}
                                                                </Listbox.Option>
                                                            ))}
                                                        </Listbox.Options>
                                                    </Transition>
                                                </div>
                                            </Listbox>
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
                                </div>

                                {/* Filter Controls */}
                                <LogFilterControls
                                    filterMode={filterMode}
                                    setFilterMode={setFilterMode}
                                    lineCount={lineCount}
                                    setLineCount={setLineCount}
                                    timeRange={timeRange}
                                    setTimeRange={setTimeRange}
                                    onApply={fetchLogs}
                                    isLoading={isLoading}
                                />

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
                                                    language={chatLogLanguage}
                                                    height="100%"
                                                    readOnly={true}
                                                />
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </Dialog.Panel>
                    </div>
                </div>
        </Dialog>
    );
}

export default ViewChatLogsModal;
