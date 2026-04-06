import { useState } from 'react';

/**
 * Shared hook for view chat logs modal state management.
 * @returns {{
 *   selectedInstanceForChatLogs: object|null,
 *   isViewChatLogsModalOpen: boolean,
 *   openViewChatLogs: (instance: object) => void,
 *   closeViewChatLogs: () => void,
 * }}
 */
export function useViewChatLogs() {
    const [isViewChatLogsModalOpen, setIsViewChatLogsModalOpen] = useState(false);
    const [selectedInstanceForChatLogs, setSelectedInstanceForChatLogs] = useState(null);

    const openViewChatLogs = (instance) => {
        setSelectedInstanceForChatLogs(instance);
        setIsViewChatLogsModalOpen(true);
    };

    const closeViewChatLogs = () => {
        setIsViewChatLogsModalOpen(false);
        setSelectedInstanceForChatLogs(null);
    };

    return { selectedInstanceForChatLogs, isViewChatLogsModalOpen, openViewChatLogs, closeViewChatLogs };
}
