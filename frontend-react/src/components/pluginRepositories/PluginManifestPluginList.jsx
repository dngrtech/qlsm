import { useCallback, useMemo, useState } from 'react';
import {
  closestCenter, DndContext, DragOverlay, KeyboardSensor, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  Plus, Trash2, GripVertical, ArrowDownAZ,
} from 'lucide-react';

// One row in the plugin list: a drag handle (reorder), the select area, and
// a remove button -- three separate controls rather than one nested inside
// another, so the drag listeners never fight the click handler.
function SortablePluginRow({ plugin, isSelected, errorBucket, onSelect, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: plugin._key });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };
  const displayName = plugin.label || plugin.filename || 'plugin';

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-1 px-2 py-2 text-sm border-b border-[var(--surface-border)] last:border-b-0 transition-colors ${
        isSelected ? 'bg-black/[0.05] dark:bg-white/[0.06]' : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.03]'
      }`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        aria-label={`Reorder ${displayName}`}
        className="flex-shrink-0 p-1 rounded text-slate-500 hover:text-slate-300 cursor-grab touch-none"
      >
        <GripVertical size={14} />
      </button>
      <button type="button" onClick={onSelect} className="flex items-center gap-2 min-w-0 flex-1 text-left">
        <span
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            errorBucket?.errors ? 'bg-red-500' : errorBucket?.warnings ? 'bg-amber-500' : 'bg-emerald-500'
          }`}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[var(--text-primary)]">{plugin.label || plugin.filename || '(untitled)'}</span>
          <span className="block truncate font-mono text-[11px] text-[var(--text-muted)]">{plugin.filename || '—'}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${displayName}`}
        className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-500/10 flex-shrink-0"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}

// What follows the cursor while a row is being dragged -- a static snapshot,
// so it doesn't need (and shouldn't have) its own drag listeners.
function PluginRowOverlay({ plugin }) {
  return (
    <div className="flex items-center gap-1 px-2 py-2 text-sm bg-[var(--surface-raised)] border border-[var(--surface-border)] rounded-md shadow-lg">
      <span className="flex-shrink-0 p-1 text-slate-400"><GripVertical size={14} /></span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[var(--text-primary)]">{plugin.label || plugin.filename || '(untitled)'}</span>
        <span className="block truncate font-mono text-[11px] text-[var(--text-muted)]">{plugin.filename || '—'}</span>
      </span>
    </div>
  );
}

/**
 * The manifest editor's left pane: the draggable plugin list plus Sort A–Z
 * and Add Plugin.
 *
 * Reordering (drag or Sort A–Z) is handed back through `onReorder` rather
 * than done here, because the parent has to recompute which row is selected
 * from where the moved plugin landed.
 */
function PluginManifestPluginList({
  plugins, selectedIndex, issuesByPlugin, onSelect, onRemove, onAdd, onReorder,
}) {
  const [activeKey, setActiveKey] = useState(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const itemKeys = useMemo(() => plugins.map((p) => p._key), [plugins]);
  const activePlugin = useMemo(
    () => (activeKey ? plugins.find((p) => p._key === activeKey) : null),
    [activeKey, plugins],
  );

  const handleDragStart = useCallback((event) => {
    setActiveKey(event.active.id);
  }, []);
  const handleDragEnd = useCallback((event) => {
    setActiveKey(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = plugins.findIndex((p) => p._key === active.id);
    const newIndex = plugins.findIndex((p) => p._key === over.id);
    if (oldIndex === -1 || newIndex === -1) return;
    onReorder(arrayMove(plugins, oldIndex, newIndex));
  }, [plugins, onReorder]);
  const handleDragCancel = useCallback(() => {
    setActiveKey(null);
  }, []);

  const handleSortAlpha = () => {
    const sorted = [...plugins].sort((a, b) => (
      (a.label || a.filename || '').localeCompare(b.label || b.filename || '', undefined, { sensitivity: 'base' })
    ));
    onReorder(sorted);
  };

  return (
    <div className="flex flex-col min-h-0 flex-1 border border-[var(--surface-border)] rounded-lg overflow-hidden">
      <div className="flex-1 overflow-y-auto scrollbar-thin divide-y divide-[var(--surface-border)]">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
          <SortableContext items={itemKeys} strategy={verticalListSortingStrategy}>
            {plugins.map((p, i) => (
              <SortablePluginRow
                key={p._key}
                plugin={p}
                isSelected={i === selectedIndex}
                errorBucket={issuesByPlugin.get(i)}
                onSelect={() => onSelect(i)}
                onRemove={() => onRemove(i)}
              />
            ))}
          </SortableContext>
          <DragOverlay dropAnimation={null}>
            {activePlugin ? <PluginRowOverlay plugin={activePlugin} /> : null}
          </DragOverlay>
        </DndContext>
        {plugins.length === 0 && (
          <p className="text-sm text-[var(--text-muted)] p-3">No plugins yet.</p>
        )}
      </div>
      <div className="p-2 border-t border-[var(--surface-border)] flex-shrink-0 flex gap-2">
        <button
          type="button"
          onClick={handleSortAlpha}
          disabled={plugins.length < 2}
          title="Sort plugins A to Z by label"
          className="btn btn-secondary flex-1 justify-center !px-2"
        >
          <ArrowDownAZ className="w-4 h-4" />
          Sort A–Z
        </button>
        <button type="button" onClick={onAdd} className="btn btn-secondary flex-1 justify-center !px-2">
          <Plus className="w-4 h-4" />
          Add Plugin
        </button>
      </div>
    </div>
  );
}

export default PluginManifestPluginList;
