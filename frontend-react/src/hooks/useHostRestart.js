import { useState } from 'react';
import { restartHost } from '../services/api';

/**
 * Shared hook for host restart with confirmation modal support.
 * @param {Function} showSuccess - Notification callback for success messages.
 * @param {Function} showError - Notification callback for error messages.
 * @param {Function} refreshFn - Callback to refresh data after the action completes.
 * @returns {{
 *   hostForRestart: object|null,
 *   isRestartModalOpen: boolean,
 *   requestRestart: (host: object) => void,
 *   confirmRestart: () => Promise<void>,
 *   closeRestartModal: () => void,
 * }}
 */
export function useHostRestart(showSuccess, showError, refreshFn) {
    const [isRestartModalOpen, setIsRestartModalOpen] = useState(false);
    const [hostForRestart, setHostForRestart] = useState(null);

    const requestRestart = (host) => {
        setHostForRestart(host);
        setIsRestartModalOpen(true);
    };

    const confirmRestart = async () => {
        if (!hostForRestart) return;
        try {
            await restartHost(hostForRestart.id);
            showSuccess(`Host "${hostForRestart.name}" restart initiated.`);
            refreshFn();
        } catch (err) {
            const errorMsg = err?.error?.message || err?.message || `Failed to restart host "${hostForRestart.name}".`;
            showError(errorMsg);
        }
        setIsRestartModalOpen(false);
        setHostForRestart(null);
    };

    const closeRestartModal = () => {
        setIsRestartModalOpen(false);
        setHostForRestart(null);
    };

    return { hostForRestart, isRestartModalOpen, requestRestart, confirmRestart, closeRestartModal };
}
