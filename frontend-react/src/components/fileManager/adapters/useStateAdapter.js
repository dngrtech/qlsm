import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { rewritePathPrefix } from '../fileManagerUtils';

function getExtension(path) {
  const dotIndex = path.lastIndexOf('.');
  return dotIndex === -1 ? '' : path.slice(dotIndex).toLowerCase();
}

function validatePath(path, allowedExtensions) {
  const segments = path.split('/');
  if (segments.length > 2) {
    throw new Error(`Path too deep: ${path}`);
  }
  for (const segment of segments) {
    if (!segment || segment.includes('\\') || segment.includes('..') || segment.startsWith('.')) {
      throw new Error(`Invalid name: ${segment}`);
    }
  }
  const ext = getExtension(path);
  if (!allowedExtensions.includes(ext)) {
    throw new Error(`Disallowed extension ${ext}`);
  }
}

function validateFolderName(name, reservedFolderNames = []) {
  if (!name || typeof name !== 'string') throw new Error('Folder name required');
  if (!/^[A-Za-z0-9._-]+$/.test(name)) throw new Error(`Invalid folder name: ${name}`);
  if (name.length > 64) throw new Error('Folder name too long');
  if (reservedFolderNames.map(n => n.toLowerCase()).includes(name.toLowerCase())) {
    throw new Error(`Reserved folder name: ${name}`);
  }
}

function normalizeTreeItem(item) {
  const path = item.path || item.name;
  return {
    ...item,
    name: item.name || path,
    path,
    type: item.type || 'file',
    file_type: item.file_type || 'text',
  };
}

function buildHierarchicalTree(flatItems, folders, protectedSet) {
  const rootFiles = [];
  const folderChildren = new Map();
  for (const item of flatItems) {
    if (item.path.includes('/')) {
      const [top, ...rest] = item.path.split('/');
      if (!folderChildren.has(top)) folderChildren.set(top, []);
      folderChildren.get(top).push({
        ...item,
        name: rest.join('/'),
        path: item.path,
        protected: protectedSet.has(item.path),
      });
    } else {
      rootFiles.push({ ...item, protected: protectedSet.has(item.path) });
    }
  }
  const folderItems = [];
  const allFolderNames = new Set([...folders, ...folderChildren.keys()]);
  for (const name of allFolderNames) {
    folderItems.push({
      name,
      path: name,
      type: 'folder',
      children: (folderChildren.get(name) || []).sort((a, b) => a.name.localeCompare(b.name)),
    });
  }
  return [...folderItems, ...rootFiles].sort((a, b) => {
    if (a.type === 'folder' && b.type !== 'folder') return -1;
    if (a.type !== 'folder' && b.type === 'folder') return 1;
    return a.name.localeCompare(b.name);
  });
}

