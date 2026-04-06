import React, { Fragment, useState, useEffect, useRef } from 'react';
import { Dialog, Transition, Listbox } from '@headlessui/react';
import { X, RefreshCw, Download, Search, Settings, ChevronDown, Check, FileText, Terminal, AlertCircle } from 'lucide-react';
import CodeMirrorEditor from '../CodeMirrorEditor';
import { chatLogLanguage } from '../../utils/chatLogLanguage';
import { fetchInstanceChatLogs, listInstanceChatLogs } from '../../services/api';

/**
 * Modal for viewing QLDS instance chat logs fetched from the remote server.
 * Uses CodeMirror in read-only mode with search functionality.
 * Supports filtering by line count and selecting archived logs.
 */

// Line count options
const LINE_OPTIONS = [100, 250, 500, 1000, 2500];

function ViewChatLogsModal({ isOpen, onClose, instance }) {
    const [logs, setLogs] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Filter state
    const [lineCount, setLineCount] = useState(500);
    const [searchTerm, setSearchTerm] = useState('');
    const [searchMatches, setSearchMatches] = useState([]);
    const [currentMatchIndex, setCurrentMatchIndex] = useState(-1);

    // Archived logs state
    const [availableFiles, setAvailableFiles] = useState(['chat.log']);
    const [selectedFile, setSelectedFile] = useState('chat.log');
    const [isLoadingFiles, setIsLoadingFiles] = useState(false);

    const editorRef = useRef(null);

    // Fetch logs when modal opens or filter changes
    const fetchLogs = async () => {
        if (!instance?.id) return;

        setIsLoading(true);
        setError(null);

        try {
            const data = await fetchInstanceChatLogs(instance.id, {
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
            setSearchTerm('');
            setSearchMatches([]);
            setCurrentMatchIndex(-1);
            fetchLogFiles();
        } else {
            // Reset state when modal closes
            setLogs('');
            setError(null);
            setSelectedFile('chat.log');
            setAvailableFiles(['chat.log']);
        }
    }, [isOpen, instance?.id]);

    // Fetch logs when selectedFile, lineCount changes (and isOpen is true)
    useEffect(() => {
        if (isOpen && instance?.id) {
            fetchLogs();
        }
    }, [isOpen, instance?.id, lineCount, selectedFile]);

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
                            <Dialog.Panel className="view-chat-logs-modal w-full transform overflow-hidden rounded-xl bg-theme-raised border border-theme-strong text-left align-middle shadow-xl transition-all flex flex-col relative" style={{ height: '80vh', maxWidth: '1400px' }}>
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
                                            <p className="font-mono text-xs text-theme-secondary mt-0.5 flex items-center">
                                                {instance?.name}
                                                <span className="text-theme-muted mx-2">|</span>
                                                <span className="text-theme-muted font-mono">{instance?.port}</span>
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

                                        {/* Line Count Selector using Listbox */}
                                        <div className="relative w-32">
                                            {/* (Simple line count buttons as before, or loop if you prefer Listbox here too) */}
                                            {/* Keeping the buttons as they are nice and quick access */}
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

                                {/* Filter Controls (kept line count here for now) */}
                                <div className="px-6 py-3 border-b border-theme bg-theme-elevated flex-shrink-0">
                                    <div className="flex flex-wrap items-center gap-4">
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
                                                    language={chatLogLanguage}
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

export default ViewChatLogsModal;
