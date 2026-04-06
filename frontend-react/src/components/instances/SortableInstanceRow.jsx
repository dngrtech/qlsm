import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { motion } from 'framer-motion';
import { GripVertical } from 'lucide-react';

export default function SortableInstanceRow({ id, children }) {
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
            layout
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className={isDragging ? 'instance-row-dragging' : ''}
        >
            <div className="server-grid py-3.5 transition-colors instance-row instance-row-border instance-row-sortable">
                <div
                    className="drag-handle"
                    {...attributes}
                    {...listeners}
                >
                    <GripVertical size={14} />
                </div>
                {children}
            </div>
        </motion.div>
    );
}

export function InstanceRowOverlay({ children }) {
    return (
        <div className="instance-row-overlay">
            <div className="drag-handle" style={{ opacity: 1 }}>
                <GripVertical size={14} />
            </div>
            {children}
        </div>
    );
}
