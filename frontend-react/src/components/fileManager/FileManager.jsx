import { forwardRef, useImperativeHandle } from 'react';

import ConfirmationModal from '../ConfirmationModal';
import FileEditorPanel from './FileEditorPanel';
import FileSidebarActions from './FileSidebarActions';
import FileTree from './FileTree';
import NewFileModal from './NewFileModal';
import RenameFileModal from './RenameFileModal';
import { basename } from './fileManagerUtils';
import { useFileManagerController } from './useFileManagerController';

function buildDeleteMessage(target) {
  if (!target) return '';
  if (target.kind === 'folder') {
    if (target.fileCount === 0) {
      return `Delete folder ${target.item.name}?`;
    }
    return `Delete folder ${target.item.name} and ${target.fileCount} file${target.fileCount === 1 ? '' : 's'} inside? This cannot be undone.`;
  }
  return `Delete ${target.item.name}?`;
}

const FileManager = forwardRef(function FileManager({
  adapter,
  capabilities,
  checkable = false,
  checkedFiles,
  onCheck,
  onExpandEditor,
  defaultSelectedPath = null,
  getLanguageForFile,
  getLinterSourceForFile,
  getBinaryMeta,
  saveBinaryMeta,
  binaryContext = null,
}, ref) {
  const controller = useFileManagerController({
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
  });

  useImperativeHandle(ref, () => ({
    flushEdits: controller.flushEdits,
    updateContent: controller.updateContent,
  }), [controller.flushEdits, controller.updateContent]);

  const creatableExtensions = capabilities.allowedExtensions.filter(ext => ext !== '.so');
  const newModalExistingNames = controller.newModalMode === 'folder'
    ? controller.rootFolderNames
    : controller.siblingNames;

  if (adapter.error) {
    return (
      <div className="flex items-center justify-center h-full text-red-400 p-4">
        {adapter.error}
      </div>
    );
  }

  if (adapter.loading) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
        Loading files...
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 border border-[var(--surface-border)] rounded overflow-hidden">
      <div className="w-64 min-h-0 flex-shrink-0 border-r border-[var(--surface-border)] bg-[var(--surface-base)] flex flex-col">
        <FileTree
          files={controller.files}
          selectedPath={controller.selectedFile?.path}
          onSelectFile={controller.handleSelectFile}
          checkable={checkable}
          checkedFiles={controller.effectiveCheckedFiles}
          onCheck={controller.effectiveOnCheck}
          foldersEnabled={capabilities.canFolders}
          capabilities={capabilities}
          expandedFolders={controller.expandedFolders}
          onToggleFolder={controller.handleToggleFolder}
          rowMenuHandlers={{
            onDownload: controller.handleDownload,
            onCopyContent: controller.handleCopyContent,
            onRename: controller.openRenameModal,
            onDelete: controller.requestDelete,
            onNewFileInFolder: controller.handleNewFileInFolder,
            onUploadToFolder: controller.handleUploadToFolder,
          }}
        />
        <FileSidebarActions
          capabilities={capabilities}
          onNewFile={() => controller.openNewFileModal('')}
          onNewFolder={controller.openNewFolderModal}
          onUpload={controller.handleUpload}
        />
      </div>
      <div className="flex-1 min-w-0 min-h-0 bg-[var(--surface-base)] flex flex-col">
        {controller.actionError && (
          <div className="px-3 py-2 text-sm text-[var(--accent-danger)] border-b border-[var(--surface-border)]">
            {controller.actionError}
          </div>
        )}
        <FileEditorPanel
          selectedFile={controller.selectedFile}
          content={controller.currentContent}
          onChange={controller.handleContentChange}
          isDirty={controller.isDirty}
          isLoading={controller.contentLoading}
          language={controller.language}
          linterSource={controller.linterSource}
          capabilities={capabilities}
          onExpand={onExpandEditor}
          onReplace={controller.handleReplace}
          binaryDescription={controller.binaryDescription}
          onSaveBinaryDescription={saveBinaryMeta ? controller.handleSaveBinaryDescription : null}
        />
      </div>
      <NewFileModal
        isOpen={controller.showNewModal}
        onClose={() => controller.setShowNewModal(false)}
        onCreate={controller.handleCreateFromModal}
        mode={controller.newModalMode}
        allowedExtensions={creatableExtensions.length ? creatableExtensions : capabilities.allowedExtensions}
        existingNames={newModalExistingNames}
        reservedNames={capabilities.reservedFolderNames || []}
      />
      <RenameFileModal
        isOpen={controller.showRenameModal}
        onClose={() => { controller.setShowRenameModal(false); }}
        onRename={controller.handleRename}
        currentName={basename(controller.renameTarget?.path || '')}
        allowedExtensions={controller.renameTarget?.kind === 'folder' ? [] : capabilities.allowedExtensions}
        existingNames={controller.renameTargetSiblings}
        reservedNames={controller.renameTarget?.kind === 'folder' ? (capabilities.reservedFolderNames || []) : []}
      />
      <ConfirmationModal
        isOpen={controller.confirmDeleteOpen}
        onClose={() => controller.setConfirmDeleteOpen(false)}
        onConfirm={controller.handleDelete}
        title={controller.deleteTarget?.kind === 'folder' ? 'Delete folder' : 'Delete file'}
        message={buildDeleteMessage(controller.deleteTarget)}
        confirmButtonText="Delete"
        confirmButtonVariant="danger"
        zIndexClass="z-[70]"
      />
    </div>
  );
});

export default FileManager;
