import React from 'react';
import { ChevronRight, ChevronDown, File, Folder, FolderOpen } from 'lucide-react';

/**
 * Recursive component for rendering file tree items.
 * Handles both files and folders with expand/collapse functionality.
 */
function FileTreeItem({
  item,
  depth = 0,
  selectedPath,
  onSelect,
  expandedFolders,
  onToggleFolder,
  searchQuery = '',
  checkable = false,
  checkedFiles = new Set(),
  onCheck = () => { }
}) {
  const isFolder = item.type === 'folder';
  const isExpanded = expandedFolders.has(item.path);
  const isSelected = selectedPath === item.path;

  // Filter items based on search query
  const matchesSearch = (node) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    if (node.name.toLowerCase().includes(query)) return true;
    if (node.type === 'folder' && node.children) {
      return node.children.some(child => matchesSearch(child));
    }
    return false;
  };

  if (!matchesSearch(item)) {
    return null;
  }

  const handleClick = (e) => {
    // If clicking checkbox, don't trigger select
    if (e.target.type === 'checkbox') return;

    if (isFolder) {
      onToggleFolder(item.path);
    } else {
      onSelect(item.path);
    }
  };

  const handleCheck = (e) => {
    e.stopPropagation();
    onCheck(item.path, e.target.checked);
  };

  // Filter children based on search
  const filteredChildren = item.children?.filter(child => matchesSearch(child)) || [];

  return (
    <div>
      <div
        className={`flex items-center gap-1 px-2 py-1 cursor-pointer hover:bg-slate-700/50 rounded text-sm transition-colors
          ${isSelected ? 'text-[var(--accent-primary)]' : 'text-[var(--text-secondary)]'}`}
        style={{
          paddingLeft: `${depth * 12 + 8}px`,
          ...(isSelected ? { backgroundColor: 'color-mix(in srgb, var(--accent-primary) 15%, transparent)' } : {}),
        }}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && handleClick()}
      >
        {isFolder ? (
          <>
            {isExpanded ? (
              <ChevronDown size={14} className="text-slate-500 flex-shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-slate-500 flex-shrink-0" />
            )}
            {isExpanded ? (
              <FolderOpen size={14} className="text-yellow-500 flex-shrink-0" />
            ) : (
              <Folder size={14} className="text-yellow-500 flex-shrink-0" />
            )}
          </>
        ) : (
          <>
            <span className="w-3.5 flex-shrink-0" />
            {checkable && (
              <input
                type="checkbox"
                checked={checkedFiles.has(item.path)}
                onChange={handleCheck}
                className="mr-1.5 w-3.5 h-3.5 rounded border-slate-600 bg-slate-700/50 text-indigo-500 focus:ring-offset-0 focus:ring-1 focus:ring-indigo-500"
              />
            )}
            <File size={14} className="text-blue-400 flex-shrink-0" />
          </>
        )}
        <span className="ml-1 truncate">{item.name}</span>
      </div>

      {isFolder && isExpanded && filteredChildren.length > 0 && (
        <div>
          {filteredChildren.map((child) => (
            <FileTreeItem
              key={child.path}
              item={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
              expandedFolders={expandedFolders}
              onToggleFolder={onToggleFolder}
              searchQuery={searchQuery}
              checkable={checkable}
              checkedFiles={checkedFiles}
              onCheck={onCheck}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default FileTreeItem;
