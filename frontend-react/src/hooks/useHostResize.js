import { useCallback, useState } from 'react';
import { resizeHost } from '../services/api';

export function useHostResize(showSuccess, showError, onSuccess) {
    const [isResizeModalOpen, setIsResizeModalOpen] = useState(false);
    const [hostForResize, setHostForResize] = useState(null);
    const [resizeError, setResizeError] = useState('');
    const [isResizeSubmitting, setIsResizeSubmitting] = useState(false);

    const openResizeModal = useCallback((host) => {
        setResizeError('');
        setHostForResize(host);
        setIsResizeModalOpen(true);
    }, []);

    const closeResizeModal = useCallback(() => {
        setIsResizeModalOpen(false);
        setHostForResize(null);
        setResizeError('');
    }, []);

    const handleResizeSubmit = useCallback(async (newPlan) => {
        if (!hostForResize) return;

        setIsResizeSubmitting(true);
        setResizeError('');
        try {
            const response = await resizeHost(hostForResize.id, newPlan);
            showSuccess(response.message || `Resize task queued: ${newPlan}`);
            if (onSuccess) onSuccess();
            closeResizeModal();
        } catch (error) {
            console.error('Failed to resize host:', error);
            const message = error.error?.message || error.message || 'Failed to resize host';
            setResizeError(message);
            showError(message);
        } finally {
            setIsResizeSubmitting(false);
        }
    }, [hostForResize, showSuccess, showError, onSuccess, closeResizeModal]);

    return {
        isResizeModalOpen,
        isResizeSubmitting,
        resizeError,
        hostForResize,
        openResizeModal,
        closeResizeModal,
        handleResizeSubmit,
    };
}
