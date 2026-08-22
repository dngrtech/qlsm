import React, { Fragment, useState, useEffect, useRef } from 'react';
import { Dialog, DialogBackdrop, Transition, Listbox } from '@headlessui/react';
import { X, RefreshCw, ChevronDown, Check, FileText, Terminal, AlertCircle } from 'lucide-react';
import CodeMirrorEditor from '../CodeMirrorEditor';
import LogFilterControls from './LogFilterControls';
import { getFilterDescription } from './logFilterOptions';
import { minqlxLogLanguage } from '../../utils/minqlxLogLanguage';
import { fetchInstanceMinqlxLogs, listInstanceMinqlxLogs } from '../../services/api';
import { runtimeLogFilename } from '../../constants/runtimes';

/**
 * Groups the live (unrotated) log file first, then any rotated siblings
 * ordered by ascending numeric suffix. Works for any runtime's log filename --
 * the backend already scopes the file list to the instance's runtime and
 * rejects anything else, so there is no filename to pattern-match here.
 */
function sortLogFiles(files) {
    const rotationSuffix = (name) => {
        const match = name.match(/\.(\d+)$/);
        return match ? parseInt(match[1], 10) : null;
    };
    const live = files.filter((f) => rotationSuffix(f) === null);
    const rotated = files
        .filter((f) => rotationSuffix(f) !== null)
        .sort((a, b) => rotationSuffix(a) - rotationSuffix(b));
    return [...live, ...rotated];
}

/**
 * Modal for viewing QLDS instance MinQLX logs fetched from the remote server.
 * Uses CodeMirror in read-only mode with search functionality.
 * Supports filtering by line count or all entries and selecting rotated logs.
 */

function ViewMinqlxLogsModal({ isOpen, onClose, instance }) {
    const [logs, setLogs] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);

    // Filter state. MinQLX logs intentionally omit time mode because entries only
    // include HH:MM:SS, not a full date.
    const [filterMode, setFilterMode] = useState('lines');
    const [lineCount, setLineCount] = useState(500);
    const [timeRange, setTimeRange] = useState('1 hour ago');

    // Rotated logs state. selectedFile starts null and is seeded from the
    // instance's own runtime when the modal opens (see the effect below) --
    // the file listing response is the source of truth once it arrives.
    const [availableFiles, setAvailableFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(null);
    const [isLoadingFiles, setIsLoadingFiles] = useState(false);

    // Tracks the filename the log-content effect below has already fetched.
    // Seeding selectedFile and firing its fetch happen in separate effects
    // (see the open effect), so on the very first render of an open the fetch
    // effect still closes over the pre-seed `null` and must not act on it --
    // this dedupes that stale pass instead of sending a request for it, while
    // still firing exactly once for the real seeded value once it commits.
    const lastFetchedFileRef = useRef(null);

    const fetchLogs = async () => {
        if (!instance?.id) return;

        setIsLoading(true);
        setError(null);

        try {
            const data = await fetchInstanceMinqlxLogs(instance.id, {
                filterMode,
                lines: lineCount,
                filename: selectedFile
            });
            setLogs(data.logs || '-- No entries --');
        } catch (err) {
            console.error('Error fetching MinQLX logs:', err);
            setError(err?.message || err?.error?.message || 'Failed to fetch MinQLX logs from the remote server.');
            setLogs('');
        } finally {
            setIsLoading(false);
        }
    };

    // currentSelection is passed explicitly rather than read from the
    // `selectedFile` state closure: this is called synchronously right after
    // seeding that state in the effect below, before React has re-rendered,
    // so the closure would otherwise still see the previous (stale) value and
    // needlessly override an already-correct seed once the list resolves.
    const fetchLogFiles = async (currentSelection) => {
        if (!instance?.id) return;
        setIsLoadingFiles(true);
        try {
            const data = await listInstanceMinqlxLogs(instance.id);
            const files = Array.isArray(data.files) ? data.files : [];
            if (files.length > 0) {
                // The backend already scoped this list to the instance's
                // runtime and validated every entry -- just order it.
                const sortedFiles = sortLogFiles(files).slice(0, 11);
                setAvailableFiles(sortedFiles);

                if (!sortedFiles.includes(currentSelection)) {
                    setSelectedFile(sortedFiles[0]);
                }
            } else {
                setAvailableFiles([]);
            }
        } catch (err) {
            console.error('Failed to list MinQLX logs:', err);
            setAvailableFiles([]);
        } finally {
            setIsLoadingFiles(false);
        }
    };

    useEffect(() => {
        if (isOpen && instance?.id) {
            setLogs('');
            setError(null);
            // A fresh open (or a switch to a different instance without closing
            // first) must always fetch at least once, even if the resolved
            // filename happens to match whatever was last fetched.
            lastFetchedFileRef.current = null;
            // Seed the initial selection from the instance's own runtime so the
            // fetch effect below asks for a filename that runtime accepts. The
            // file listing response corrects this if it turns out to be wrong.
            const seed = runtimeLogFilename(instance.host_runtime);
            setSelectedFile(seed);
            fetchLogFiles(seed);
        } else {
            setLogs('');
            setError(null);
            setSelectedFile(null);
            setAvailableFiles([]);
            setFilterMode('lines');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, instance?.id]);

    useEffect(() => {
        // selectedFile is null on the render that seeds it (the seed itself is
        // set in the effect above, in the same commit, so this effect's closure
        // still sees the pre-seed value here) -- wait for the follow-up render
        // where it actually reflects a filename. Once it does, fetch only if
        // that filename hasn't already been fetched for this open.
        if (!isOpen || !instance?.id || selectedFile === null) return;
        if (lastFetchedFileRef.current === selectedFile) return;
        lastFetchedFileRef.current = selectedFile;
        fetchLogs();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, instance?.id, selectedFile]);

    useEffect(() => {
        if (!isLoading && logs) {
            const timer = setTimeout(() => {
                const cmEditor = document.querySelector('.view-minqlx-logs-modal .cm-editor .cm-scroller');
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
                            <Dialog.Panel transition className="view-minqlx-logs-modal w-full transform overflow-hidden rounded-xl bg-theme-raised border border-theme-strong text-left align-middle shadow-xl transition-all flex flex-col relative transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:scale-95" style={{ height: '80vh', maxWidth: '1400px' }}>
                                <div className="accent-line-top" />

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
                                                MinQLX Logs
                                            </Dialog.Title>
                                            <p className="font-mono text-xs text-theme-secondary mt-0.5">
                                                {instance?.name} <span className="text-theme-muted">•</span> Port {instance?.port} <span className="text-theme-muted">•</span> {getFilterDescription(filterMode, lineCount, timeRange)}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-3">
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

                                <LogFilterControls
                                    filterMode={filterMode}
                                    setFilterMode={setFilterMode}
                                    lineCount={lineCount}
                                    setLineCount={setLineCount}
                                    timeRange={timeRange}
                                    setTimeRange={setTimeRange}
                                    onApply={fetchLogs}
                                    isLoading={isLoading}
                                    allowedModes={['lines', 'all']}
                                />

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
                                                    onChange={() => { }}
                                                    language={minqlxLogLanguage}
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

export default ViewMinqlxLogsModal;
