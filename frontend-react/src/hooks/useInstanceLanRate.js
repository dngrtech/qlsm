import { useState } from 'react';
import { updateInstanceLanRate } from '../services/api';

/**
 * Shared hook for LAN rate toggle with confirmation modal support.
 * @param {Function} showSuccess - Notification callback for success messages.
 * @param {Function} showError - Notification callback for error messages.
 * @param {Function} refreshFn - Callback to refresh data after the action completes.
 * @returns {{
 *   lanRateAction: object|null,
 *   isLanRateModalOpen: boolean,
 *   requestToggleLanRate: (instanceId: number, instanceName: string, currentLanRateEnabled: boolean) => void,
 *   confirmToggleLanRate: () => Promise<void>,
 *   closeLanRateModal: () => void,
 * }}
 */
export function useInstanceLanRate(showSuccess, showError, refreshFn) {
    const [isLanRateModalOpen, setIsLanRateModalOpen] = useState(false);
    const [lanRateAction, setLanRateAction] = useState(null);

    const requestToggleLanRate = (instanceId, instanceName, currentLanRateEnabled) => {
        setLanRateAction({
            id: instanceId,
            name: instanceName,
            enabling: !currentLanRateEnabled,
        });
        setIsLanRateModalOpen(true);
    };

    const confirmToggleLanRate = async () => {
        if (!lanRateAction) return;
        try {
            const response = await updateInstanceLanRate(lanRateAction.id, lanRateAction.enabling);
            const message = response.message || `LAN rate ${lanRateAction.enabling ? 'enabled' : 'disabled'} for "${lanRateAction.name}". Instance will restart.`;
            showSuccess(message);
            refreshFn();
        } catch (err) {
            const errorMsg = err?.error?.message || err?.message || `Failed to toggle LAN rate for "${lanRateAction.name}".`;
            showError(errorMsg);
        }
        setIsLanRateModalOpen(false);
        setLanRateAction(null);
    };

    const closeLanRateModal = () => {
        setIsLanRateModalOpen(false);
        setLanRateAction(null);
    };

    return { lanRateAction, isLanRateModalOpen, requestToggleLanRate, confirmToggleLanRate, closeLanRateModal };
}
