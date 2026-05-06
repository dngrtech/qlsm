import { Pencil, Plus, Trash2, Upload } from 'lucide-react';

export default function FileSidebarActions({
  capabilities,
  selectedFile,
  onNew,
  onUpload,
  onRename,
  onDelete,
}) {
  const {
    canCreate,
    canUpload,
    canRename,
    canDelete,
    allowedExtensions,
  } = capabilities;
  const isProtected = selectedFile?.protected;
  const noSelection = !selectedFile;
  const renameDisabled = noSelection || isProtected;
  const deleteDisabled = noSelection || isProtected;
  const renameTitle = noSelection
    ? 'Select a file first'
    : isProtected ? 'Built-in file, cannot be renamed' : 'Rename selected file';
  const deleteTitle = noSelection
    ? 'Select a file first'
    : isProtected ? 'Built-in file, cannot be deleted' : 'Delete selected file';

  return (
    <div className="flex-shrink-0 border-t border-[var(--surface-border)] p-2 space-y-1.5">
      {(canCreate || canUpload) && (
        <div className="grid grid-cols-2 gap-2">
          {canCreate && (
            <button
              type="button"
              onClick={onNew}
              className="flex items-center justify-center gap-1 px-3 py-1.5 bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 text-[var(--text-secondary)] rounded text-xs"
            >
              <Plus className="w-3.5 h-3.5" /> New
            </button>
          )}
          {canUpload && (
            <label className="flex items-center justify-center gap-1 px-3 py-1.5 bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 text-[var(--text-secondary)] rounded text-xs cursor-pointer">
              <Upload className="w-3.5 h-3.5" /> Upload
              <input
                type="file"
                accept={allowedExtensions.join(',')}
                className="hidden"
                onChange={(e) => {
                  if (e.target.files[0]) onUpload(e.target.files[0]);
                  e.target.value = '';
                }}
              />
            </label>
          )}
        </div>
      )}
      {(canRename || canDelete) && (
        <div className="grid grid-cols-2 gap-2">
          {canRename && (
            <button
              type="button"
              onClick={onRename}
              disabled={renameDisabled}
              title={renameTitle}
              className="flex items-center justify-center gap-1 px-3 py-1.5 bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 disabled:opacity-50 disabled:cursor-not-allowed text-[var(--text-secondary)] rounded text-xs"
            >
              <Pencil className="w-3.5 h-3.5" /> Rename
            </button>
          )}
          {canDelete && (
            <button
              type="button"
              onClick={onDelete}
              disabled={deleteDisabled}
              title={deleteTitle}
              className="flex items-center justify-center gap-1 px-3 py-1.5 bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 disabled:opacity-50 disabled:cursor-not-allowed text-[var(--accent-danger)] rounded text-xs"
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete
            </button>
          )}
        </div>
      )}
    </div>
  );
}
