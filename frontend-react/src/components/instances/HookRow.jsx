import { Fragment, useRef, useState } from 'react';
import { Menu, Transition } from '@headlessui/react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { AlertTriangle, Check, Download, Edit2, GripVertical, MoreVertical, Pencil, RefreshCw, Trash2, X } from 'lucide-react';
import {
  downloadInstanceHook,
  renameInstanceHook,
  replaceInstanceHook,
  setInstanceHookDescription,
} from '../../services/api';
import InfoTooltip from '../common/InfoTooltip';

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function timeAgo(ts) {
  if (!ts) return null;
  const secs = Math.floor(Date.now() / 1000) - ts;
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  if (secs < 86400 * 30) return `${Math.floor(secs / 86400)}d ago`;
  return `${Math.floor(secs / (86400 * 30))}mo ago`;
}

function FilenameCell({ filename }) {
  const dot = filename.lastIndexOf('.');
  const base = dot > 0 ? filename.slice(0, dot) : filename;
  const ext = dot > 0 ? filename.slice(dot) : '';
  return (
    <span className="font-mono text-sm text-[var(--text-primary)]">
      {base}<span className="text-[var(--text-muted)]">{ext}</span>
    </span>
  );
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
        className="min-w-0 flex-1 rounded border border-[var(--surface-border)] bg-[var(--surface-raised)] px-1 py-0.5 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
      />
      <button type="button" onClick={save} disabled={saving} aria-label="Save description" className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[var(--accent-success)] hover:bg-[var(--surface-elevated)]">
        <Check size={12} />
      </button>
      <button
        type="button"
        onClick={() => { setEditing(false); setValue(hook.description || ''); }}
        disabled={saving}
        aria-label="Cancel description"
        className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
      >
        <X size={12} />
      </button>
    </span>
  );
}

function HookActionsMenu({ hook, instanceId, onChanged, onDelete, onRename }) {
  const [actionError, setActionError] = useState(null);
  const fileInputRef = useRef(null);

  const handleDownload = async () => {
    setActionError(null);
    try {
      const blob = await downloadInstanceHook(instanceId, hook.filename);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = hook.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionError(err?.error?.message || 'Download failed');
    }
  };

  const onReplaceFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setActionError(null);
    try {
      await replaceInstanceHook(instanceId, hook.filename, file);
      onChanged?.();
    } catch (err) {
      setActionError(err?.error?.message || 'Replace failed');
    }
  };

  const items = [
    { key: 'download', label: 'Download', icon: Download, onClick: handleDownload },
    { key: 'replace', label: 'Replace', icon: RefreshCw, onClick: () => fileInputRef.current?.click() },
    { key: 'rename', label: 'Rename', icon: Edit2, onClick: onRename },
    { key: 'delete', label: 'Delete', icon: Trash2, onClick: () => onDelete?.(hook), danger: true },
  ];

  return (
    <div className="relative flex-shrink-0">
      <input ref={fileInputRef} type="file" accept=".so" className="hidden" onChange={onReplaceFile} />
      <Menu as="div" className="relative">
        <Menu.Button
          aria-label={`Actions for ${hook.filename}`}
          onClick={() => setActionError(null)}
          className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
        >
          <MoreVertical size={16} />
        </Menu.Button>
        <Transition
          as={Fragment}
          unmount={false}
          enter="transition ease-out duration-100"
          enterFrom="transform opacity-0 scale-95"
          enterTo="transform opacity-100 scale-100"
          leave="transition ease-in duration-75"
          leaveFrom="transform opacity-100 scale-100"
          leaveTo="transform opacity-0 scale-95"
        >
          <Menu.Items unmount={false} className="absolute right-0 z-50 mt-1 w-36 origin-top-right rounded-md border border-[var(--surface-border)] bg-[var(--surface-elevated)] py-1 shadow-lg focus:outline-none">
            {items.map((item) => (
              <Menu.Item key={item.key}>
                {({ active }) => (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); item.onClick(); }}
                    className={`${active ? 'bg-black/10 dark:bg-white/10' : ''} ${item.danger ? 'text-[var(--accent-danger)]' : 'text-[var(--text-secondary)]'} flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs`}
                  >
                    <item.icon size={14} /> {item.label}
                  </button>
                )}
              </Menu.Item>
            ))}
          </Menu.Items>
        </Transition>
      </Menu>
      {actionError && (
        <div className="absolute right-0 z-20 mt-1 w-48 rounded border border-[var(--surface-border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs text-theme-danger shadow-lg">
          {actionError}
        </div>
      )}
    </div>
  );
}

