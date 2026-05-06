import { forwardRef, useImperativeHandle } from 'react';

import ConfirmationModal from '../ConfirmationModal';
import FileEditorPanel from './FileEditorPanel';
import FileSidebarActions from './FileSidebarActions';
import FileTree from './FileTree';
import NewFileModal from './NewFileModal';
import RenameFileModal from './RenameFileModal';
import { basename } from './fileManagerUtils';
import { useFileManagerController } from './useFileManagerController';

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
        />
        <FileSidebarActions
          capabilities={capabilities}
          selectedFile={controller.selectedFile}
          onNew={() => controller.setShowNewModal(true)}
          onUpload={controller.handleUpload}
          onRename={() => controller.setShowRenameModal(true)}
          onDelete={() => controller.setConfirmDeleteOpen(true)}
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
        onCreate={controller.handleCreate}
        allowedExtensions={creatableExtensions.length ? creatableExtensions : capabilities.allowedExtensions}
        existingNames={controller.siblingNames}
      />
      <RenameFileModal
        isOpen={controller.showRenameModal}
        onClose={() => controller.setShowRenameModal(false)}
        onRename={controller.handleRename}
        currentName={basename(controller.selectedFile?.path || '')}
        allowedExtensions={capabilities.allowedExtensions}
        existingNames={controller.siblingNames}
      />
      <ConfirmationModal
        isOpen={controller.confirmDeleteOpen}
        onClose={() => controller.setConfirmDeleteOpen(false)}
        onConfirm={controller.handleDelete}
        title="Delete file"
        message={`Delete ${controller.selectedFile?.name || 'this file'}?`}
        confirmButtonText="Delete"
        confirmButtonVariant="danger"
        zIndexClass="z-[70]"
      />
    </div>
  );
});

export default FileManager;
