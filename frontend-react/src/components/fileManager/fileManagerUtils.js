export function flattenFiles(items = []) {
  return items.flatMap(item => {
    if (item.type === 'folder') return flattenFiles(item.children || []);
    return [item];
  });
}

export function sortFileTree(items = [], { checkable = false, checkedFiles = new Set() } = {}) {
  return [...items].sort((a, b) => {
    if (a.type === 'folder' && b.type !== 'folder') return -1;
    if (a.type !== 'folder' && b.type === 'folder') return 1;
    if (checkable) {
      const aChecked = a.type !== 'folder' && checkedFiles.has(a.path);
      const bChecked = b.type !== 'folder' && checkedFiles.has(b.path);
      if (aChecked && !bChecked) return -1;
      if (!aChecked && bChecked) return 1;
    }
    return a.name.localeCompare(b.name);
  }).map(item => item.type === 'folder' && item.children
    ? { ...item, children: sortFileTree(item.children, { checkable, checkedFiles }) }
    : item);
}

export function getInitialSelectableFile(files = [], {
  checkable = false,
  checkedFiles = new Set(),
  defaultSelectedPath = null,
} = {}) {
  const sortedFiles = flattenFiles(sortFileTree(files, { checkable, checkedFiles }));
  if (defaultSelectedPath) {
    const preferred = sortedFiles.find(file => file.path === defaultSelectedPath);
    if (preferred) return preferred;
  }
  if (checkable) {
    return sortedFiles.find(file => checkedFiles.has(file.path)) || null;
  }
  return sortedFiles[0] || null;
}

export function getFileType(name = '') {
  if (name.endsWith('.py')) return 'python';
  if (name.endsWith('.so')) return 'binary';
  return 'text';
}

export function basename(path = '') {
  const index = path.lastIndexOf('/');
  return index === -1 ? path : path.slice(index + 1);
}

export function dirname(path = '') {
  const index = path.lastIndexOf('/');
  return index === -1 ? '' : path.slice(0, index);
}

export function joinPath(dir, name) {
  return dir ? `${dir}/${name}` : name;
}

export function isCheckablePath(path = '') {
  return path.endsWith('.py') || path.endsWith('.factories');
}

export function getErrorMessage(error, fallback) {
  return error?.response?.data?.error?.message || error?.message || fallback;
}

export function mergeFoldersIntoTree(items = [], folders = new Set()) {
  const existing = new Set(items.filter(i => i.type === 'folder').map(i => i.name));
  const extras = [];
  for (const name of folders) {
    if (existing.has(name)) continue;
    extras.push({ name, path: name, type: 'folder', children: [] });
  }
  return [...items, ...extras];
}

export function rewritePathPrefix(path, oldPrefix, newPrefix) {
  if (path === oldPrefix) return newPrefix;
  if (path.startsWith(oldPrefix + '/')) {
    return newPrefix + path.slice(oldPrefix.length);
  }
  return null;
}

export function getExtension(name = '') {
  const dotIndex = name.lastIndexOf('.');
  return dotIndex === -1 ? '' : name.slice(dotIndex).toLowerCase();
}
