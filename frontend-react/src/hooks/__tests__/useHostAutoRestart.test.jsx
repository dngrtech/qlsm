import { renderHook, act } from '@testing-library/react';
import { useHostAutoRestart } from '../useHostAutoRestart';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import * as api from '../../services/api';

vi.mock('../../services/api', () => ({
    configureAutoRestart: vi.fn(),
}));

describe('useHostAutoRestart Hook', () => {
    const showSuccessMock = vi.fn();
    const showErrorMock = vi.fn();
    const onSuccessMock = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('should initialize with default states', () => {
        const { result } = renderHook(() => useHostAutoRestart(showSuccessMock, showErrorMock, onSuccessMock));

        expect(result.current.isAutoRestartModalOpen).toBe(false);
        expect(result.current.hostForAutoRestart).toBeNull();
    });

    it('should open modal and set host', () => {
        const { result } = renderHook(() => useHostAutoRestart(showSuccessMock, showErrorMock, onSuccessMock));
        const mockHost = { id: 1, name: 'test-host' };

        act(() => {
            result.current.openAutoRestartModal(mockHost);
        });

        expect(result.current.isAutoRestartModalOpen).toBe(true);
        expect(result.current.hostForAutoRestart).toEqual(mockHost);
    });

    it('should close modal and clear host', () => {
        const { result } = renderHook(() => useHostAutoRestart(showSuccessMock, showErrorMock, onSuccessMock));

        act(() => {
            result.current.openAutoRestartModal({ id: 1 });
            result.current.closeAutoRestartModal();
        });

        expect(result.current.isAutoRestartModalOpen).toBe(false);
        expect(result.current.hostForAutoRestart).toBeNull();
    });

    it('should handle successful submit', async () => {
        api.configureAutoRestart.mockResolvedValueOnce({ message: 'Success' });
        const { result } = renderHook(() => useHostAutoRestart(showSuccessMock, showErrorMock, onSuccessMock));
        const mockHost = { id: 1, name: 'test-host' };

        act(() => {
            result.current.openAutoRestartModal(mockHost);
        });

        await act(async () => {
            await result.current.handleAutoRestartSubmit(1, '*-*-* 04:00:00');
        });

        expect(api.configureAutoRestart).toHaveBeenCalledWith(1, '*-*-* 04:00:00');
        expect(showSuccessMock).toHaveBeenCalledWith('Success');
        expect(onSuccessMock).toHaveBeenCalled();
        expect(result.current.isAutoRestartModalOpen).toBe(false);
    });

    it('should handle failed submit', async () => {
        const errorMsg = 'Failed to configure scheduler';
        api.configureAutoRestart.mockRejectedValueOnce({ message: errorMsg });
        const { result } = renderHook(() => useHostAutoRestart(showSuccessMock, showErrorMock, onSuccessMock));

        act(() => {
            result.current.openAutoRestartModal({ id: 1 });
        });

        await act(async () => {
            await result.current.handleAutoRestartSubmit(1, '*-*-* 04:00:00');
        });

        expect(showErrorMock).toHaveBeenCalledWith(errorMsg);
        expect(onSuccessMock).not.toHaveBeenCalled();
        expect(result.current.isAutoRestartModalOpen).toBe(true); // remain open on failure usually or not handled explicitly, but here it doesn't call close
    });
});
