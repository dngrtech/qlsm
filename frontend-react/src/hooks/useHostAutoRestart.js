import { useState, useCallback } from 'react';
import { configureAutoRestart } from '../services/api';

export function useHostAutoRestart(showSuccess, showError, onSuccess) {
    const [isAutoRestartModalOpen, setIsAutoRestartModalOpen] = useState(false);
    const [hostForAutoRestart, setHostForAutoRestart] = useState(null);

    const openAutoRestartModal = useCallback((host) => {
        setHostForAutoRestart(host);
        setIsAutoRestartModalOpen(true);
    }, []);

    const closeAutoRestartModal = useCallback(() => {
        setIsAutoRestartModalOpen(false);
        setHostForAutoRestart(null);
    }, []);

    const handleAutoRestartSubmit = useCallback(async (hostId, scheduleStr) => {
        if (!hostForAutoRestart) return;

        try {
            const response = await configureAutoRestart(hostForAutoRestart.id, scheduleStr);
            showSuccess(response.message || `Auto-restart schedule updated for host`);
            if (onSuccess) onSuccess();
            closeAutoRestartModal();
        } catch (error) {
            console.error("Failed to update auto-restart schedule:", error);
            showError(error.error?.message || error.message || "Failed to update schedule");
        }
    }, [hostForAutoRestart, showSuccess, showError, onSuccess, closeAutoRestartModal]);

    return {
        isAutoRestartModalOpen,
        hostForAutoRestart,
        openAutoRestartModal,
        closeAutoRestartModal,
        handleAutoRestartSubmit
    };
}