function HookRowContent({ hook, onToggle, dragHandleProps = null, style = undefined, readOnly = false, instanceId, onChanged, onDelete }) {
  const [renaming, setRenaming] = useState(false);
  const [renameSaving, setRenameSaving] = useState(false);
  const [renameValue, setRenameValue] = useState(hook.filename);
  const [renameError, setRenameError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const fileInputRef = useRef(null);

  const handleDownload = async () => {
    setActionError(null);
    try {
      const blob = await downloadInstanceHook(instanceId, hook.filename);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = hook.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionError(err?.error?.message || 'Download failed');
    }
  };

  const onReplaceFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setActionError(null);
    try {
      await replaceInstanceHook(instanceId, hook.filename, file);
      onChanged?.();
    } catch (err) {
      setActionError(err?.error?.message || 'Replace failed');
    }
  };

  const startRename = () => { setRenameValue(hook.filename); setRenameError(null); setRenaming(true); };
  const cancelRename = () => { setRenaming(false); setRenameError(null); };
  const submitRename = async () => {
    if (renameSaving) return;
    const trimmed = renameValue.trim();
    if (trimmed === hook.filename) { cancelRename(); return; }
    setRenameSaving(true);
    try {
      await renameInstanceHook(instanceId, hook.filename, trimmed);
      setRenaming(false);
      onChanged?.();
    } catch (err) {
      setRenameError(err?.error?.message || 'Rename failed');
    } finally {
      setRenameSaving(false);
    }
  };

  return (
    <div
      style={style}
      className={`flex min-h-12 items-center gap-3 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-raised)] px-3 py-2.5${readOnly ? '' : ' hover:bg-[var(--surface-elevated)]'}`}
      data-testid={`hook-row-${hook.filename}`}
    >
      {!readOnly && (dragHandleProps ? (
        <button
          type="button"
          {...dragHandleProps.attributes}
          {...dragHandleProps.listeners}
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
          aria-label={`Reorder ${hook.filename}`}
        >
          <GripVertical size={16} />
        </button>
      ) : (
        <span className="h-7 w-7 flex-shrink-0" />
      ))}
      {readOnly && <span className="h-7 w-7 flex-shrink-0" />}
      <button
        type="button"
        onClick={readOnly ? undefined : () => onToggle(hook.filename)}
        disabled={readOnly}
        className="neu-toggle neu-toggle--sm flex-shrink-0"
        aria-label={`Enable ${hook.filename}`}
        aria-pressed={hook.enabled}
      >
        <span className={`neu-toggle__track ${hook.enabled ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
          <span className={`neu-toggle__knob ${hook.enabled ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
        </span>
      </button>
      {renaming ? (
        <span className="flex min-w-0 flex-1 items-center gap-1">
          <input
            type="text"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitRename();
              if (e.key === 'Escape' && !renameSaving) cancelRename();
            }}
            autoFocus
            disabled={renameSaving}
            className="min-w-0 flex-1 rounded border border-[var(--surface-border)] bg-[var(--surface-raised)] px-1 py-0.5 font-mono text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
          />
          {renameError && <span className="flex-shrink-0 text-xs text-theme-danger">{renameError}</span>}
        </span>
      ) : (
        <div className="flex min-w-0 basis-1/3 flex-col">
          <FilenameCell filename={hook.filename} />
        </div>
      )}
      {!readOnly && instanceId ? (
        <DescriptionCell hook={hook} instanceId={instanceId} onChanged={onChanged} readOnly={readOnly} />
      ) : (
        hook.description ? (
          <span className="min-w-0 flex-1 truncate text-xs text-[var(--text-muted)]">{hook.description}</span>
        ) : (
          <span className="min-w-0 flex-1" />
        )
      )}
      <span className="w-16 flex-shrink-0 text-right font-mono text-xs text-[var(--text-muted)]">
        {formatSize(hook.size)}
      </span>
      {!readOnly && instanceId && (
        <div className="relative flex flex-shrink-0 items-center">
          <input ref={fileInputRef} type="file" accept=".so" className="hidden" onChange={onReplaceFile} />
          <div className="flex items-center">
            <button type="button" onClick={handleDownload} aria-label={`Download ${hook.filename}`} className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]">
              <Download size={14} />
            </button>
            <button type="button" onClick={() => fileInputRef.current?.click()} aria-label={`Replace ${hook.filename}`} className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]">
              <RefreshCw size={14} />
            </button>
            <button type="button" onClick={startRename} disabled={renaming} aria-label={`Rename ${hook.filename}`} className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]">
              <Edit2 size={14} />
            </button>
            <button type="button" onClick={() => onDelete?.(hook)} aria-label={`Delete ${hook.filename}`} className="flex h-7 w-7 items-center justify-center rounded text-[var(--accent-danger)] hover:bg-[var(--surface-elevated)]">
              <Trash2 size={14} />
            </button>
          </div>
          {actionError && (
            <div className="absolute right-0 top-full z-20 mt-1 w-48 rounded border border-[var(--surface-border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs text-theme-danger shadow-lg">
              {actionError}
            </div>
          )}
        </div>
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
  return (
    <div
      className="flex min-h-10 items-center gap-3 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-raised)] px-3 py-2"
      data-testid={`hook-row-${hook.filename}`}
    >
      <div className="flex flex-shrink-0 items-center gap-1">
        <button
          type="button"
          disabled
          className="neu-toggle neu-toggle--sm cursor-not-allowed opacity-75"
          aria-label={`${hook.filename} is always active`}
          aria-pressed={true}
        >
          <span className="neu-toggle__track neu-toggle__track--on">
            <span className="neu-toggle__knob neu-toggle__knob--on" />
          </span>
        </button>
        <InfoTooltip text="System hooks are always active and cannot be disabled" size={12} />
      </div>
      <div className="min-w-0 flex-1">
        <FilenameCell filename={hook.filename} />
      </div>
      {hook.description && (
        <span className="flex-shrink-0 text-xs text-[var(--text-muted)]">{hook.description}</span>
      )}
      <span className="w-16 flex-shrink-0 text-right font-mono text-xs text-[var(--text-muted)]">
        {formatSize(hook.size)}
      </span>
    </div>
  );
}

export function MissingHookRow({ hook, onRemove }) {
  return (
    <div
      className="flex min-h-12 items-center gap-3 rounded-lg border border-theme-danger/40 bg-theme-danger/5 px-3 py-2.5"
      data-testid={`hook-row-missing-${hook.filename}`}
    >
      <span className="h-7 w-7 flex items-center justify-center text-theme-danger">
        <AlertTriangle size={15} />
      </span>
      <button
        type="button"
        onClick={() => onRemove(hook.filename)}
        className="neu-toggle neu-toggle--sm"
        aria-label={`Remove missing hook ${hook.filename}`}
        aria-pressed={true}
      >
        <span className="neu-toggle__track neu-toggle__track--on">
          <span className="neu-toggle__knob neu-toggle__knob--on" />
        </span>
      </button>
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
