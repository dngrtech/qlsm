import { useState } from 'react';

/**
 * Shared hook for view MinQLX logs modal state management.
 * @returns {{
 *   selectedInstanceForMinqlxLogs: object|null,
 *   isViewMinqlxLogsModalOpen: boolean,
 *   openViewMinqlxLogs: (instance: object) => void,
 *   closeViewMinqlxLogs: () => void,
 * }}
 */
export function useViewMinqlxLogs() {
    const [isViewMinqlxLogsModalOpen, setIsViewMinqlxLogsModalOpen] = useState(false);
    const [selectedInstanceForMinqlxLogs, setSelectedInstanceForMinqlxLogs] = useState(null);

    const openViewMinqlxLogs = (instance) => {
        setSelectedInstanceForMinqlxLogs(instance);
        setIsViewMinqlxLogsModalOpen(true);
    };

    const closeViewMinqlxLogs = () => {
        setIsViewMinqlxLogsModalOpen(false);
        setSelectedInstanceForMinqlxLogs(null);
    };

    return { selectedInstanceForMinqlxLogs, isViewMinqlxLogsModalOpen, openViewMinqlxLogs, closeViewMinqlxLogs };
}
