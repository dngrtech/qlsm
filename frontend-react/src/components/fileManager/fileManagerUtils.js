export function flattenFiles(items = []) {
  return items.flatMap(item => {
    if (item.type === 'folder') return flattenFiles(item.children || []);
    return [item];
  });
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
