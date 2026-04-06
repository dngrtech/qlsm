import { useState, useMemo, useCallback } from 'react';
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    DragOverlay,
} from '@dnd-kit/core';
import {
    SortableContext,
    verticalListSortingStrategy,
    arrayMove,
    sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import SortableInstanceRow, { InstanceRowOverlay } from './SortableInstanceRow';

const restrictToVerticalAxis = ({ transform }) => ({
    ...transform,
    x: 0,
});

export default function SortableInstanceList({
    instances,
    onOrderChange,
    renderInstanceContent,
}) {
    const [activeId, setActiveId] = useState(null);

    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: { distance: 4 },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    const itemIds = useMemo(
        () => instances.map((inst) => inst.id),
        [instances]
    );

    const activeInstance = useMemo(
        () => (activeId ? instances.find((i) => i.id === activeId) : null),
        [activeId, instances]
    );

    const handleDragStart = useCallback((event) => {
        setActiveId(event.active.id);
    }, []);

    const handleDragEnd = useCallback(
        (event) => {
            setActiveId(null);
            const { active, over } = event;
            if (!over || active.id === over.id) return;

            const oldIndex = instances.findIndex((i) => i.id === active.id);
            const newIndex = instances.findIndex((i) => i.id === over.id);
            if (oldIndex === -1 || newIndex === -1) return;

            const reordered = arrayMove(instances, oldIndex, newIndex);
            onOrderChange(reordered);
        },
        [instances, onOrderChange]
    );

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
            modifiers={[restrictToVerticalAxis]}
        >
            <SortableContext
                items={itemIds}
                strategy={verticalListSortingStrategy}
            >
                {instances.map((inst) => (
                    <SortableInstanceRow key={inst.id} id={inst.id}>
                        {renderInstanceContent(inst)}
                    </SortableInstanceRow>
                ))}
            </SortableContext>

            <DragOverlay dropAnimation={null}>
                {activeInstance ? (
                    <InstanceRowOverlay>
                        {renderInstanceContent(activeInstance)}
                    </InstanceRowOverlay>
                ) : null}
            </DragOverlay>
        </DndContext>
    );
}
