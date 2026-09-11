import { useState, useCallback } from 'react';
import { checkPluginUpdates, applyPluginUpdates } from '../services/api';

export function useCheckForUpdates(showSuccess, showError, onSuccess) {
    const [isUpdatesModalOpen, setIsUpdatesModalOpen] = useState(false);
    const [hostForUpdates, setHostForUpdates] = useState(null);
    const [isChecking, setIsChecking] = useState(false);
    const [checkResult, setCheckResult] = useState(null);
    const [checkError, setCheckError] = useState(null);

    const openUpdatesModal = useCallback(async (host) => {
        setHostForUpdates(host);
        setIsUpdatesModalOpen(true);
        setCheckResult(null);
        setCheckError(null);
        setIsChecking(true);
        try {
            const response = await checkPluginUpdates(host.id);
            setCheckResult(response.data);
        } catch (error) {
            setCheckError(error.error?.message || error.message || 'Failed to check for updates');
        } finally {
            setIsChecking(false);
        }
    }, []);

    const closeUpdatesModal = useCallback(() => {
        setIsUpdatesModalOpen(false);
        setHostForUpdates(null);
        setCheckResult(null);
        setCheckError(null);
    }, []);

    const handleApplyUpdates = useCallback(async (payload) => {
        if (!hostForUpdates) return;

        try {
            const response = await applyPluginUpdates(hostForUpdates.id, payload);
            showSuccess(response.message || 'Plugin updates queued');
            if (onSuccess) onSuccess();
            closeUpdatesModal();
        } catch (error) {
            console.error("Failed to apply plugin updates:", error);
            showError(error.error?.message || error.message || "Failed to apply plugin updates");
        }
    }, [hostForUpdates, showSuccess, showError, onSuccess, closeUpdatesModal]);

    return {
        isUpdatesModalOpen,
        hostForUpdates,
        isChecking,
        checkResult,
        checkError,
        openUpdatesModal,
        closeUpdatesModal,
        handleApplyUpdates,
    };
}
