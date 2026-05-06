import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  basename,
  dirname,
  flattenFiles,
  getErrorMessage,
  getFileType,
  getInitialSelectableFile,
  isCheckablePath,
  joinPath,
} from './fileManagerUtils';

const EMPTY_TREE = [];

function filterExcludedFiles(items = [], excludedPaths = new Set()) {
  if (!excludedPaths.size) return items;
  return items.reduce((acc, item) => {
    if (item.type === 'folder') {
      acc.push({
        ...item,
        children: filterExcludedFiles(item.children || [], excludedPaths),
      });
      return acc;
    }
    if (!excludedPaths.has(item.path)) acc.push(item);
    return acc;
  }, []);
}

export function useFileManagerController({
  adapter,
  capabilities,
  checkable,
  checkedFiles,
  onCheck,
  defaultSelectedPath,
  getLanguageForFile,
  getLinterSourceForFile,
  getBinaryMeta,
  saveBinaryMeta,
  binaryContext,
}) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [currentContent, setCurrentContent] = useState('');
  const [editedContent, setEditedContent] = useState({});
  const [contentLoading, setContentLoading] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [binaryDescription, setBinaryDescription] = useState('');
  const [actionError, setActionError] = useState(null);
  const pendingLocalPathsRef = useRef(new Set());
  const pendingRemovedPathsRef = useRef(new Set());
  const prevResetCountRef = useRef(adapter.resetCount ?? 0);
  const emptyCheckedFiles = useMemo(() => new Set(), []);
  const noopCheck = useCallback(() => undefined, []);

  const files = adapter.tree || EMPTY_TREE;
  const flatFiles = useMemo(() => flattenFiles(files), [files]);
  const serializeAdapter = adapter.serialize;
  const serializedFiles = useMemo(() => serializeAdapter?.(), [serializeAdapter]);
  const effectiveCheckedFiles = checkedFiles || adapter.checkedFiles || emptyCheckedFiles;
  const effectiveOnCheck = onCheck || adapter.setChecked || noopCheck;
  const selectedDir = dirname(selectedFile?.path || '');
  const siblingNames = useMemo(() => flatFiles
    .filter(file => dirname(file.path) === selectedDir)
    .map(file => basename(file.path)), [flatFiles, selectedDir]);

  const flushEdits = useCallback(async () => {
    for (const [path, content] of Object.entries(editedContent)) {
      await adapter.writeContent(path, content);
    }
    setEditedContent({});
  }, [adapter, editedContent]);

  useEffect(() => {
    const current = adapter.resetCount ?? 0;
    if (current === prevResetCountRef.current) return;
    prevResetCountRef.current = current;
    setEditedContent({});
    setSelectedFile(null);
    setCurrentContent('');
    setBinaryDescription('');
  }, [adapter.resetCount]);

  useEffect(() => {
    if (!selectedFile || !serializedFiles) return;
    if (!Object.prototype.hasOwnProperty.call(serializedFiles, selectedFile.path)) return;
    const nextContent = serializedFiles[selectedFile.path] ?? '';
    setCurrentContent(prev => (prev === nextContent ? prev : nextContent));
  }, [selectedFile, serializedFiles]);

  const handleSelectFile = useCallback(async (item) => {
    if (!item || item.type === 'folder') return;
    setSelectedFile(item);
    setActionError(null);
    const fileType = item.file_type || getFileType(item.name);
    if (fileType === 'binary') {
      setCurrentContent('');
      setBinaryDescription('');
      if (!getBinaryMeta) return;
      try {
        const result = await getBinaryMeta(item.path);
        setBinaryDescription(result?.description ?? '');
      } catch {
        setBinaryDescription('');
      }
      return;
    }
    if (editedContent[item.path] !== undefined) {
      setCurrentContent(editedContent[item.path]);
      return;
    }
    setContentLoading(true);
    try {
      const content = await adapter.readContent(item.path);
      setCurrentContent(content || '');
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to read file'));
      setCurrentContent('');
    } finally {
      setContentLoading(false);
    }
  }, [adapter, editedContent, getBinaryMeta]);

  useEffect(() => {
    if (adapter.loading) return;
    for (const path of pendingLocalPathsRef.current) {
      if (flatFiles.some(file => file.path === path)) {
        pendingLocalPathsRef.current.delete(path);
      }
    }
    for (const path of pendingRemovedPathsRef.current) {
      if (!flatFiles.some(file => file.path === path)) {
        pendingRemovedPathsRef.current.delete(path);
      }
    }

    const removedPaths = pendingRemovedPathsRef.current;
    const selectedExists = selectedFile && (
      pendingLocalPathsRef.current.has(selectedFile.path) ||
      flatFiles.some(file => file.path === selectedFile.path && !removedPaths.has(file.path))
    );
    if (selectedExists) return;

    const selectableFiles = filterExcludedFiles(files, removedPaths);
    const nextSelection = getInitialSelectableFile(selectableFiles, {
      checkable,
      checkedFiles: effectiveCheckedFiles,
      defaultSelectedPath,
    });

    if (nextSelection) {
      handleSelectFile(nextSelection);
      return;
    }

    if (selectedFile) setSelectedFile(null);
    setCurrentContent('');
    setBinaryDescription('');
  }, [
    adapter.loading,
    checkable,
    defaultSelectedPath,
    effectiveCheckedFiles,
    files,
    flatFiles,
    handleSelectFile,
    selectedFile,
  ]);

  const updateContent = useCallback((path, content) => {
    setEditedContent(prev => ({ ...prev, [path]: content }));
    if (selectedFile?.path === path) setCurrentContent(content);
  }, [selectedFile]);

  const handleContentChange = useCallback((value) => {
    setCurrentContent(value);
    if (!selectedFile) return;
    setEditedContent(prev => ({ ...prev, [selectedFile.path]: value }));
    if (adapter.serialize) adapter.writeContent(selectedFile.path, value).catch(() => {});
  }, [adapter, selectedFile]);

  const selectPath = useCallback(async (path, fallback = null) => {
    const item = flatFiles.find(file => file.path === path) || fallback;
    if (item) await handleSelectFile(item);
  }, [flatFiles, handleSelectFile]);

  const handleCreate = useCallback(async (name) => {
    const path = joinPath(selectedDir, name);
    const template = capabilities.newFileTemplate?.(path) ?? '';
    try {
      await adapter.writeContent(path, template);
      await adapter.refreshTree?.();
      if (checkable && isCheckablePath(path) && onCheck && onCheck !== adapter.setChecked) {
        await onCheck(path, true);
      }
      setShowNewModal(false);
      setActionError(null);
      pendingLocalPathsRef.current.add(path);
      setSelectedFile({ name, path, type: 'file', file_type: getFileType(name) });
      setCurrentContent(template);
      setEditedContent(prev => ({ ...prev, [path]: template }));
    } catch (err) {
      setActionError(getErrorMessage(err, 'Create failed'));
    }
  }, [adapter, capabilities, checkable, onCheck, selectedDir]);

  const handleUpload = useCallback(async (file) => {
    try {
      const result = await adapter.upload(file, selectedDir);
      const path = result?.path || joinPath(selectedDir, file.name);
      if (checkable && isCheckablePath(path) && onCheck && onCheck !== adapter.setChecked) {
        await onCheck(path, true);
      }
      const fileType = getFileType(path);
      setActionError(null);
      pendingLocalPathsRef.current.add(path);
      setSelectedFile({
        name: basename(path),
        path,
        type: 'file',
        file_type: fileType,
      });
      if (fileType === 'binary') {
        setCurrentContent('');
        setBinaryDescription('');
      } else {
        const content = await file.text();
        setCurrentContent(content);
        setEditedContent(prev => ({ ...prev, [path]: content }));
      }
    } catch (err) {
      setActionError(getErrorMessage(err, 'Upload failed'));
    }
  }, [adapter, checkable, onCheck, selectedDir]);

  const handleRename = useCallback(async (newName) => {
    if (!selectedFile) return;
    const oldPath = selectedFile.path;
    const newPath = joinPath(dirname(oldPath), newName);
    const context = oldPath.endsWith('.so') ? binaryContext : null;
    try {
      await adapter.renameFile(oldPath, newPath, context);
      await adapter.refreshTree?.();
      if (checkable && effectiveCheckedFiles.has(oldPath)) {
        await effectiveOnCheck(oldPath, false);
        await effectiveOnCheck(newPath, true);
      }
      setEditedContent(prev => {
        if (prev[oldPath] === undefined) return prev;
        const next = { ...prev, [newPath]: prev[oldPath] };
        delete next[oldPath];
        return next;
      });
      setSelectedFile({ ...selectedFile, name: newName, path: newPath });
      setShowRenameModal(false);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Rename failed'));
    }
  }, [adapter, binaryContext, checkable, effectiveCheckedFiles, effectiveOnCheck, selectedFile]);

  const handleDelete = useCallback(async () => {
    if (!selectedFile) return;
    try {
      await adapter.deleteFile(selectedFile.path);
      if (checkable && effectiveCheckedFiles.has(selectedFile.path)) {
        await effectiveOnCheck(selectedFile.path, false);
      }
      setEditedContent(prev => {
        const next = { ...prev };
        delete next[selectedFile.path];
        return next;
      });
      pendingLocalPathsRef.current.delete(selectedFile.path);
      pendingRemovedPathsRef.current.add(selectedFile.path);
      setSelectedFile(null);
      setCurrentContent('');
      setBinaryDescription('');
    } catch (err) {
      setActionError(getErrorMessage(err, 'Delete failed'));
    }
  }, [adapter, checkable, effectiveCheckedFiles, effectiveOnCheck, selectedFile]);

  const handleReplace = useCallback(async (file) => {
    if (!selectedFile) return;
    try {
      const dir = dirname(selectedFile.path);
      const result = await adapter.upload(file, dir);
      const uploadedPath = result?.path || joinPath(dir, file.name);
      if (uploadedPath !== selectedFile.path) await adapter.deleteFile(selectedFile.path);
      await adapter.refreshTree?.();
      await selectPath(uploadedPath, {
        ...selectedFile,
        name: basename(uploadedPath),
        path: uploadedPath,
      });
    } catch (err) {
      setActionError(getErrorMessage(err, 'Replace failed'));
    }
  }, [adapter, selectPath, selectedFile]);

  const handleSaveBinaryDescription = useCallback(async (description) => {
    if (!selectedFile || !saveBinaryMeta) return;
    try {
      const result = await saveBinaryMeta(selectedFile.path, description);
      setBinaryDescription(result?.description ?? description);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Description save failed'));
    }
  }, [saveBinaryMeta, selectedFile]);

  const language = selectedFile && getLanguageForFile ? getLanguageForFile(selectedFile.path) : null;
  const linterSource = selectedFile && getLinterSourceForFile
    ? getLinterSourceForFile(selectedFile.path)
    : null;

  return {
    actionError,
    binaryDescription,
    confirmDeleteOpen,
    contentLoading,
    currentContent,
    effectiveCheckedFiles,
    effectiveOnCheck,
    files,
    flushEdits,
    handleContentChange,
    handleCreate,
    handleDelete,
    handleRename,
    handleReplace,
    handleSaveBinaryDescription,
    handleSelectFile,
    handleUpload,
    isDirty: selectedFile ? editedContent[selectedFile.path] !== undefined : false,
    language,
    linterSource,
    selectedFile,
    setConfirmDeleteOpen,
    setShowNewModal,
    setShowRenameModal,
    showNewModal,
    showRenameModal,
    siblingNames,
    updateContent,
  };
}