export function useStateAdapter({
  initialFiles = {},
  initialFolders = [],
  allowedExtensions = [],
  protectedFiles = [],
  reservedFolderNames = [],
  serverTree = null,
  readServerContent = null,
  onFilesChange = null,
} = {}) {
  const [files, setFiles] = useState(initialFiles);
  const [folders, setFolders] = useState(() => new Set(initialFolders));
  const [deletedPaths, setDeletedPaths] = useState(() => new Set());
  const [resetCount, setResetCount] = useState(0);
  const initialFilesRef = useRef(initialFiles);
  const initialFoldersRef = useRef(new Set(initialFolders));
  const protectedSet = useMemo(() => new Set(protectedFiles), [protectedFiles]);

  useEffect(() => {
    onFilesChange?.(files);
  }, [files, onFilesChange]);

  const tree = useMemo(() => {
    const byPath = new Map();
    for (const item of serverTree || []) {
      const normalized = normalizeTreeItem(item);
      if (!deletedPaths.has(normalized.path)) {
        byPath.set(normalized.path, normalized);
      }
    }
    for (const path of Object.keys(files)) {
      const existing = byPath.get(path) || {};
      byPath.set(path, {
        ...existing,
        name: existing.name || path.split('/').pop(),
        path,
        type: 'file',
        file_type: existing.file_type || 'text',
      });
    }
    return buildHierarchicalTree([...byPath.values()], folders, protectedSet);
  }, [files, folders, serverTree, deletedPaths, protectedSet]);

  const checkedFiles = useMemo(() => new Set(Object.keys(files)), [files]);

  const readContent = useCallback(async (path) => {
    if (files[path] !== undefined) return files[path] ?? '';
    if (readServerContent) return await readServerContent(path);
    return '';
  }, [files, readServerContent]);

  const writeContent = useCallback(async (path, content) => {
    validatePath(path, allowedExtensions);
    setFiles(prev => ({ ...prev, [path]: content ?? '' }));
    setDeletedPaths(prev => {
      const next = new Set(prev);
      next.delete(path);
      return next;
    });
  }, [allowedExtensions]);

  const upload = useCallback(async (file, targetDir = '') => {
    const targetPath = targetDir ? `${targetDir}/${file.name}` : file.name;
    validatePath(targetPath, allowedExtensions);
    const content = await file.text();
    setFiles(prev => ({ ...prev, [targetPath]: content }));
    setDeletedPaths(prev => {
      const next = new Set(prev);
      next.delete(targetPath);
      return next;
    });
    return { path: targetPath, content };
  }, [allowedExtensions]);

  const deleteFile = useCallback(async (path) => {
    if (protectedSet.has(path)) {
      throw new Error(`Cannot delete protected file: ${path}`);
    }
    setFiles(prev => {
      const next = { ...prev };
      delete next[path];
      return next;
    });
    setDeletedPaths(prev => new Set(prev).add(path));
  }, [protectedSet]);

  const setChecked = useCallback(async (path, checked) => {
    if (checked) {
      if (files[path] !== undefined) return;
      const content = readServerContent ? await readServerContent(path) : '';
      setFiles(prev => prev[path] !== undefined ? prev : { ...prev, [path]: content || '' });
      return;
    }
    if (protectedSet.has(path)) {
      throw new Error(`Cannot uncheck protected file: ${path}`);
    }
    setFiles(prev => {
      const next = { ...prev };
      delete next[path];
      return next;
    });
  }, [files, readServerContent, protectedSet]);

  const renameFile = useCallback(async (oldPath, newPath) => {
    if (protectedSet.has(oldPath)) {
      throw new Error(`Cannot rename protected file: ${oldPath}`);
    }
    validatePath(newPath, allowedExtensions);
    if (Object.prototype.hasOwnProperty.call(files, newPath)) {
      throw new Error(`Target exists: ${newPath}`);
    }
    const content = files[oldPath] !== undefined ? files[oldPath] : await readContent(oldPath);
    setFiles(prev => {
      const next = { ...prev };
      delete next[oldPath];
      next[newPath] = content ?? '';
      return next;
    });
    setDeletedPaths(prev => {
      const next = new Set(prev);
      next.add(oldPath);
      next.delete(newPath);
      return next;
    });
  }, [allowedExtensions, protectedSet, readContent, files]);

  const createFolder = useCallback((name) => {
    validateFolderName(name, reservedFolderNames);
    if (folders.has(name)) throw new Error(`Folder already exists: ${name}`);
    setFolders(prev => {
      const next = new Set(prev);
      next.add(name);
      return next;
    });
  }, [folders, reservedFolderNames]);

  const deleteFolder = useCallback((name) => {
    setFiles(prev => {
      const next = {};
      for (const [path, content] of Object.entries(prev)) {
        if (path === name || path.startsWith(name + '/')) continue;
        next[path] = content;
      }
      return next;
    });
    setDeletedPaths(prev => {
      const next = new Set(prev);
      for (const path of Object.keys(files)) {
        if (path === name || path.startsWith(name + '/')) next.add(path);
      }
      return next;
    });
    setFolders(prev => {
      const next = new Set(prev);
      next.delete(name);
      return next;
    });
  }, [files]);

  const renameFolder = useCallback((oldName, newName) => {
    validateFolderName(newName, reservedFolderNames);
    if (folders.has(newName)) throw new Error(`Folder already exists: ${newName}`);
    setFiles(prev => {
      const next = {};
      for (const [path, content] of Object.entries(prev)) {
        const rewritten = rewritePathPrefix(path, oldName, newName);
        next[rewritten ?? path] = content;
      }
      return next;
    });
    setFolders(prev => {
      const next = new Set(prev);
      next.delete(oldName);
      next.add(newName);
      return next;
    });
  }, [folders, reservedFolderNames]);

  const hasChanges = useMemo(
    () =>
      JSON.stringify(files) !== JSON.stringify(initialFilesRef.current) ||
      deletedPaths.size > 0 ||
      JSON.stringify([...folders].sort()) !== JSON.stringify([...initialFoldersRef.current].sort()),
    [files, deletedPaths, folders],
  );

  const serialize = useCallback(() => ({
    files: { ...files },
    folders: [...folders],
  }), [files, folders]);

  const reset = useCallback((newInitialFiles = {}, newInitialFolders = []) => {
    setFiles(newInitialFiles);
    setFolders(new Set(newInitialFolders));
    setDeletedPaths(new Set());
    initialFilesRef.current = newInitialFiles;
    initialFoldersRef.current = new Set(newInitialFolders);
    setResetCount(c => c + 1);
  }, []);

  return {
    resetCount,
    tree,
    readContent,
    writeContent,
    upload,
    deleteFile,
    renameFile,
    createFolder,
    deleteFolder,
    renameFolder,
    checkedFiles,
    setChecked,
    hasChanges,
    serialize,
    reset,
    loading: false,
    error: null,
  };
}
