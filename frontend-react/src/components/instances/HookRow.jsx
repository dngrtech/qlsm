import { useRef, useState } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { AlertTriangle, Check, Download, Edit2, GripVertical, MoreVertical, Pencil, RefreshCw, Trash2, X } from 'lucide-react';
import {
  downloadInstanceHook,
  renameInstanceHook,
  replaceInstanceHook,
  setInstanceHookDescription,
} from '../../services/api';

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function DescriptionCell({ hook, instanceId, onChanged, readOnly }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(hook.description || '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await setInstanceHookDescription(instanceId, hook.filename, value);
      setEditing(false);
      onChanged?.();
    } finally {
      setSaving(false);
    }
  };

  if (readOnly) {
    return (
      <span className="min-w-0 flex-1 truncate text-xs text-[var(--text-muted)]">
        {hook.description}
      </span>
    );
  }
  if (!editing) {
    return (
      <span className="flex min-w-0 flex-1 items-center gap-1.5 text-xs text-[var(--text-muted)]">
        <span className="truncate">{hook.description || <em>no description</em>}</span>
        <button
          type="button"
          aria-label={`Edit description for ${hook.filename}`}
          onClick={() => setEditing(true)}
          className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded hover:bg-[var(--surface-elevated)]"
        >
          <Pencil size={12} />
        </button>
      </span>
    );
  }
  return (
    <span className="flex min-w-0 flex-1 items-center gap-1">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') save();
          if (e.key === 'Escape') { setEditing(false); setValue(hook.description || ''); }
        }}
        autoFocus
        disabled={saving}
        className="min-w-0 flex-1 rounded border border-[var(--surface-border)] bg-[var(--surface)] px-1 py-0.5 text-xs"
      />
      <button type="button" onClick={save} disabled={saving} aria-label="Save description">
        <Check size={12} />
      </button>
      <button
        type="button"
        onClick={() => { setEditing(false); setValue(hook.description || ''); }}
        disabled={saving}
        aria-label="Cancel description"
      >
        <X size={12} />
      </button>
    </span>
  );
}

function HookActionsMenu({ hook, instanceId, onChanged, onDelete, onRename }) {
  const [open, setOpen] = useState(false);
  const fileInputRef = useRef(null);

  const handleDownload = async () => {
    setOpen(false);
    const blob = await downloadInstanceHook(instanceId, hook.filename);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = hook.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleReplace = () => {
    setOpen(false);
    fileInputRef.current?.click();
  };

  const onReplaceFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    await replaceInstanceHook(instanceId, hook.filename, file);
    onChanged?.();
  };

  return (
    <div className="relative flex-shrink-0">
      <input ref={fileInputRef} type="file" accept=".so" className="hidden" onChange={onReplaceFile} />
      <button
        type="button"
        aria-label={`Actions for ${hook.filename}`}
        onClick={() => setOpen((v) => !v)}
        className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
      >
        <MoreVertical size={16} />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-10 mt-1 w-32 rounded border border-[var(--surface-border)] bg-[var(--surface-elevated)] py-1 text-sm shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            onClick={handleDownload}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--surface-hover)]"
          >
            <Download size={14} /> Download
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={handleReplace}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--surface-hover)]"
          >
            <RefreshCw size={14} /> Replace
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => { setOpen(false); onRename(); }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--surface-hover)]"
          >
            <Edit2 size={14} /> Rename
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => { setOpen(false); onDelete?.(hook); }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-theme-danger hover:bg-[var(--surface-hover)]"
          >
            <Trash2 size={14} /> Delete
          </button>
        </div>
      )}
    </div>
  );
}

