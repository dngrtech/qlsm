import { useEffect, useMemo, useState } from 'react';
import { closestCenter, DndContext } from '@dnd-kit/core';
import { arrayMove, SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { fetchInstanceHooks, saveInstanceHooks } from '../../services/api';
import HookRow, { SortableHookRow } from './HookRow';

function errorMessage(error, fallback) {
  return error?.error?.message || error?.message || fallback;
}

export default function HooksTab({ instanceId, draftId, onApplied }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [available, setAvailable] = useState([]);
  const [enabledOrder, setEnabledOrder] = useState([]);
  const [initialEnabled, setInitialEnabled] = useState([]);
  const [systemHooks, setSystemHooks] = useState([]);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchInstanceHooks(instanceId, draftId)
      .then((data) => {
        if (cancelled) return;
        const enabled = [...(data.available || [])]
          .filter((hook) => hook.enabled)
          .sort((a, b) => a.order - b.order)
          .map((hook) => hook.filename);
        setAvailable(data.available || []);
        setEnabledOrder(enabled);
        setInitialEnabled(enabled);
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
  }, [instanceId, draftId]);

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
  const dirty = useMemo(
    () => enabledOrder.length !== initialEnabled.length
      || enabledOrder.some((filename, index) => initialEnabled[index] !== filename),
    [enabledOrder, initialEnabled],
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
    setError(null);
  };

  const handleApply = async () => {
    setApplying(true);
    setError(null);
    try {
      await saveInstanceHooks(instanceId, enabledOrder);
      setInitialEnabled(enabledOrder);
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
        <div className="border-b border-[var(--surface-border)] px-4 py-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            System hooks
          </h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {systemHooks.map((name) => (
              <span key={name} className="rounded border border-[var(--surface-border)] px-2 py-1 font-mono text-xs">
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="border-b border-[var(--surface-border)] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          User hooks
        </div>
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={enabledOrder} strategy={verticalListSortingStrategy}>
            {enabledRows.map((hook) => (
              <SortableHookRow key={hook.filename} hook={hook} onToggle={toggleHook} />
            ))}
          </SortableContext>
        </DndContext>
        {disabledRows.map((hook) => (
          <HookRow key={hook.filename} hook={hook} onToggle={toggleHook} />
        ))}
        {available.length === 0 && (
          <div className="px-4 py-8 text-sm text-[var(--text-muted)]">
            No shared objects found in scripts.
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
    </div>
  );
}
