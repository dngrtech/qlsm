// frontend-react/src/components/hosts/SortableHostCard.jsx
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { motion } from 'framer-motion';
import { GripVertical } from 'lucide-react';

export default function SortableHostCard({ id, children }) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
    };

    return (
        <motion.div
            ref={setNodeRef}
            style={style}
            layout={!isDragging}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className={isDragging ? 'host-card-dragging' : ''}
        >
            {children({ dragHandleProps: { attributes, listeners } })}
        </motion.div>
    );
}

export function HostCardDragOverlay({ host }) {
    return (
        <div className="host-card-overlay">
            <div className="server-grid py-[18px]">
                <div className="host-row-first-col">
                    <div className="host-drag-handle">
                        <GripVertical size={14} />
                    </div>
                </div>
                <span
                    className="text-[15px] font-semibold truncate"
                    style={{ color: 'var(--accent-primary)' }}
                >
                    {host.name}
                </span>
            </div>
        </div>
    );
}
