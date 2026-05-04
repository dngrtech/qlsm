import { useCallback, useMemo, useRef, useState } from 'react';

function getExtension(path) {
  const dotIndex = path.lastIndexOf('.');
  return dotIndex === -1 ? '' : path.slice(dotIndex).toLowerCase();
}

function validatePath(path, allowedExtensions) {
  if (!path || path.includes('/') || path.includes('\\') || path.includes('..') || path.startsWith('.')) {
    throw new Error(`Invalid filename: ${path}`);
  }
  const ext = getExtension(path);
  if (!allowedExtensions.includes(ext)) {
    throw new Error(`Disallowed extension ${ext}`);
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

export function useStateAdapter({
  initialFiles = {},
  allowedExtensions = [],
  protectedFiles = [],
  serverTree = null,
  readServerContent = null,
}) {
  const [files, setFiles] = useState(initialFiles);
  const [deletedPaths, setDeletedPaths] = useState(() => new Set());
  const initialRef = useRef(initialFiles);
  const protectedSet = useMemo(() => new Set(protectedFiles), [protectedFiles]);

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
        name: existing.name || path,
        path,
        type: 'file',
        file_type: existing.file_type || 'text',
      });
    }
    return [...byPath.values()]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(item => ({
        ...item,
        protected: protectedSet.has(item.path),
      }));
  }, [files, serverTree, deletedPaths, protectedSet]);

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

  const upload = useCallback(async (file) => {
    validatePath(file.name, allowedExtensions);
    const content = await file.text();
    setFiles(prev => ({ ...prev, [file.name]: content }));
    setDeletedPaths(prev => {
      const next = new Set(prev);
      next.delete(file.name);
      return next;
    });
    return { path: file.name };
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
    if (tree.some(item => item.path === newPath && item.path !== oldPath)) {
      throw new Error(`Target exists: ${newPath}`);
    }
    const content = await readContent(oldPath);
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
  }, [allowedExtensions, protectedSet, readContent, tree]);

  const hasChanges = useMemo(
    () => JSON.stringify(files) !== JSON.stringify(initialRef.current) || deletedPaths.size > 0,
    [files, deletedPaths],
  );

  const serialize = useCallback(() => ({ ...files }), [files]);

  const reset = useCallback((newInitial = {}) => {
    setFiles(newInitial);
    setDeletedPaths(new Set());
    initialRef.current = newInitial;
  }, []);

  return {
    tree,
    readContent,
    writeContent,
    upload,
    deleteFile,
    renameFile,
    checkedFiles,
    setChecked,
    hasChanges,
    serialize,
    reset,
    loading: false,
    error: null,
  };
}
