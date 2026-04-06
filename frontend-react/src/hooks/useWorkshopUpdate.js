import { useState, useCallback } from 'react';
import { updateWorkshopItem } from '../services/api';

export function useWorkshopUpdate(showSuccess, showError, onSuccess) {
    const [isWorkshopModalOpen, setIsWorkshopModalOpen] = useState(false);
    const [hostForWorkshopUpdate, setHostForWorkshopUpdate] = useState(null);

    const openWorkshopModal = useCallback((host) => {
        setHostForWorkshopUpdate(host);
        setIsWorkshopModalOpen(true);
    }, []);

    const closeWorkshopModal = useCallback(() => {
        setIsWorkshopModalOpen(false);
        setHostForWorkshopUpdate(null);
    }, []);

    const handleWorkshopUpdateSubmit = useCallback(async (workshopId, restartInstanceIds) => {
        if (!hostForWorkshopUpdate) return;

        try {
            const response = await updateWorkshopItem(hostForWorkshopUpdate.id, {
                workshop_id: workshopId,
                restart_instances: restartInstanceIds
            });
            showSuccess(response.message || `Workshop update task queued for ${workshopId}`);
            if (onSuccess) onSuccess();
            closeWorkshopModal();
        } catch (error) {
            console.error("Failed to update workshop item:", error);
            showError(error.error?.message || error.message || "Failed to update workshop item");
        }
    }, [hostForWorkshopUpdate, showSuccess, showError, onSuccess, closeWorkshopModal]);

    return {
        isWorkshopModalOpen,
        hostForWorkshopUpdate,
        openWorkshopModal,
        closeWorkshopModal,
        handleWorkshopUpdateSubmit
    };
}
