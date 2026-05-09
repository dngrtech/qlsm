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
  const [newModalMode, setNewModalMode] = useState('file');
  const [newModalTargetDir, setNewModalTargetDir] = useState('');
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [renameTarget, setRenameTarget] = useState(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [expandedFolders, setExpandedFolders] = useState(() => new Set());
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
  const serializedFiles = useMemo(() => {
    const result = serializeAdapter?.();
    return result?.files || result;
  }, [serializeAdapter]);
  const effectiveCheckedFiles = checkedFiles || adapter.checkedFiles || emptyCheckedFiles;
  const effectiveOnCheck = onCheck || adapter.setChecked || noopCheck;
  const selectedDir = dirname(selectedFile?.path || '');
  const siblingNames = useMemo(() => flatFiles
    .filter(file => dirname(file.path) === selectedDir)
    .map(file => basename(file.path)), [flatFiles, selectedDir]);
  const rootFolderNames = useMemo(() => files
    .filter(item => item.type === 'folder')
    .map(item => item.name), [files]);

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
    setExpandedFolders(new Set());
  }, [adapter.resetCount]);

  useEffect(() => {
    if (!selectedFile || !serializedFiles) return;
    if (!Object.prototype.hasOwnProperty.call(serializedFiles, selectedFile.path)) return;
    const nextContent = serializedFiles[selectedFile.path] ?? '';
    setCurrentContent(prev => (prev === nextContent ? prev : nextContent));
  }, [selectedFile, serializedFiles]);

  const expandFolder = useCallback((path) => {
    if (!path) return;
    setExpandedFolders(prev => {
      if (prev.has(path)) return prev;
      const next = new Set(prev);
      next.add(path);
      return next;
    });
  }, []);

  const handleToggleFolder = useCallback((path) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }, []);

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

  const openNewFileModal = useCallback((targetDir = '') => {
    setNewModalMode('file');
    setNewModalTargetDir(targetDir);
    setShowNewModal(true);
  }, []);

  const openNewFolderModal = useCallback(() => {
    setNewModalMode('folder');
    setNewModalTargetDir('');
    setShowNewModal(true);
  }, []);

  const handleCreateFromModal = useCallback(async (name) => {
    try {
      if (newModalMode === 'folder') {
        if (!adapter.createFolder) throw new Error('Folder creation not supported');
        await adapter.createFolder(name);
        await adapter.refreshTree?.();
        expandFolder(name);
        setShowNewModal(false);
        setActionError(null);
        return;
      }
      const targetDir = newModalTargetDir || dirname(selectedFile?.path || '');
      const path = joinPath(targetDir, name);
      const template = capabilities.newFileTemplate?.(path) ?? '';
      await adapter.writeContent(path, template);
      await adapter.refreshTree?.();
      if (checkable && isCheckablePath(path) && onCheck && onCheck !== adapter.setChecked) {
        await onCheck(path, true);
      }
      if (targetDir) expandFolder(targetDir);
      setShowNewModal(false);
      setActionError(null);
      pendingLocalPathsRef.current.add(path);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Create failed'));
    }
  }, [adapter, capabilities, checkable, expandFolder, newModalMode, newModalTargetDir, onCheck, selectedFile]);

  const handleUpload = useCallback(async (file, targetDir = null) => {
    try {
      const dir = targetDir ?? dirname(selectedFile?.path || '');
      const result = await adapter.upload(file, dir);
      const path = result?.path || joinPath(dir, file.name);
      if (checkable && isCheckablePath(path) && onCheck && onCheck !== adapter.setChecked) {
        await onCheck(path, true);
      }
      if (dir) expandFolder(dir);
      setActionError(null);
      pendingLocalPathsRef.current.add(path);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Upload failed'));
    }
  }, [adapter, checkable, expandFolder, onCheck, selectedFile]);

  const openRenameModal = useCallback((item) => {
    setRenameTarget({ kind: item.type, path: item.path });
    setShowRenameModal(true);
  }, []);

  const handleRename = useCallback(async (newName) => {
    if (!renameTarget) return;
    const oldPath = renameTarget.path;
    try {
      if (renameTarget.kind === 'folder') {
        if (!adapter.renameFolder) throw new Error('Folder rename not supported');
        await adapter.renameFolder(oldPath, newName);
        setEditedContent(prev => {
          const next = {};
          for (const [path, content] of Object.entries(prev)) {
            if (path === oldPath || path.startsWith(oldPath + '/')) {
              next[newName + path.slice(oldPath.length)] = content;
            } else {
              next[path] = content;
            }
          }
          return next;
        });
        await adapter.refreshTree?.();
        setExpandedFolders(prev => {
          const next = new Set();
          for (const p of prev) {
            if (p === oldPath) next.add(newName);
            else if (p.startsWith(oldPath + '/')) next.add(newName + p.slice(oldPath.length));
            else next.add(p);
          }
          return next;
        });
      } else {
        const newPath = joinPath(dirname(oldPath), newName);
        const context = oldPath.endsWith('.so') ? binaryContext : null;
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
        if (selectedFile?.path === oldPath) {
          setSelectedFile({ ...selectedFile, name: newName, path: newPath });
        }
      }
      setShowRenameModal(false);
      setRenameTarget(null);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Rename failed'));
    }
  }, [adapter, binaryContext, checkable, effectiveCheckedFiles, effectiveOnCheck, renameTarget, selectedFile]);

  const requestDelete = useCallback((item) => {
    if (item.type === 'folder') {
      const fileCount = flattenFiles(item.children || []).length;
      setDeleteTarget({ kind: 'folder', item, fileCount });
    } else {
      setDeleteTarget({ kind: 'file', item, fileCount: 0 });
    }
    setConfirmDeleteOpen(true);
  }, []);

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      if (deleteTarget.kind === 'folder') {
        if (!adapter.deleteFolder) throw new Error('Folder delete not supported');
        await adapter.deleteFolder(deleteTarget.item.path);
        await adapter.refreshTree?.();
        setExpandedFolders(prev => {
          const next = new Set(prev);
          next.delete(deleteTarget.item.path);
          return next;
        });
      } else {
        await adapter.deleteFile(deleteTarget.item.path);
        if (checkable && effectiveCheckedFiles.has(deleteTarget.item.path)) {
          await effectiveOnCheck(deleteTarget.item.path, false);
        }
        setEditedContent(prev => {
          const next = { ...prev };
          delete next[deleteTarget.item.path];
          return next;
        });
        pendingRemovedPathsRef.current.add(deleteTarget.item.path);
        if (selectedFile?.path === deleteTarget.item.path) {
          setSelectedFile(null);
          setCurrentContent('');
          setBinaryDescription('');
        }
      }
      setConfirmDeleteOpen(false);
      setDeleteTarget(null);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Delete failed'));
    }
  }, [adapter, checkable, deleteTarget, effectiveCheckedFiles, effectiveOnCheck, selectedFile]);

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

  const handleDownload = useCallback((item) => {
    const content = editedContent[item.path] ?? currentContent;
    const blob = new Blob([content || ''], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = basename(item.path);
    a.click();
    URL.revokeObjectURL(url);
  }, [editedContent, currentContent]);

  const handleCopyContent = useCallback(async (item) => {
    const content = editedContent[item.path] ?? (item.path === selectedFile?.path ? currentContent : await adapter.readContent(item.path));
    const { copyToClipboard } = await import('../../utils/clipboard');
    await copyToClipboard(content || '');
  }, [adapter, currentContent, editedContent, selectedFile]);

  const handleNewFileInFolder = useCallback((folderItem) => {
    openNewFileModal(folderItem.path);
  }, [openNewFileModal]);

  const handleUploadToFolder = useCallback((folderItem, file) => {
    handleUpload(file, folderItem.path);
  }, [handleUpload]);

  const language = selectedFile && getLanguageForFile ? getLanguageForFile(selectedFile.path) : null;
  const linterSource = selectedFile && getLinterSourceForFile
    ? getLinterSourceForFile(selectedFile.path)
    : null;

  const renameTargetItem = renameTarget
    ? flatFiles.find(f => f.path === renameTarget.path) || files.find(i => i.type === 'folder' && i.path === renameTarget.path)
    : null;
  const renameTargetSiblings = renameTarget?.kind === 'folder'
    ? rootFolderNames
    : flatFiles
        .filter(f => dirname(f.path) === dirname(renameTarget?.path || ''))
        .map(f => basename(f.path));

  return {
    actionError,
    binaryDescription,
    confirmDeleteOpen,
    contentLoading,
    currentContent,
    deleteTarget,
    effectiveCheckedFiles,
    effectiveOnCheck,
    expandedFolders,
    files,
    flushEdits,
    handleContentChange,
    handleCreateFromModal,
    handleDelete,
    handleDownload,
    handleCopyContent,
    handleNewFileInFolder,
    handleRename,
    handleReplace,
    handleSaveBinaryDescription,
    handleSelectFile,
    handleToggleFolder,
    handleUpload,
    handleUploadToFolder,
    isDirty: selectedFile ? editedContent[selectedFile.path] !== undefined : false,
    language,
    linterSource,
    newModalMode,
    newModalTargetDir,
    openNewFileModal,
    openNewFolderModal,
    openRenameModal,
    renameTarget,
    renameTargetItem,
    renameTargetSiblings,
    requestDelete,
    rootFolderNames,
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
