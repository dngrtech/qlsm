/**
 * RconConsoleModal - RCON Console Modal Component
 * 
 * Provides a terminal-style interface for sending RCON commands
 * to a QLDS instance with optional real-time game events.
 * Uses CodeMirror 6 with a custom Quake color extension for output display.
 */

import React, { useState, useRef, useEffect, useCallback, useMemo, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, Terminal, Wifi, WifiOff, RefreshCw, Send } from 'lucide-react';
import { useRconSocket } from '../hooks/useRconSocket';

// CodeMirror imports
import { EditorState } from '@codemirror/state';
import {
    EditorView,
    lineNumbers,
    highlightActiveLine,
    highlightActiveLineGutter,
    drawSelection,
} from '@codemirror/view';
import { search, searchKeymap } from '@codemirror/search';
import { keymap } from '@codemirror/view';
import { defaultKeymap } from '@codemirror/commands';
import { Prec } from '@codemirror/state';
import { oneDark } from '@codemirror/theme-one-dark';

// Quake color code extension
import { quakeColorPlugin } from '../utils/quakeColorExtension';
import { rconTheme } from '../utils/rconTheme';


/**
 * Strip Quake color codes from text (for plain text operations).
 */
function stripColorCodes(text) {
    return text.replace(/\^[0-9]/g, '');
}


