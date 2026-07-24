import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { autoUpdate, flip, offset, shift, useFloating } from '@floating-ui/react-dom';
import { Download, Edit2, MoreVertical, RefreshCw, Trash2 } from 'lucide-react';
import { downloadInstanceHook, replaceInstanceHook } from '../../services/api';

export default function HookActionsMenu({ hook, instanceId, onChanged, onDelete, onRename }) {
  const [actionError, setActionError] = useState(null);
  const [open, setOpen] = useState(false);
  const fileInputRef = useRef(null);
  const { x, y, refs, strategy } = useFloating({
    placement: 'bottom-end',
    middleware: [
      offset(6),
      flip(),
      shift({ padding: 8 }),
    ],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    if (!open) return undefined;

    const closeOnOutsidePress = (event) => {
      const target = event.target;
      if (
        refs.reference.current?.contains(target)
        || refs.floating.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    };

    const closeOnEscape = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    document.addEventListener('pointerdown', closeOnOutsidePress, true);
    document.addEventListener('keydown', closeOnEscape);

    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePress, true);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open, refs.floating, refs.reference]);

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
      // Replacing an enabled hook's binary is a hook change: flag it so a running
      // instance is forced to restart on the next Save Configuration.
      onChanged?.({ hooksChanged: hook.enabled });
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
    <div className="relative flex justify-center">
      <input ref={fileInputRef} type="file" accept=".so" className="hidden" onChange={onReplaceFile} />
      <button
        ref={refs.setReference}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Actions for ${hook.filename}`}
        onClick={() => {
          setActionError(null);
          setOpen((value) => !value);
        }}
        className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
      >
        <MoreVertical size={16} />
      </button>
      {open && createPortal(
        <div
          ref={refs.setFloating}
          role="menu"
          style={{
            position: strategy,
            top: y ?? 0,
            left: x ?? 0,
          }}
          className="z-[10000] w-36 origin-top-right rounded-md border border-[var(--surface-border)] bg-[var(--surface-elevated)] py-1 shadow-lg focus:outline-none"
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              onClick={(e) => {
                e.stopPropagation();
                item.onClick();
                setOpen(false);
              }}
              className={`${item.danger ? 'text-[var(--accent-danger)]' : 'text-[var(--text-secondary)]'} flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-black/10 dark:hover:bg-white/10`}
            >
              <item.icon size={14} /> {item.label}
            </button>
          ))}
        </div>,
        document.body,
      )}
      {actionError && (
        <div className="absolute right-0 z-20 mt-1 w-48 rounded border border-[var(--surface-border)] bg-[var(--surface-elevated)] px-3 py-2 text-xs text-theme-danger shadow-lg">
          {actionError}
        </div>
      )}
    </div>
  );
}
