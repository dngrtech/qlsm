import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { closestCenter, DndContext } from '@dnd-kit/core';
import { arrayMove, SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { deleteInstanceHook, fetchInstanceHooks, saveInstanceHooks, uploadInstanceHook } from '../../services/api';
import HookRow, { MissingHookRow, ReadOnlyHookRow, SortableHookRow } from './HookRow';
import ConfirmationModal from '../ConfirmationModal';

function errorMessage(error, fallback) {
  return error?.error?.message || error?.message || fallback;
}

export default function HooksTab({ instanceId, draftId, onApplied }) {
  const uploadRef = useRef(null);
  const scrollRef = useRef(null);
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
  const [hasReplacedHook, setHasReplacedHook] = useState(false);

  const reload = () => setReloadKey((k) => k + 1);

  // Reset to blank loading state only when the target instance/draft changes.
  useEffect(() => {
    setLoading(true);
    setError(null);
    setAvailable([]);
    setEnabledOrder([]);
    setInitialEnabled([]);
    setSystemHooks([]);
    setMissingHooks([]);
    setInitialMissing([]);
    setHasReplacedHook(false);
  }, [instanceId, draftId]);

  // Fetch (or silently re-fetch on reload). Does NOT set loading=true so
  // uploads/deletes refresh without blanking the tab.
  useEffect(() => {
    let cancelled = false;
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
    const isReplacement = available.some((h) => h.filename === file.name);
    setUploading(true);
    setError(null);
    try {
      await uploadInstanceHook(instanceId, file);
      if (isReplacement) setHasReplacedHook(true);
      reload();
    } catch (err) {
      setError(errorMessage(err, 'Upload failed.'));
    } finally {
      setUploading(false);
    }
  };

  const confirmDelete = async () => {
    try {
      await deleteInstanceHook(instanceId, pendingDelete.filename);
      reload();
    } catch (err) {
      setError(errorMessage(err, 'Delete failed.'));
    }
  };

  const dirty = useMemo(
    () => hasReplacedHook
      || enabledOrder.length !== initialEnabled.length
      || enabledOrder.some((filename, index) => initialEnabled[index] !== filename)
      || missingHooks.length !== initialMissing.length,
    [hasReplacedHook, enabledOrder, initialEnabled, missingHooks, initialMissing],
  );

  const restrictToTab = useCallback(({ transform, draggingNodeRect }) => {
    if (!scrollRef.current || !draggingNodeRect) return { ...transform, x: 0 };
    const bounds = scrollRef.current.getBoundingClientRect();
    const minY = bounds.top - draggingNodeRect.top;
    const maxY = bounds.bottom - draggingNodeRect.bottom;
    return { ...transform, x: 0, y: Math.min(Math.max(transform.y, minY), maxY) };
  }, []);

  const toggleHook = (filename) => {
    const doUpdate = () => setEnabledOrder((current) => (
      current.includes(filename)
        ? current.filter((item) => item !== filename)
        : [...current, filename]
    ));
    if (document.startViewTransition) {
      document.startViewTransition(() => flushSync(doUpdate));
    } else {
      doUpdate();
    }
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
    setHasReplacedHook(false);
    setError(null);
  };

  const handleApply = async () => {
    setApplying(true);
    setError(null);
    try {
      await saveInstanceHooks(instanceId, enabledOrder, draftId);
      setInitialEnabled(enabledOrder);
      setInitialMissing(missingHooks);
      setHasReplacedHook(false);
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
        <div className="flex flex-col gap-2 px-3 pb-17">
          <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd} modifiers={[restrictToTab]}>
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
            <div className="py-6 text-center text-sm text-[var(--text-muted)]">
              No hook files found.
            </div>
          )}
        </div>
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
