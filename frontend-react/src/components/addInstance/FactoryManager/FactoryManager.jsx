import React, { useState, useEffect, useCallback, useRef } from 'react';
import { getFactoryTree, getFactoryContent } from '../../../services/api';
import FileTree from '../ScriptManager/FileTree';
import CodeMirrorEditor from '../../CodeMirrorEditor';
import { Loader2, File as FileIcon, Maximize, Copy } from 'lucide-react';
import NewFactoryModal from './NewFactoryModal';
import FullScreenConfigEditorModal from '../../config/FullScreenConfigEditorModal';
import { copyToClipboard } from '../../../utils/clipboard';

// Using a simple JSON syntax highlighter might be better if factories are JSON-like,
// but they are usually JSON-ish or proprietary. Python or just generic config is often fine.
// If it's pure JSON, we should use json(). 
// QL factories are typically JSON objects.
import { json } from '@codemirror/lang-json';

function FactoryManager({
    factories, // Map of filename -> content (initial/saved state)
    onFactoriesChange, // Function to update parent state with NEW map of filename -> content
    isNewInstance,
    preset,
    hostId,
    instanceId,
    checkable = true,
}) {
    const [serverFiles, setServerFiles] = useState([]);
    const [selectedFiles, setSelectedFiles] = useState(new Set()); // Set of enabled filenames

    // Snapshot of selected files at mount time — used only for sort order.
    // Files checked by the user mid-session won't jump to the top until the
    // component remounts (e.g. after saving a preset or reopening the modal).
    const [pinnedFiles] = useState(() => new Set(factories ? Object.keys(factories) : []));
    const [activeFile, setActiveFile] = useState(null); // File currently being edited
    const [editedContent, setEditedContent] = useState({}); // Map of filename -> content (unsaved edits)
    const [isLoadingTree, setIsLoadingTree] = useState(false);
    const [isLoadingContent, setIsLoadingContent] = useState(false);
    const [isNewFactoryModalOpen, setIsNewFactoryModalOpen] = useState(false);

    // Full Screen Editor State
    const [isFullScreenEditorOpen, setIsFullScreenEditorOpen] = useState(false);

    // Caching and Race Condition Guards
    const fetchedCache = useRef({});
    const loadingPathRef = useRef(null);
    const fileInputRef = useRef(null);

    // Initialize selected files based on passed props
    useEffect(() => {
        if (factories) {
            setSelectedFiles(new Set(Object.keys(factories)));
            // Also prime the cache/edited content with initial values if provided?
            // Actually factories prop is the *result* to be saved.
            // If we are editing an existing instance, factories prop has current state.
            // We should treat `factories` prop as the source of truth for "Enabled files + their content"
        }
    }, [factories]);

    // Fetch file tree
    const fetchTree = useCallback(async () => {
        setIsLoadingTree(true);
        try {
            // params: preset, host, instanceId
            const params = {};
            if (preset) params.preset = preset;
            if (hostId) params.host = hostId; // API expects 'host' (ID or name? API calls it 'host', assumes ID often or name depending on route)
            // Wait, api.js getFactoryTree expects: { preset, host, instanceId }
            // host_routes usually take ID, but instance_routes/factory_routes logical helpers might expect name if it's building path?
            // factory_routes.py uses request.args.get('host'). _get_factories_base_path uses it.
            // If we look at instance_routes: os.path.join('configs', host_name, ...)
            // So passed 'host' should probably be the NAME if it's new instance?
            // But we might only have ID.
            // Actually `getFactoryTree` in backend: 
            // if (host and instance_id) -> path = configs/HOST/ID/factories
            // So checks purely based on args.

            // For NEW Instance: we rely on 'preset' (e.g. default).
            // For EDIT Instance: we rely on 'host' (name) and 'instanceId'.

            const tree = await getFactoryTree({
                preset: preset,
                // For existing instance, we need host NAME. Parent should probably pass hostName or we handle it?
                // Let's assume parent passes relevant props.
                host: !isNewInstance ? (hostId) : undefined, // If hostId is actually name? Logic check needed.
                // The API seems to treat 'host' as the directory segment name usually.
                instanceId: instanceId
            });

            setServerFiles(tree || []);
        } catch (error) {
            console.error("Failed to load factory list", error);
        } finally {
            setIsLoadingTree(false);
        }
    }, [preset, hostId, instanceId, isNewInstance]);

    useEffect(() => {
        fetchTree();
    }, [fetchTree]);

    // Merge server files with locally added (unsaved) files from factories prop
    // This logic ensures that if we create a file, it remains in the list even if we remount
    // (e.g. switch tabs) because the parent holds the 'factories' state.
    const availableFiles = React.useMemo(() => {
        // Start with server files
        const merged = [...(serverFiles || [])];
        const serverFileNames = new Set(merged.map(f => f.name));

        // Add files from factories prop that aren't on the server yet
        if (factories) {
            Object.keys(factories).forEach(name => {
                if (!serverFileNames.has(name)) {
                    merged.push({ name: name, type: 'file', path: name, isUnsaved: true });
                }
            });
        }

        return merged.sort((a, b) => {
            if (checkable) {
                const aPinned = pinnedFiles.has(a.name);
                const bPinned = pinnedFiles.has(b.name);
                if (aPinned && !bPinned) return -1;
                if (!aPinned && bPinned) return 1;
            }
            return a.name.localeCompare(b.name);
        });
    }, [serverFiles, factories, pinnedFiles, checkable]);

    // Handle file selection (enable/disable)
    // When checking a file, fetch its content and show it in the editor
    const toggleFileSelection = async (filename) => {
        const newSelected = new Set(selectedFiles);
        const isAdding = !newSelected.has(filename);

        if (isAdding) {
            newSelected.add(filename);

            // Show loading state while fetching
            setActiveFile(filename);
            setIsLoadingContent(true);

            // Check if we need to fetch content for this file
            const hasContent =
                editedContent[filename] !== undefined ||
                fetchedCache.current[filename] !== undefined ||
                (factories && factories[filename] !== undefined);

            if (!hasContent) {
                // Fetch content for this file
                try {
                    const data = await getFactoryContent(filename, {
                        preset: preset,
                        host: !isNewInstance ? hostId : undefined,
                        instanceId: instanceId
                    });
                    const content = data.content || '';
                    fetchedCache.current[filename] = content;
                } catch (error) {
                    console.error(`Failed to fetch content for ${filename}:`, error);
                    // Set empty content so we at least have something
                    fetchedCache.current[filename] = '';
                }
            }

            setIsLoadingContent(false);
        } else {
            newSelected.delete(filename);
            // If we're unchecking the active file, clear the editor
            if (activeFile === filename) {
                setActiveFile(null);
            }
        }

        setSelectedFiles(newSelected);

        // Trigger update to parent
        updateParent(newSelected, editedContent);
    };

    // Update parent with current state
    // Parent expects: Map<filename, content>
    // Since we now fetch content when checking files (in toggleFileSelection),
    // we should always have content for selected files.
    const updateParent = (selected, edited) => {
        const result = {};
        selected.forEach(filename => {
            // Priority: edited content > cached content > factories prop
            if (edited[filename] !== undefined) {
                result[filename] = edited[filename];
            } else if (fetchedCache.current[filename] !== undefined) {
                result[filename] = fetchedCache.current[filename];
            } else if (factories && factories[filename] !== undefined) {
                result[filename] = factories[filename];
            }
            // If we don't have content, don't include in result
            // (this shouldn't happen since toggleFileSelection fetches on check)
        });
        onFactoriesChange(result);
    };


    // Handle file activation (edit)
    const handleActivateFile = async (filename) => {
        if (activeFile === filename) return;
        setActiveFile(filename);

        // Check if we have content (edited or cached)
        if (editedContent[filename] !== undefined) {
            // We have unsaved edits, no need to fetch
            return;
        }

        if (fetchedCache.current[filename] !== undefined) {
            // We have cached content
            return;
        }

        // Check if parent already provided content (e.g. preserved unsaved edits)
        if (factories && factories[filename] !== undefined) {
            return;
        }

        // Need to fetch
        setIsLoadingContent(true);
        loadingPathRef.current = filename; // Mark this as the target

        try {
            const data = await getFactoryContent(filename, {
                preset: preset,
                host: !isNewInstance ? hostId : undefined,
                instanceId: instanceId
            });

            if (loadingPathRef.current !== filename) {
                return;
            }

            const content = data.content || '';
            fetchedCache.current[filename] = content;

            // Force re-render/update?
            // Setting state to trigger re-render is usually enough, but here we just updated cache.
            // We need to ensure the Editor sees this.
            // The Editor reads `getCurrentContent`.
            // We need to trigger a state update to force re-read.
            setIsLoadingContent(false); // This triggers render

        } catch (error) {
            console.error(`Failed to load content for ${filename}`, error);
            if (loadingPathRef.current === filename) {
                setIsLoadingContent(false);
            }
        }
    };

    const getCurrentContent = () => {
        if (!activeFile) return '';

        // 1. User edits
        if (editedContent[activeFile] !== undefined) {
            return editedContent[activeFile];
        }
        // 2. Cache
        if (fetchedCache.current[activeFile] !== undefined) {
            return fetchedCache.current[activeFile];
        }
        // 3. Fallback (e.g. initial `factories` prop if applicable)
        if (factories && factories[activeFile]) {
            // Update cache for consistency
            fetchedCache.current[activeFile] = factories[activeFile];
            return factories[activeFile];
        }

        return '';
    };

    const handleEditorChange = (newVal) => {
        if (!activeFile) return;

        // IGNORE EMPTY UPDATE RACE CONDITION
        // When switching activeFile, CodeMirror might fire an onChange with empty string 
        // before the new content is loaded, potentially wiping out state.
        // Logic: If new content is empty, AND we previously had content (or are waiting for it),
        // and we just switched? 
        // A simpler check used in ScriptManager:
        // if (newVal === '' && currentContent === '' && !isActuallyEmptyFile) ...
        // But simplest is: if we are loading content, ignore changes?
        if (isLoadingContent) return;

        // Use a ref to track if this is a "real" user edit vs a mount effect?
        // CodeMirror 6 usually behaves better, but safe to check.

        setEditedContent(prev => {
            const next = { ...prev, [activeFile]: newVal };
            // Defer parent update slightly or do it now?
            // Doing it now updates the 'factories' prop passed back to us?
            // No, `onFactoriesChange` updates parent state, parent re-renders us.
            // We should break that loop or ensure stable props.
            // Usually safe to just update local state and notify parent.
            return next;
        });

        // Notify parent immediately (debouncing might be better but let's stick to simple first)
        // We need the *latest* editedContent, which we just computed.
        const updatedEdited = { ...editedContent, [activeFile]: newVal };
        updateParent(selectedFiles, updatedEdited);
    };

    const handleCreateFile = (name) => {
        // Add to selected
        const newSelected = new Set(selectedFiles);
        newSelected.add(name);
        setSelectedFiles(newSelected);

        // Set content to empty and activate
        setEditedContent(prev => ({ ...prev, [name]: '{\n  \n}' })); // Default JSON-ish empty
        fetchedCache.current[name] = '{\n  \n}';

        setActiveFile(name);

        // Update parent
        updateParent(newSelected, { ...editedContent, [name]: '{\n  \n}' });
    };

    const handleUploadClick = () => {
        fileInputRef.current?.click();
    };

    const handleFileUpload = async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;

        // Validate extension
        if (!file.name.endsWith('.factories')) {
            alert('Only .factories files can be uploaded');
            return;
        }

        // Read file content
        const content = await file.text();
        const name = file.name;

        // Add to selected
        const newSelected = new Set(selectedFiles);
        newSelected.add(name);
        setSelectedFiles(newSelected);

        // Set content
        setEditedContent(prev => ({ ...prev, [name]: content }));
        fetchedCache.current[name] = content;

        // Activate
        setActiveFile(name);

        // Update parent
        updateParent(newSelected, { ...editedContent, [name]: content });

        // Reset input
        event.target.value = '';
    };

    const handleCopyContent = () => {
        const content = getCurrentContent();
        if (content) {
            copyToClipboard(content);
        }
    };

    const handleExpandEditor = () => {
        setIsFullScreenEditorOpen(true);
    };

    const handleCloseFullScreenEditor = () => {
        setIsFullScreenEditorOpen(false);
    };

    const handleSaveFullScreenEditor = (newContent) => {
        handleEditorChange(newContent);
        setIsFullScreenEditorOpen(false);
    };


    return (
        <div className="flex gap-4 flex-1 min-h-0">
            {/* Sidebar (File Tree) */}
            <div className="w-64 h-full flex-shrink-0">
                <FileTree
                    files={availableFiles}
                    selectedPath={activeFile}
                    onSelectFile={handleActivateFile}
                    onNewFile={() => setIsNewFactoryModalOpen(true)}
                    onUploadFile={handleUploadClick}
                    isLoading={isLoadingTree}
                    checkable={checkable}
                    checkedFiles={selectedFiles}
                    onCheck={toggleFileSelection}
                />
            </div>

            {/* Main Editor Area */}
            {!activeFile ? (
                <div className="flex-1 flex items-center justify-center bg-[var(--surface-base)] rounded-lg border border-[var(--surface-border)]">
                    <p className="text-[var(--text-muted)] text-sm">Select a factory file to view or edit.</p>
                </div>
            ) : (
                <div className="flex-1 flex flex-col min-w-0">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-2 flex-shrink-0">
                        <div className="flex items-center gap-2 min-w-0">
                            <FileIcon size={16} className="text-[var(--accent-primary)] flex-shrink-0" />
                            <span className="text-sm font-medium text-[var(--text-primary)] truncate">{activeFile}</span>
                            {editedContent[activeFile] !== undefined && (
                                <span className="text-[var(--accent-warning)] ml-1">●</span>
                            )}
                        </div>
                        <div className="flex items-center gap-1">
                            <button
                                type="button"
                                onClick={handleCopyContent}
                                className="p-1 hover:bg-[var(--surface-elevated)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                                title="Copy to clipboard"
                            >
                                <Copy size={14} />
                            </button>
                            <button
                                type="button"
                                onClick={handleExpandEditor}
                                className="p-1 hover:bg-[var(--surface-elevated)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                                title="Expand editor"
                                aria-label="Expand editor"
                            >
                                <Maximize size={14} />
                            </button>
                        </div>
                    </div>

                    {/* Editor Container */}
                    <div className="flex-1 min-h-0 border border-[var(--surface-border)] rounded-lg overflow-hidden relative">
                        {isLoadingContent && (
                            <div className="absolute inset-0 z-10 bg-[var(--surface-base)]/50 backdrop-blur-[1px] flex items-center justify-center">
                                <Loader2 className="animate-spin text-indigo-500" />
                            </div>
                        )}
                        <CodeMirrorEditor
                            value={getCurrentContent()}
                            onChange={handleEditorChange}
                            height="100%"
                            language={json()} // Assuming JSON for factories
                            isActiveTab={true}
                        />
                    </div>
                </div>
            )}

            <NewFactoryModal
                isOpen={isNewFactoryModalOpen}
                onClose={() => setIsNewFactoryModalOpen(false)}
                onCreate={handleCreateFile}
                existingFiles={availableFiles}
            />

            <FullScreenConfigEditorModal
                isOpen={isFullScreenEditorOpen}
                onClose={handleCloseFullScreenEditor}
                onSave={handleSaveFullScreenEditor}
                fileName={activeFile}
                initialContent={getCurrentContent()}
                language={json()}
            />

            {/* Hidden file input for upload */}
            <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                accept=".factories"
                className="hidden"
            />
        </div>
    );
}

export default FactoryManager;
