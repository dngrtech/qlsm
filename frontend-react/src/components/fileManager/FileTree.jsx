import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Code, FileText, Folder, FolderOpen, Lock, Search } from 'lucide-react';

const FILE_TYPE_ICONS = {
  python: Code,
  text: FileText,
  binary: Box,
};

const FILE_TYPE_COLORS = {
  python: 'text-blue-400',
  text: 'text-gray-400',
  binary: 'text-purple-400',
};

function getFileType(name = '') {
  if (name.endsWith('.py')) return 'python';
  if (name.endsWith('.so')) return 'binary';
  return 'text';
}

function isCheckableFile(item, fileType, checkable) {
  if (!checkable || item.type === 'folder') return false;
  return fileType === 'python' || item.name?.endsWith('.factories');
}

function TreeItem({
  item,
  depth,
  selectedPath,
  onSelectFile,
  checkable,
  checkedFiles,
  onCheck,
  foldersEnabled,
}) {
  const [expanded, setExpanded] = useState(true);
  const isFolder = item.type === 'folder';
  const isSelected = !isFolder && item.path === selectedPath;
  const fileType = item.file_type || getFileType(item.name);
  const Icon = isFolder
    ? (expanded ? FolderOpen : Folder)
    : (FILE_TYPE_ICONS[fileType] || FileText);
  const iconColor = isFolder
    ? 'text-yellow-400'
    : (FILE_TYPE_COLORS[fileType] || 'text-gray-400');
  const showCheckbox = isCheckableFile(item, fileType, checkable);

  if (isFolder && !foldersEnabled) {
    return (
      <>
        {item.children?.map(child => (
          <TreeItem
            key={child.path}
            item={child}
            depth={depth}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            checkable={checkable}
            checkedFiles={checkedFiles}
            onCheck={onCheck}
            foldersEnabled={foldersEnabled}
          />
        ))}
      </>
    );
  }

  const handleClick = () => {
    if (isFolder) {
      setExpanded(current => !current);
      return;
    }
    onSelectFile(item);
  };

  return (
    <>
      <button
        type="button"
        className={`flex w-full items-center gap-2 px-2 py-1 rounded text-sm text-left ${
          isSelected
            ? 'bg-[var(--surface-elevated)] text-[var(--text-primary)]'
            : 'text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]/50'
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={handleClick}
      >
        {showCheckbox && (
          <input
            type="checkbox"
            checked={checkedFiles?.has(item.path) || false}
            onChange={(e) => {
              e.stopPropagation();
              onCheck(item.path, e.target.checked);
            }}
            onClick={(e) => e.stopPropagation()}
            className="h-3.5 w-3.5 rounded border-gray-500 text-blue-500 focus:ring-blue-500 flex-shrink-0"
          />
        )}
        <Icon className={`w-4 h-4 flex-shrink-0 ${iconColor}`} />
        <span className="truncate flex-1 min-w-0">{item.name}</span>
        {item.protected && (
          <Lock className="w-3 h-3 flex-shrink-0 text-[var(--text-muted)]" />
        )}
      </button>
      {isFolder && foldersEnabled && expanded && item.children?.map(child => (
        <TreeItem
          key={child.path}
          item={child}
          depth={depth + 1}
          selectedPath={selectedPath}
          onSelectFile={onSelectFile}
          checkable={checkable}
          checkedFiles={checkedFiles}
          onCheck={onCheck}
          foldersEnabled={foldersEnabled}
        />
      ))}
    </>
  );
}

export default function FileTree({
  files,
  selectedPath,
  onSelectFile,
  checkable = false,
  checkedFiles = new Set(),
  onCheck = () => {},
  foldersEnabled = false,
}) {
  const [search, setSearch] = useState('');
  const sortPriorityRef = useRef(null);

  useEffect(() => {
    sortPriorityRef.current = new Set(checkedFiles || []);
  }, [files]); // eslint-disable-line react-hooks/exhaustive-deps

  if (sortPriorityRef.current === null) {
    sortPriorityRef.current = new Set(checkedFiles || []);
  }

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const sortPriority = sortPriorityRef.current;

    function sortItems(items) {
      return [...items].sort((a, b) => {
        if (a.type === 'folder' && b.type !== 'folder') return -1;
        if (a.type !== 'folder' && b.type === 'folder') return 1;
        if (checkable) {
          const aChecked = sortPriority?.has(a.path);
          const bChecked = sortPriority?.has(b.path);
          if (aChecked && !bChecked) return -1;
          if (!aChecked && bChecked) return 1;
        }
        return a.name.localeCompare(b.name);
      }).map(item => item.type === 'folder' && item.children
        ? { ...item, children: sortItems(item.children) }
        : item);
    }

    function filterTree(items) {
      return items.reduce((acc, item) => {
        if (item.type === 'folder') {
          const children = filterTree(item.children || []);
          if (children.length) acc.push({ ...item, children });
        } else if (item.name.toLowerCase().includes(term)) {
          acc.push(item);
        }
        return acc;
      }, []);
    }

    const sorted = sortItems(files || []);
    return term ? filterTree(sorted) : sorted;
  }, [files, search, checkable]);

  return (
    <div className="flex flex-col h-full">
      <div className="p-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search files..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-[var(--surface-elevated)] border border-[var(--surface-border)] rounded text-sm text-[var(--text-secondary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--surface-border-strong)]"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-1 scrollbar-thick">
        {filtered.map(item => (
          <TreeItem
            key={item.path}
            item={item}
            depth={0}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            checkable={checkable}
            checkedFiles={checkedFiles}
            onCheck={onCheck}
            foldersEnabled={foldersEnabled}
          />
        ))}
      </div>
    </div>
  );
}
