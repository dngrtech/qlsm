import { useState } from 'react';

/**
 * Shared hook for view logs modal state management.
 * @returns {{
 *   selectedInstanceForLogs: object|null,
 *   isViewLogsModalOpen: boolean,
 *   openViewLogs: (instance: object) => void,
 *   closeViewLogs: () => void,
 * }}
 */
export function useViewLogs() {
    const [isViewLogsModalOpen, setIsViewLogsModalOpen] = useState(false);
    const [selectedInstanceForLogs, setSelectedInstanceForLogs] = useState(null);

    const openViewLogs = (instance) => {
        setSelectedInstanceForLogs(instance);
        setIsViewLogsModalOpen(true);
    };

    const closeViewLogs = () => {
        setIsViewLogsModalOpen(false);
        setSelectedInstanceForLogs(null);
    };

    return { selectedInstanceForLogs, isViewLogsModalOpen, openViewLogs, closeViewLogs };
}
