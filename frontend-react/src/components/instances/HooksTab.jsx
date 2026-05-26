import { useEffect, useMemo, useRef, useState } from 'react';
import { closestCenter, DndContext } from '@dnd-kit/core';
import { arrayMove, SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { deleteInstanceHook, fetchInstanceHooks, saveInstanceHooks, uploadInstanceHook } from '../../services/api';
import HookRow, { MissingHookRow, ReadOnlyHookRow, SortableHookRow } from './HookRow';

function errorMessage(error, fallback) {
  return error?.error?.message || error?.message || fallback;
}

export default function HooksTab({ instanceId, draftId, onApplied }) {
  const uploadRef = useRef(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [available, setAvailable] = useState([]);
  const [enabledOrder, setEnabledOrder] = useState([]);
  const [initialEnabled, setInitialEnabled] = useState([]);
  const [systemHooks, setSystemHooks] = useState([]);
  const [applying, setApplying] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [missingHooks, setMissingHooks] = useState([]);
  const [initialMissing, setInitialMissing] = useState([]);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleteError, setDeleteError] = useState(null);

  const reload = () => setReloadKey((k) => k + 1);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchInstanceHooks(instanceId, draftId)
      .then((data) => {
        if (cancelled) return;
        const all = data.available || [];
        const enabled = all
          .filter((hook) => hook.enabled && !hook.missing)
          .sort((a, b) => a.order - b.order)
          .map((hook) => hook.filename);
        const missing = all.filter((hook) => hook.missing).map((hook) => hook.filename);
        setAvailable(all.filter((hook) => !hook.missing));
        setEnabledOrder(enabled);
        setInitialEnabled(enabled);
        setMissingHooks(missing);
        setInitialMissing(missing);
        setSystemHooks(data.system_hooks_active || []);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Failed to load hooks.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [instanceId, draftId, reloadKey]);

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
  const removeMissingHook = (filename) => {
    setMissingHooks((current) => current.filter((f) => f !== filename));
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadInstanceHook(instanceId, file);
      reload();
    } catch (err) {
      setError(errorMessage(err, 'Upload failed.'));
    } finally {
      setUploading(false);
    }
  };

  const confirmDelete = async () => {
    setDeleteError(null);
    try {
      await deleteInstanceHook(instanceId, pendingDelete.filename);
      setPendingDelete(null);
      reload();
    } catch (err) {
      setDeleteError(errorMessage(err, 'Delete failed.'));
    }
  };

  const dirty = useMemo(
    () => enabledOrder.length !== initialEnabled.length
      || enabledOrder.some((filename, index) => initialEnabled[index] !== filename)
      || missingHooks.length !== initialMissing.length,
    [enabledOrder, initialEnabled, missingHooks, initialMissing],
  );

  const toggleHook = (filename) => {
    setEnabledOrder((current) => (
      current.includes(filename)
        ? current.filter((item) => item !== filename)
        : [...current, filename]
    ));
  };

  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return;
    setEnabledOrder((current) => {
      const oldIndex = current.indexOf(active.id);
      const newIndex = current.indexOf(over.id);
      if (oldIndex === -1 || newIndex === -1) return current;
      return arrayMove(current, oldIndex, newIndex);
    });
  };

  const handleCancel = () => {
    setEnabledOrder(initialEnabled);
    setMissingHooks(initialMissing);
    setError(null);
  };

  const handleApply = async () => {
    setApplying(true);
    setError(null);
    try {
      await saveInstanceHooks(instanceId, enabledOrder, draftId);
      setInitialEnabled(enabledOrder);
      setInitialMissing(missingHooks);
      onApplied?.();
    } catch (err) {
      setError(errorMessage(err, 'Failed to save hooks.'));
    } finally {
      setApplying(false);
    }
  };

  if (loading) {
    return <div className="p-4 text-sm text-[var(--text-muted)]">Loading hooks...</div>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {error && (
        <div className="border-b border-[var(--surface-border)] px-4 py-2 text-sm text-theme-danger">
          {error}
        </div>
      )}
      {systemHooks.length > 0 && (
        <div className="border-b border-[var(--surface-border)]">
          <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            System hooks
          </div>
          {systemHooks.map((hook) => (
            <ReadOnlyHookRow key={hook.filename} hook={hook} />
          ))}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex items-center justify-between border-b border-[var(--surface-border)] px-4 py-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">User hooks</span>
          {!draftId && instanceId && (
            <>
              <input ref={uploadRef} type="file" accept=".so" className="hidden" onChange={handleUpload} />
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
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={enabledOrder} strategy={verticalListSortingStrategy}>
            {enabledRows.map((hook) => (
              <SortableHookRow
                key={hook.filename}
                hook={hook}
                onToggle={toggleHook}
                instanceId={instanceId}
                onChanged={reload}
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
            onChanged={reload}
            onDelete={setPendingDelete}
          />
        ))}
        {missingHooks.map((filename) => (
          <MissingHookRow
            key={filename}
            hook={{ filename }}
            onRemove={removeMissingHook}
          />
        ))}
        {available.length === 0 && missingHooks.length === 0 && (
          <div className="px-4 py-8 text-sm text-[var(--text-muted)]">
            No hook files found.
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2 border-t border-[var(--surface-border)] px-4 py-3">
        <button
          type="button"
          onClick={handleCancel}
          disabled={!dirty || applying}
          className="btn btn-secondary"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={!dirty || applying}
          className="btn btn-primary"
        >
          {applying ? 'Applying...' : 'Apply & Restart'}
        </button>
      </div>
      {pendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div role="dialog" aria-modal="true" className="w-80 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-elevated)] p-6 shadow-xl">
            <h3 className="mb-2 font-semibold text-[var(--text-primary)]">Delete hook?</h3>
            <p className="mb-4 text-sm text-[var(--text-muted)]">
              <span className="font-mono text-[var(--text-primary)]">{pendingDelete.filename}</span> will be permanently deleted.
            </p>
            {deleteError && <p className="mb-3 text-sm text-theme-danger">{deleteError}</p>}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => { setPendingDelete(null); setDeleteError(null); }}
                className="btn btn-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                className="rounded px-3 py-1.5 text-sm font-medium bg-red-600 text-white hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
