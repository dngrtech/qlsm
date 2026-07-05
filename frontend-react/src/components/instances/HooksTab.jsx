import { useCallback, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { closestCenter, DndContext } from '@dnd-kit/core';
import { arrayMove, SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { deleteInstanceHook, uploadInstanceHook } from '../../services/api';
import HookRow, { MissingHookRow, ReadOnlyHookRow, SortableHookRow } from './HookRow';
import ConfirmationModal from '../ConfirmationModal';

function errorMessage(error, fallback) {
  return error?.error?.message || error?.message || fallback;
}

export default function HooksTab({
  instanceId,
  available = [],
  missing = [],
  systemHooks = [],
  enabledOrder = [],
  dirty = false,
  onToggleHook,
  onReorderHooks,
  onRemoveMissing,
  onRefresh,
}) {
  const uploadRef = useRef(null);
  const scrollRef = useRef(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  const enabledSet = useMemo(() => new Set(enabledOrder), [enabledOrder]);
  const enabledRows = useMemo(
    () => enabledOrder
      .map((filename) => available.find((hook) => hook.filename === filename))
      .filter(Boolean)
      .map((hook) => ({ ...hook, enabled: true })),
    [available, enabledOrder],
  );
  const disabledRows = useMemo(
    () => available
      .filter((hook) => !enabledSet.has(hook.filename))
      .map((hook) => ({ ...hook, enabled: false, order: null }))
      .sort((a, b) => a.filename.localeCompare(b.filename)),
    [available, enabledSet],
  );
  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadInstanceHook(instanceId, file);
      onRefresh?.();
    } catch (err) {
      setError(errorMessage(err, 'Upload failed.'));
    } finally {
      setUploading(false);
    }
  };

  const confirmDelete = async () => {
    try {
      await deleteInstanceHook(instanceId, pendingDelete.filename);
      setPendingDelete(null);
      onRefresh?.();
    } catch (err) {
      setError(errorMessage(err, 'Delete failed.'));
    }
  };

  const restrictToTab = useCallback(({ transform, draggingNodeRect }) => {
    if (!scrollRef.current || !draggingNodeRect) return { ...transform, x: 0 };
    const bounds = scrollRef.current.getBoundingClientRect();
    const minY = bounds.top - draggingNodeRect.top;
    const maxY = bounds.bottom - draggingNodeRect.bottom;
    return { ...transform, x: 0, y: Math.min(Math.max(transform.y, minY), maxY) };
  }, []);

  const toggleHook = (filename) => {
    const doUpdate = () => onToggleHook?.(filename);
    if (document.startViewTransition) {
      document.startViewTransition(() => flushSync(doUpdate));
    } else {
      doUpdate();
    }
  };

  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return;
    const oldIndex = enabledOrder.indexOf(active.id);
    const newIndex = enabledOrder.indexOf(over.id);
    if (oldIndex === -1 || newIndex === -1) return;
    onReorderHooks?.(arrayMove(enabledOrder, oldIndex, newIndex));
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {error && (
        <div className="border-b border-[var(--surface-border)] px-4 py-2 text-sm text-theme-danger">
          {error}
        </div>
      )}
      {dirty && (
        <div className="border-b border-[var(--surface-border)] px-4 py-2 text-sm text-[var(--accent-warning)]">
          Unsaved hook changes — click Save Configuration to apply.
        </div>
      )}
      {systemHooks.length > 0 && (
        <div>
          <div className="px-4 pt-3 pb-3 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            System hooks
          </div>
          <div className="flex flex-col gap-2 px-3">
            {systemHooks.map((hook) => (
              <ReadOnlyHookRow key={hook.filename} hook={hook} />
            ))}
          </div>
        </div>
      )}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex items-center justify-between px-4 pt-2 pb-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">User hooks</span>
          {instanceId && (
            <>
              <input ref={uploadRef} data-testid="hook-upload-input" type="file" accept=".so" className="hidden" onChange={handleUpload} />
              <button
                type="button"
                onClick={() => uploadRef.current?.click()}
                disabled={uploading}
                className="btn btn-secondary text-xs"
              >
                {uploading ? 'Uploading…' : 'Upload .so'}
              </button>
            </>
          )}
        </div>
        <div className="flex flex-col gap-2 px-3 pb-17">
          <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd} modifiers={[restrictToTab]}>
            <SortableContext items={enabledOrder} strategy={verticalListSortingStrategy}>
              {enabledRows.map((hook) => (
                <SortableHookRow
                  key={hook.filename}
                  hook={hook}
                  onToggle={toggleHook}
                  instanceId={instanceId}
                  onChanged={onRefresh}
                  onDelete={setPendingDelete}
                />
              ))}
            </SortableContext>
          </DndContext>
          {disabledRows.map((hook) => (
            <HookRow
              key={hook.filename}
              hook={hook}
              onToggle={toggleHook}
              instanceId={instanceId}
              onChanged={onRefresh}
              onDelete={setPendingDelete}
            />
          ))}
          {missing.map((filename) => (
            <MissingHookRow
              key={filename}
              hook={{ filename }}
              onRemove={onRemoveMissing}
            />
          ))}
          {available.length === 0 && missing.length === 0 && (
            <div className="py-6 text-center text-sm text-[var(--text-muted)]">
              No hook files found.
            </div>
          )}
        </div>
      </div>
      <ConfirmationModal
        isOpen={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
        title="Delete hook?"
        message={<>Delete <span className="font-mono text-theme-primary">{pendingDelete?.filename}</span>? This cannot be undone.</>}
        confirmButtonText="Delete"
        confirmButtonVariant="danger"
        zIndexClass="z-[60]"
      />
    </div>
  );
}
