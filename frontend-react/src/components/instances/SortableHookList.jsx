import { useCallback, useMemo, useState } from 'react';
import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { HookRowOverlay, SortableHookRow } from './HookRow';

function restrictToHookBoundary(boundaryRef, topBoundaryRef) {
  return ({ activeNodeRect, draggingNodeRect, overlayNodeRect, transform }) => {
    const boundary = boundaryRef?.current;
    const topBoundaryEl = topBoundaryRef?.current;
    const nodeRect = overlayNodeRect || draggingNodeRect || activeNodeRect;
    if (!boundary || !nodeRect) {
      return { ...transform, x: 0 };
    }

    const boundaryRect = boundary.getBoundingClientRect();
    const topBoundary = topBoundaryEl?.getBoundingClientRect().top ?? boundaryRect.top;
    let y = transform.y;

    const nextTop = nodeRect.top + y;
    if (nextTop < topBoundary) {
      y += topBoundary - nextTop;
    }

    const clampedBottom = nodeRect.bottom + y;
    if (clampedBottom > boundaryRect.bottom) {
      y -= clampedBottom - boundaryRect.bottom;
    }

    return { ...transform, x: 0, y };
  };
}

export default function SortableHookList({
  hooks,
  onOrderChange,
  onToggle,
  instanceId,
  onChanged,
  onDelete,
  boundaryRef,
  topBoundaryRef,
}) {
  const [activeId, setActiveId] = useState(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 4 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const itemIds = useMemo(() => hooks.map((hook) => hook.filename), [hooks]);
  const activeHook = useMemo(
    () => (activeId ? hooks.find((hook) => hook.filename === activeId) : null),
    [activeId, hooks],
  );
  const modifiers = useMemo(
    () => [restrictToHookBoundary(boundaryRef, topBoundaryRef)],
    [boundaryRef, topBoundaryRef],
  );

  const handleDragStart = useCallback((event) => {
    setActiveId(event.active.id);
  }, []);

  const handleDragEnd = useCallback((event) => {
    setActiveId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = hooks.findIndex((hook) => hook.filename === active.id);
    const newIndex = hooks.findIndex((hook) => hook.filename === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    onOrderChange(arrayMove(hooks, oldIndex, newIndex));
  }, [hooks, onOrderChange]);

  const handleDragCancel = useCallback(() => {
    setActiveId(null);
  }, []);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
      modifiers={modifiers}
    >
      <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
        {hooks.map((hook) => (
          <SortableHookRow
            key={hook.filename}
            hook={hook}
            onToggle={onToggle}
            instanceId={instanceId}
            onChanged={onChanged}
            onDelete={onDelete}
          />
        ))}
      </SortableContext>

      <DragOverlay dropAnimation={null} modifiers={modifiers}>
        {activeHook ? <HookRowOverlay hook={activeHook} /> : null}
      </DragOverlay>
    </DndContext>
  );
}
