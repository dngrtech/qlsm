import { useMemo, useRef, useState } from 'react';
import { Box, Code, FileText, Folder, FolderOpen, Lock, Search, Settings, Type } from 'lucide-react';

import FileTreeRowMenu from './FileTreeRowMenu';
import InfoTooltip from '../common/InfoTooltip';
import { getFileType, sortFileTree, MAX_CONFIG_FOLDER_DEPTH } from './fileManagerUtils';
import {
  folderHasPluginFiles,
  getPluginHintReason,
  isEnableablePluginPath,
  PLUGIN_HINT_TEXT,
} from './pluginSelection';
import { formatPluginCommandsText, getPluginCvars, getPluginDescription, getPluginDisplayLabel } from './pluginManifest';

const FILE_TYPE_ICONS = {
  python: Code,
  text: FileText,
  binary: Box,
  font: Type,
};

const FILE_TYPE_COLORS = {
  python: 'text-blue-400',
  text: 'text-gray-400',
  binary: 'text-purple-400',
  font: 'text-pink-400',
};

function isCheckableFile(item, fileType, checkable, capabilities) {
  if (!checkable || item.type === 'folder') return false;
  if (fileType !== 'python' && !item.name?.endsWith('.factories')) return false;
  if (capabilities?.rootOnlyCheckable && !isEnableablePluginPath(item.path)) return false;
  return true;
}

