// frontend-react/src/components/hosts/SortableHostList.jsx
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
import SortableHostCard, { HostCardDragOverlay } from './SortableHostCard';

const restrictToVerticalAxis = ({ transform }) => ({
    ...transform,
    x: 0,
});

const MODIFIERS = [restrictToVerticalAxis];

export default function SortableHostList({ hosts, onOrderChange, renderHostCard }) {
    const [activeId, setActiveId] = useState(null);

    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: { distance: 4 },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    const itemIds = useMemo(() => hosts.map((h) => h.id), [hosts]);

    const activeHost = useMemo(
        () => (activeId ? hosts.find((h) => h.id === activeId) : null),
        [activeId, hosts]
    );

    const handleDragStart = useCallback((event) => {
        setActiveId(event.active.id);
    }, []);

    const handleDragEnd = useCallback(
        (event) => {
            setActiveId(null);
            const { active, over } = event;
            if (!over || active.id === over.id) return;

            const oldIndex = hosts.findIndex((h) => h.id === active.id);
            const newIndex = hosts.findIndex((h) => h.id === over.id);
            if (oldIndex === -1 || newIndex === -1) return;

            onOrderChange(arrayMove(hosts, oldIndex, newIndex));
        },
        [hosts, onOrderChange]
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
            modifiers={MODIFIERS}
        >
            <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
                {hosts.map((host) => (
                    <SortableHostCard key={host.id} id={host.id}>
                        {({ dragHandleProps }) => renderHostCard(host, dragHandleProps)}
                    </SortableHostCard>
                ))}
            </SortableContext>

            <DragOverlay dropAnimation={null}>
                {activeHost ? <HostCardDragOverlay host={activeHost} /> : null}
            </DragOverlay>
        </DndContext>
    );
}