function HookRowContent({ hook, onToggle, dragHandleProps = null, style = undefined, readOnly = false, instanceId, onChanged, onDelete }) {
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(hook.filename);
  const [renameError, setRenameError] = useState(null);

  const startRename = () => { setRenameValue(hook.filename); setRenameError(null); setRenaming(true); };
  const cancelRename = () => { setRenaming(false); setRenameError(null); };
  const submitRename = async () => {
    try {
      const trimmed = renameValue.trim();
      if (trimmed === hook.filename) { cancelRename(); return; }
      await renameInstanceHook(instanceId, hook.filename, trimmed);
      setRenaming(false);
      onChanged?.();
    } catch (err) {
      setRenameError(err?.error?.message || 'Rename failed');
    }
  };

  return (
    <div
      style={style}
      className={`flex min-h-10 items-center gap-3 border-b border-[var(--surface-border)] px-3 py-2${readOnly ? '' : ' hover:bg-[var(--surface-hover)]'}`}
      data-testid={`hook-row-${hook.filename}`}
    >
      {!readOnly && (dragHandleProps ? (
        <button
          type="button"
          {...dragHandleProps.attributes}
          {...dragHandleProps.listeners}
          className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
          aria-label={`Reorder ${hook.filename}`}
        >
          <GripVertical size={16} />
        </button>
      ) : (
        <span className="h-7 w-7" />
      ))}
      {readOnly && <span className="h-7 w-7" />}
      <input
        type="checkbox"
        checked={hook.enabled}
        onChange={readOnly ? undefined : () => onToggle(hook.filename)}
        disabled={readOnly}
        className={`h-4 w-4 ${readOnly ? 'cursor-default opacity-75' : 'cursor-pointer'}`}
        aria-label={`Enable ${hook.filename}`}
      />
      {renaming ? (
        <span className="flex min-w-0 flex-1 items-center gap-1">
          <input
            type="text"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitRename();
              if (e.key === 'Escape') cancelRename();
            }}
            autoFocus
            className="min-w-0 flex-1 rounded border border-[var(--surface-border)] bg-[var(--surface)] px-1 py-0.5 font-mono text-sm"
          />
          {renameError && <span className="flex-shrink-0 text-xs text-theme-danger">{renameError}</span>}
        </span>
      ) : (
        <span className="min-w-0 basis-1/3 truncate font-mono text-sm text-[var(--text-primary)]">
          {hook.filename}
        </span>
      )}
      <span className="w-20 flex-shrink-0 text-right font-mono text-xs text-[var(--text-muted)]">
        {formatSize(hook.size)}
      </span>
      {!readOnly && instanceId ? (
        <DescriptionCell hook={hook} instanceId={instanceId} onChanged={onChanged} readOnly={readOnly} />
      ) : (
        hook.description ? (
          <span className="min-w-0 flex-1 truncate text-xs text-[var(--text-muted)]">{hook.description}</span>
        ) : (
          <span className="min-w-0 flex-1" />
        )
      )}
      {!readOnly && instanceId && (
        <HookActionsMenu
          hook={hook}
          instanceId={instanceId}
          onChanged={onChanged}
          onDelete={onDelete}
          onRename={startRename}
        />
      )}
    </div>
  );
}

export function SortableHookRow({ hook, onToggle, instanceId, onChanged, onDelete }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: hook.filename,
  });
  const style = {
    opacity: isDragging ? 0.6 : 1,
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <div ref={setNodeRef}>
      <HookRowContent
        hook={hook}
        onToggle={onToggle}
        dragHandleProps={{ attributes, listeners }}
        style={style}
        instanceId={instanceId}
        onChanged={onChanged}
        onDelete={onDelete}
      />
    </div>
  );
}

export function ReadOnlyHookRow({ hook }) {
  return <HookRowContent hook={{ ...hook, enabled: true }} readOnly />;
}

export function MissingHookRow({ hook, onRemove }) {
  return (
    <div
      className="flex min-h-10 items-center gap-3 border-b border-[var(--surface-border)] bg-theme-danger/5 px-3 py-2"
      data-testid={`hook-row-missing-${hook.filename}`}
    >
      <span className="h-7 w-7 flex items-center justify-center text-theme-danger">
        <AlertTriangle size={15} />
      </span>
      <input
        type="checkbox"
        checked
        onChange={() => onRemove(hook.filename)}
        className="h-4 w-4 cursor-pointer"
        aria-label={`Remove missing hook ${hook.filename}`}
      />
      <span className="min-w-0 flex-1 truncate font-mono text-sm text-theme-danger">
        {hook.filename}
      </span>
      <span className="text-xs text-theme-danger">File missing</span>
      <span className="w-3.5" />
    </div>
  );
}

export default function HookRow({ hook, onToggle, instanceId, onChanged, onDelete }) {
  return <HookRowContent hook={hook} onToggle={onToggle} instanceId={instanceId} onChanged={onChanged} onDelete={onDelete} />;
}