function RconConsoleModal({ isOpen, onClose, instance }) {
    const [inputValue, setInputValue] = useState('');
    const [commandHistory, setCommandHistory] = useState([]);
    const [historyIndex, setHistoryIndex] = useState(-1);
    const [showStats, setShowStats] = useState(true);

    const inputRef = useRef(null);
    const editorContainerRef = useRef(null);
    const editorViewRef = useRef(null);

    const handleNewMessage = useCallback((msg) => {
        if (!editorViewRef.current) return;

        const prefix = `[${msg.timestamp}] `;
        let formatted = '';

        if (msg.type === 'command') {
            formatted = `${prefix}> ${msg.content}`;
        } else if (msg.type === 'error') {
            formatted = `${prefix}^1ERROR: ${msg.content}`;
        } else if (msg.type === 'stats') {
            formatted = `${prefix}^8${msg.content}`;
        } else {
            // response — preserve color codes as-is
            formatted = `${prefix}${msg.content}`;
        }

        const view = editorViewRef.current;
        const currentDocLength = view.state.doc.length;
        const insertText = currentDocLength === 0 ? formatted : `\n${formatted}`;

        const changes = [{ from: currentDocLength, insert: insertText }];

        // Keep document from growing infinitely (e.g., truncate if > 1000 lines)
        const newLinesAdded = insertText.split('\n').length - 1;
        const projectedTotalLines = view.state.doc.lines + newLinesAdded;

        if (projectedTotalLines > 1000) {
            const linesToRemove = projectedTotalLines - 1000;
            const lineEndPos = view.state.doc.line(linesToRemove + 1).from;
            changes.push({ from: 0, to: lineEndPos, insert: "" });
        }

        view.dispatch({ changes });

        // Auto-scroll
        requestAnimationFrame(() => {
            if (editorViewRef.current) {
                const scroller = editorViewRef.current.scrollDOM;
                scroller.scrollTop = scroller.scrollHeight;
            }
        });
    }, []);

    const {
        connected,
        status,
        sendCommand,
        subscribeStats,
        unsubscribeStats,
    } = useRconSocket(instance, isOpen, handleNewMessage);

    // No longer parsing full output text in React rendering cycle


    // CodeMirror extensions (stable reference)
    const editorExtensions = useMemo(() => [
        lineNumbers(),
        highlightActiveLine(),
        highlightActiveLineGutter(),
        drawSelection(),
        search(),
        Prec.highest(keymap.of([
            ...searchKeymap,
            ...defaultKeymap,
        ])),
        oneDark,
        rconTheme,
        quakeColorPlugin,
        EditorState.readOnly.of(true),
        EditorView.editable.of(true), // Allow selection/search even in readOnly
    ], []);

    // Initialize/reinitialize CodeMirror when modal opens
    useEffect(() => {
        if (!isOpen || !editorContainerRef.current || editorViewRef.current) return;

        const state = EditorState.create({
            doc: '',
            extensions: editorExtensions,
        });

        editorViewRef.current = new EditorView({
            state,
            parent: editorContainerRef.current,
        });

        return () => {
            if (editorViewRef.current) {
                editorViewRef.current.destroy();
                editorViewRef.current = null;
            }
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, editorExtensions]);

    // Progressive append sync is now handled directly inside the useRconSocket callback

    // Clear CodeMirror when modal is artificially closed/opened or instance changes to clear buffer
    useEffect(() => {
        if (isOpen && editorViewRef.current) {
            const view = editorViewRef.current;
            if (view.state.doc.length > 0) {
                view.dispatch({
                    changes: { from: 0, to: view.state.doc.length, insert: '' }
                });
            }
        }
    }, [isOpen, instance?.id]);

    // Focus input when modal opens - use a slightly longer timeout to ensure transition is complete
    useEffect(() => {
        if (isOpen && inputRef.current) {
            // fast initial attempt
            inputRef.current.focus();

            // backup attempt after transition (300ms duration)
            const timer = setTimeout(() => {
                inputRef.current?.focus();
            }, 350);

            return () => clearTimeout(timer);
        }
    }, [isOpen]);


    // Handle stats checkbox toggle
    useEffect(() => {
        if (connected) {
            if (showStats) {
                subscribeStats();
            } else {
                unsubscribeStats();
            }
        }
    }, [showStats, connected, subscribeStats, unsubscribeStats]);

    const handleSubmit = useCallback((e) => {
        e.preventDefault();
        const cmd = inputValue.trim();
        if (!cmd) return;

        sendCommand(cmd);
        setCommandHistory(prev => [cmd, ...prev.slice(0, 49)]); // Keep last 50
        setHistoryIndex(-1);
        setInputValue('');
    }, [inputValue, sendCommand]);

    const handleKeyDown = useCallback((e) => {
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (historyIndex < commandHistory.length - 1) {
                const newIndex = historyIndex + 1;
                setHistoryIndex(newIndex);
                setInputValue(commandHistory[newIndex]);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex > 0) {
                const newIndex = historyIndex - 1;
                setHistoryIndex(newIndex);
                setInputValue(commandHistory[newIndex]);
            } else if (historyIndex === 0) {
                setHistoryIndex(-1);
                setInputValue('');
            }
        }
    }, [historyIndex, commandHistory]);

    const getStatusStyles = () => {
        switch (status) {
            case 'connected':
                return { color: 'var(--accent-primary)', icon: Wifi };
            case 'connecting':
                return { color: 'var(--accent-warning)', icon: RefreshCw };
            case 'error':
                return { color: 'var(--accent-danger)', icon: WifiOff };
            default:
                return { color: 'var(--text-muted)', icon: WifiOff };
        }
    };

    const statusStyles = getStatusStyles();
    const StatusIcon = statusStyles.icon;

    return (
        <Transition appear show={isOpen} as={Fragment}>
            <Dialog
                as="div"
                className="relative z-50"
                onClose={onClose}
                initialFocus={inputRef}
            >
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
                            <Dialog.Panel
                                className="rcon-console-modal w-full transform overflow-hidden rounded-xl bg-theme-raised border border-theme-strong text-left align-middle shadow-xl transition-all flex flex-col relative"
                                style={{ height: '70vh', maxWidth: '1000px' }}
                            >
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
                                                RCON Console
                                            </Dialog.Title>
                                            <p className="font-mono text-xs text-theme-secondary mt-0.5">
                                                {instance?.name} <span className="text-theme-muted">•</span> Port {instance?.zmq_rcon_port}
                                                <span className="text-theme-muted"> •</span>
                                                <span className="inline-flex items-center gap-1 ml-1" style={{ color: statusStyles.color }}>
                                                    <StatusIcon className={`h-3 w-3 ${status === 'connecting' ? 'animate-spin' : ''}`} strokeWidth={2} />
                                                    {status}
                                                </span>
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={onClose}
                                        className="logs-modal-close-btn"
                                    >
                                        <X className="h-5 w-5" strokeWidth={2} />
                                    </button>
                                </div>

                                {/* Stats Checkbox */}
                                <div className="px-6 py-3 border-b border-theme bg-theme-elevated flex-shrink-0">
                                    <label className="flex items-center gap-2 text-sm text-theme-secondary cursor-pointer select-none">
                                        <input
                                            type="checkbox"
                                            checked={showStats}
                                            onChange={(e) => setShowStats(e.target.checked)}
                                            className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0"
                                        />
                                        Show real-time game events
                                    </label>
                                </div>

                                {/* CodeMirror Output Area */}
                                <div className="flex-1 overflow-hidden bg-theme-base p-4">
                                    <div
                                        ref={editorContainerRef}
                                        className="h-full rounded-lg border-2 border-theme-strong overflow-hidden [&_.cm-editor]:h-full"
                                        style={{ background: 'rgba(0,0,0,0.4)' }}
                                    />
                                </div>

                                {/* Input Area */}
                                <form
                                    onSubmit={handleSubmit}
                                    className="flex items-center gap-3 px-6 py-4 border-t border-theme bg-theme-elevated flex-shrink-0"
                                >
                                    <span className="font-mono text-sm font-semibold" style={{ color: 'var(--accent-primary)' }}>
                                        RCON&gt;
                                    </span>
                                    <input
                                        ref={inputRef}
                                        type="text"
                                        value={inputValue}
                                        onChange={(e) => setInputValue(e.target.value)}
                                        onKeyDown={handleKeyDown}
                                        placeholder={connected ? 'Enter command...' : 'Connecting...'}
                                        className="flex-1 bg-transparent border-none outline-none font-mono text-sm text-theme-primary placeholder-theme-muted"
                                        autoComplete="off"
                                        spellCheck="false"
                                    />
                                    <button
                                        type="submit"
                                        disabled={!connected || !inputValue.trim()}
                                        className="btn btn-primary gap-2"
                                    >
                                        <Send size={14} />
                                        Send
                                    </button>
                                </form>
                            </Dialog.Panel>
                        </Transition.Child>
                    </div>
                </div>
            </Dialog>
        </Transition>
    );
}

export default RconConsoleModal;
