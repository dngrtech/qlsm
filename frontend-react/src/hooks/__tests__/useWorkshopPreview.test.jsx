import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as api from '../../services/api';
import { useWorkshopPreview, __clearWorkshopPreviewCacheForTests } from '../useWorkshopPreview';

vi.mock('../../services/api', () => ({
    getWorkshopPreview: vi.fn(),
}));

describe('useWorkshopPreview', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        __clearWorkshopPreviewCacheForTests();
    });

    it('returns null when workshop item id is missing', () => {
        const { result } = renderHook(() => useWorkshopPreview(null, true));

        expect(result.current.loading).toBe(false);
        expect(result.current.previewUrl).toBeNull();
        expect(api.getWorkshopPreview).not.toHaveBeenCalled();
    });

    it('returns null and does not fetch when disabled', () => {
        const { result } = renderHook(() => useWorkshopPreview('2358556636', false));

        expect(result.current.loading).toBe(false);
        expect(result.current.previewUrl).toBeNull();
        expect(api.getWorkshopPreview).not.toHaveBeenCalled();
    });

    it('fetches preview URL when workshop item id exists', async () => {
        api.getWorkshopPreview.mockResolvedValueOnce({
            workshop_id: '2358556636',
            preview_url: 'https://images.steamusercontent.com/ugc/example.jpg',
        });

        const { result } = renderHook(() => useWorkshopPreview('2358556636', true));

        await waitFor(() => {
            expect(result.current.loading).toBe(false);
            expect(result.current.previewUrl).toBe('https://images.steamusercontent.com/ugc/example.jpg');
        });
        expect(api.getWorkshopPreview).toHaveBeenCalledWith('2358556636');
    });

    it('returns null on API failure', async () => {
        api.getWorkshopPreview.mockRejectedValueOnce(new Error('network'));

        const { result } = renderHook(() => useWorkshopPreview('2358556636', true));

        await waitFor(() => {
            expect(result.current.loading).toBe(false);
            expect(result.current.previewUrl).toBeNull();
        });
        expect(api.getWorkshopPreview).toHaveBeenCalledTimes(1);
    });

    it('uses in-memory cache for repeated id lookups', async () => {
        api.getWorkshopPreview.mockResolvedValueOnce({
            workshop_id: '2358556636',
            preview_url: 'https://images.steamusercontent.com/ugc/example.jpg',
        });

        const first = renderHook(() => useWorkshopPreview('2358556636', true));
        await waitFor(() => {
            expect(first.result.current.loading).toBe(false);
            expect(first.result.current.previewUrl).toBe('https://images.steamusercontent.com/ugc/example.jpg');
        });
        first.unmount();

        const second = renderHook(() => useWorkshopPreview('2358556636', true));
        await waitFor(() => {
            expect(second.result.current.loading).toBe(false);
            expect(second.result.current.previewUrl).toBe('https://images.steamusercontent.com/ugc/example.jpg');
        });

        expect(api.getWorkshopPreview).toHaveBeenCalledTimes(1);
    });
});
