import { installQlfilter, uninstallQlfilter } from '../services/api';

/**
 * Shared hook for QLFilter install/uninstall actions.
 * @param {Function} showSuccess - Notification callback for success messages.
 * @param {Function} showError - Notification callback for error messages.
 * @param {Function} refreshFn - Callback to refresh data after the action completes.
 * @returns {{ handleQlfilterAction: (hostId: number, actionType: string) => Promise<void> }}
 */
export function useQlfilterActions(showSuccess, showError, refreshFn) {
    const handleQlfilterAction = async (hostId, actionType) => {
        try {
            let responseMessage = '';
            if (actionType === 'install') {
                const response = await installQlfilter(hostId);
                responseMessage = response.message || 'QLFilter installation initiated.';
                showSuccess(responseMessage);
            } else if (actionType === 'uninstall') {
                const response = await uninstallQlfilter(hostId);
                responseMessage = response.message || 'QLFilter uninstallation initiated.';
                showSuccess(responseMessage);
            }
        } catch (err) {
            const errorMsg = err?.error?.message || err?.message || 'Unknown error';
            showError(`Error initiating QLFilter ${actionType}: ${errorMsg}`);
        } finally {
            refreshFn();
        }
    };

    return { handleQlfilterAction };
}
