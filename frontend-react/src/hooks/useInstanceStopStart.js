import { useState } from 'react';
import { stopInstance, startInstance } from '../services/api';

/**
 * Shared hook for instance stop/start with confirmation modal support.
 * @param {Function} showSuccess - Notification callback for success messages.
 * @param {Function} showError - Notification callback for error messages.
 * @param {Function} refreshFn - Callback to refresh data after the action completes.
 */
export function useInstanceStopStart(showSuccess, showError, refreshFn) {
    const [isStopStartModalOpen, setIsStopStartModalOpen] = useState(false);
    const [stopStartAction, setStopStartAction] = useState(null);

    const requestStop = (instanceId, instanceName) => {
        setStopStartAction({ id: instanceId, name: instanceName, action: 'stop' });
        setIsStopStartModalOpen(true);
    };

    const requestStart = (instanceId, instanceName) => {
        setStopStartAction({ id: instanceId, name: instanceName, action: 'start' });
        setIsStopStartModalOpen(true);
    };

    const confirmStopStart = async () => {
        if (!stopStartAction) return;
        const { id, name, action } = stopStartAction;
        try {
            const response = action === 'stop'
                ? await stopInstance(id)
                : await startInstance(id);
            const message = response.message || `Instance "${name}" ${action} task queued.`;
            showSuccess(message);
            refreshFn();
        } catch (err) {
            const errorMsg = err?.error?.message || err?.message || `Failed to ${action} instance "${name}".`;
            showError(errorMsg);
        }
        setIsStopStartModalOpen(false);
        setStopStartAction(null);
    };

    const closeStopStartModal = () => {
        setIsStopStartModalOpen(false);
        setStopStartAction(null);
    };

    return { stopStartAction, isStopStartModalOpen, requestStop, requestStart, confirmStopStart, closeStopStartModal };
}