function getTreeSignature(items = []) {
  return items.map(item => {
    if (item.type === 'folder') {
      return `${item.path}:folder[${getTreeSignature(item.children || [])}]`;
    }
    return `${item.path}:file`;
  }).join('|');
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
  capabilities,
  expandedFolders,
  onToggleFolder,
  rowMenuHandlers,
  onEditCvars,
}) {
  const expanded = item.type === 'folder' ? expandedFolders.has(item.path) : false;
  const isFolder = item.type === 'folder';
  const isSelected = !isFolder && item.path === selectedPath;
  const fileType = item.file_type || getFileType(item.name);
  const Icon = isFolder
    ? (expanded ? FolderOpen : Folder)
    : (FILE_TYPE_ICONS[fileType] || FileText);
  const iconColor = isFolder
    ? 'text-yellow-400'
    : (FILE_TYPE_COLORS[fileType] || 'text-gray-400');
  const showCheckbox = isCheckableFile(item, fileType, checkable, capabilities);
  const rootOnly = checkable && !!capabilities?.rootOnlyCheckable;
  const hintReason = !isFolder && rootOnly && !showCheckbox
    ? getPluginHintReason(item.path)
    : null;
  // rootOnlyCheckable is plugin-tab-exclusive (see capabilities.js PLUGIN_CAPS) —
  // safe signal to only enrich rows there, never Config/Factories tabs.
  const displayLabel = !isFolder && rootOnly ? getPluginDisplayLabel(item) : item.name;
  const manifestDescription = !isFolder && rootOnly ? (() => {
    // InfoTooltip's bubble is white-space: normal (shared component, other
    // callers rely on that), so a literal \n here would just collapse to a
    // space — join with punctuation instead of relying on a line break.
    const description = getPluginDescription(item);
    const commandsText = formatPluginCommandsText(item);
    if (description && commandsText) return `${description} Commands: ${commandsText}`;
    return description || (commandsText ? `Commands: ${commandsText}` : null);
  })() : null;
  const pluginCvars = !isFolder && rootOnly && onEditCvars ? getPluginCvars(item) : [];
  // One hint per open folder, next to its name, instead of one per child row.
  const showFolderHint = isFolder && rootOnly && foldersEnabled && expanded
    && folderHasPluginFiles(item);

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
            capabilities={capabilities}
            expandedFolders={expandedFolders}
            onToggleFolder={onToggleFolder}
            rowMenuHandlers={rowMenuHandlers}
            onEditCvars={onEditCvars}
          />
        ))}
      </>
    );
  }

  const handleClick = () => {
    if (isFolder) {
      onToggleFolder(item.path);
      return;
    }
    onSelectFile(item);
  };

  return (
    <>
      <div
        className={`group flex w-full items-center gap-2 px-2 py-1 rounded text-sm text-left ${
          isSelected
            ? 'bg-[var(--surface-elevated)] text-[var(--text-primary)]'
            : 'text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]/50'
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        <button
          type="button"
          className="flex flex-1 items-center gap-2 min-w-0 text-left"
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
          {hintReason && (
            <InfoTooltip
              text={PLUGIN_HINT_TEXT[hintReason]}
              size={14}
              testId={`plugin-hint-${item.path}`}
              className="flex-shrink-0"
            />
          )}
          <Icon className={`w-4 h-4 flex-shrink-0 ${iconColor}`} />
          <span className={`truncate min-w-0 ${showFolderHint ? '' : 'flex-1'}`}>{displayLabel}</span>
          {manifestDescription && (
            <InfoTooltip
              text={manifestDescription}
              size={13}
              testId={`plugin-manifest-${item.path}`}
              className="flex-shrink-0"
            />
          )}
          {/* Swallowing the click keeps a reach for the hint from collapsing the folder. */}
          {showFolderHint && (
            <span
              className="flex flex-shrink-0 items-center"
              onClick={(e) => e.stopPropagation()}
            >
              <InfoTooltip
                text={PLUGIN_HINT_TEXT.subfolder}
                size={13}
                testId={`plugin-hint-${item.path}`}
              />
            </span>
          )}
          {item.protected && (
            <Lock className="w-3 h-3 flex-shrink-0 text-[var(--text-muted)]" />
          )}
        </button>
        {pluginCvars.length > 0 && (
          <button
            type="button"
            onClick={() => onEditCvars(item, pluginCvars)}
            className="flex-shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            title="Edit plugin settings"
            data-testid={`plugin-cvars-${item.path}`}
          >
            <Settings size={13} />
          </button>
        )}
        <FileTreeRowMenu
          itemType={item.type}
          fileType={fileType}
          isProtected={!!item.protected}
          isMaxDepth={isFolder && item.path.split('/').length >= MAX_CONFIG_FOLDER_DEPTH}
          capabilities={capabilities}
          onDownload={() => rowMenuHandlers.onDownload(item)}
          onCopyContent={() => rowMenuHandlers.onCopyContent(item)}
          onRename={() => rowMenuHandlers.onRename(item)}
          onDelete={() => rowMenuHandlers.onDelete(item)}
          onNewFileInFolder={() => rowMenuHandlers.onNewFileInFolder(item)}
          onNewFolderInFolder={() => rowMenuHandlers.onNewFolderInFolder(item)}
          onUploadToFolder={(files) => rowMenuHandlers.onUploadToFolder(item, files)}
        />
      </div>
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
          capabilities={capabilities}
          expandedFolders={expandedFolders}
          onToggleFolder={onToggleFolder}
          rowMenuHandlers={rowMenuHandlers}
          onEditCvars={onEditCvars}
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
  capabilities = {},
  expandedFolders = new Set(),
  onToggleFolder = () => {},
  rowMenuHandlers = {},
  onEditCvars = null,
}) {
  const [search, setSearch] = useState('');
  const filesSignature = useMemo(() => getTreeSignature(files || []), [files]);
  const filesSignatureRef = useRef(null);
  const sortPriorityRef = useRef(null);
  const userChangedChecksRef = useRef(false);

  if (sortPriorityRef.current === null || filesSignatureRef.current !== filesSignature) {
    filesSignatureRef.current = filesSignature;
    sortPriorityRef.current = new Set(checkedFiles || []);
    userChangedChecksRef.current = false;
  } else if (
    checkable &&
    !userChangedChecksRef.current &&
    sortPriorityRef.current.size === 0 &&
    checkedFiles?.size > 0
  ) {
    sortPriorityRef.current = new Set(checkedFiles);
  }

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();

    function filterTree(items) {
      return items.reduce((acc, item) => {
        if (item.type === 'folder') {
          const children = filterTree(item.children || []);
          if (children.length || item.name.toLowerCase().includes(term)) {
            acc.push({ ...item, children });
          }
        } else if (item.name.toLowerCase().includes(term)) {
          acc.push(item);
        }
        return acc;
      }, []);
    }

    const sorted = sortFileTree(files || [], {
      checkable,
      checkedFiles: sortPriorityRef.current || checkedFiles,
    });
    return term ? filterTree(sorted) : sorted;
  }, [files, search, checkable, checkedFiles]);

  const handleCheck = (path, checked) => {
    userChangedChecksRef.current = true;
    onCheck(path, checked);
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-shrink-0 p-2">
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
      <div className="flex-1 min-h-0 overflow-y-auto px-1 scrollbar-thick">
        {filtered.map(item => (
          <TreeItem
            key={item.path}
            item={item}
            depth={0}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            checkable={checkable}
            checkedFiles={checkedFiles}
            onCheck={handleCheck}
            foldersEnabled={foldersEnabled}
            capabilities={capabilities}
            expandedFolders={expandedFolders}
            onToggleFolder={onToggleFolder}
            rowMenuHandlers={rowMenuHandlers}
            onEditCvars={onEditCvars}
          />
        ))}
      </div>
    </div>
  );
}
