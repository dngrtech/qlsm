import React, { useState } from 'react';
import { Search, Plus, Upload } from 'lucide-react';
import FileTreeItem from './FileTreeItem';

/**
 * Container component for the file tree with search, actions, and tree display.
 */
function FileTree({
  files,
  selectedPath,
  onSelectFile,
  onNewFile,
  onUploadFile,
  isLoading = false,
  checkable = false,
  checkedFiles = new Set(),
  onCheck = () => { }
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedFolders, setExpandedFolders] = useState(new Set());

  const handleToggleFolder = (path) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev);
      if (newSet.has(path)) {
        newSet.delete(path);
      } else {
        newSet.add(path);
      }
      return newSet;
    });
  };

  // Auto-expand folders when searching
  const getExpandedForSearch = () => {
    if (!searchQuery) return expandedFolders;

    // When searching, expand all folders that have matching children
    const expanded = new Set(expandedFolders);
    const expandMatching = (items) => {
      items.forEach(item => {
        if (item.type === 'folder' && item.children) {
          const hasMatch = item.children.some(child =>
            child.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (child.type === 'folder' && child.children?.length > 0)
          );
          if (hasMatch) {
            expanded.add(item.path);
          }
          expandMatching(item.children);
        }
      });
    };
    expandMatching(files);
    return expanded;
  };

  const effectiveExpanded = searchQuery ? getExpandedForSearch() : expandedFolders;

  return (
    <div className="flex flex-col h-full bg-transparent rounded-lg border border-slate-600">
      {/* Search */}
      <div className="p-2 border-b border-slate-600">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search files..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent border border-slate-600 rounded pl-8 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 focus:outline-none"
          />
        </div>
      </div>

      {/* File Tree */}
      <div className="flex-1 overflow-y-auto p-2 min-h-0 scrollbar-thick">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <span className="text-slate-500 text-sm">Loading scripts...</span>
          </div>
        ) : files.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <span className="text-slate-500 text-sm">No scripts found</span>
          </div>
        ) : (
          files.map((item) => (
            <FileTreeItem
              key={item.path}
              item={item}
              selectedPath={selectedPath}
              onSelect={onSelectFile}
              expandedFolders={effectiveExpanded}
              onToggleFolder={handleToggleFolder}
              searchQuery={searchQuery}
              checkable={checkable}
              checkedFiles={checkedFiles}
              onCheck={onCheck}
            />
          ))
        )}
      </div>

      {/* Actions */}
      <div className="p-2 border-t border-slate-600 flex gap-2">
        {onNewFile && (
          <button
            type="button"
            onClick={onNewFile}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-slate-700/50 hover:bg-slate-600/50 text-slate-300 text-xs font-medium rounded transition-colors"
          >
            <Plus size={14} />
            New
          </button>
        )}
        {onUploadFile && (
          <button
            type="button"
            onClick={onUploadFile}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-slate-700/50 hover:bg-slate-600/50 text-slate-300 text-xs font-medium rounded transition-colors"
          >
            <Upload size={14} />
            Upload
          </button>
        )}
      </div>
    </div>
  );
}

export default FileTree;
