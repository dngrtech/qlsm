import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import LiveServerStatusModal from '../LiveServerStatusModal';

vi.mock('../../../hooks/useWorkshopPreview', () => ({
    useWorkshopPreview: vi.fn(),
}));

import { useWorkshopPreview } from '../../../hooks/useWorkshopPreview';

const baseInstance = { id: 1, name: 'test-server', port: 27960 };
const baseStatus = {
    map: 'campgrounds',
    gametype: 'ca',
    factory: 'clanarena',
    state: 'in_progress',
    match_start_time: null,
    players: [],
    maxplayers: 16,
    red_score: 0,
    blue_score: 0,
    workshop_item_id: null,
};

describe('LiveServerStatusModal map preview', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        useWorkshopPreview.mockReturnValue({ previewUrl: null, loading: false });
    });

    it('renders a static preview image for a known standard map', () => {
        render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'campgrounds' }}
            />
        );

        const img = screen.getByRole('img', { name: /map preview/i });
        expect(img.src).toContain('map-previews/standard/campgrounds.webp');
    });

    it('renders a static preview image by map filename for non-listed standard maps', () => {
        render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'asylum', workshop_item_id: null }}
            />
        );

        const img = screen.getByRole('img', { name: /map preview/i });
        expect(img.src).toContain('map-previews/standard/asylum.webp');
    });

    it('prefers static standard preview even when workshop preview is available', () => {
        const workshopUrl = 'https://steamcdn.example.com/workshop_preview.jpg';
        useWorkshopPreview.mockReturnValue({ previewUrl: workshopUrl, loading: false });

        render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'campgrounds', workshop_item_id: '2358556636' }}
            />
        );

        const img = screen.getByRole('img', { name: /map preview/i });
        expect(img.src).toContain('map-previews/standard/campgrounds.webp');
    });

    it('renders workshop preview when map is not a standard map and hook returns URL', () => {
        const workshopUrl = 'https://steamcdn.example.com/workshop_preview.jpg';
        useWorkshopPreview.mockReturnValue({ previewUrl: workshopUrl, loading: false });

        render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'some_workshop_map', workshop_item_id: '2358556636' }}
            />
        );

        const img = screen.getByRole('img', { name: /map preview/i });
        expect(img.src).toBe(workshopUrl);
    });

    it('keeps previous preview while workshop preview is loading for new map', () => {
        useWorkshopPreview.mockReturnValue({ previewUrl: null, loading: false });

        const { rerender } = render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'campgrounds', workshop_item_id: null }}
            />
        );

        const firstImage = screen.getByRole('img', { name: /map preview/i });
        expect(firstImage.src).toContain('map-previews/standard/campgrounds.webp');

        useWorkshopPreview.mockReturnValue({ previewUrl: null, loading: true });
        rerender(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'some_workshop_map', workshop_item_id: '2358556636' }}
            />
        );

        const loadingImage = screen.getByRole('img', { name: /map preview/i });
        expect(loadingImage.src).toContain('map-previews/standard/campgrounds.webp');
    });

    it('falls back to placeholder when unknown map static preview is missing', () => {
        render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'obscure_map', workshop_item_id: null }}
            />
        );

        const img = screen.getByRole('img', { name: /map preview/i });
        expect(img.src).toContain('map-previews/standard/obscure_map.webp');
        fireEvent.error(img);
        expect(img.src).toContain('map-previews/defaultmap.webp');
    });

    it('falls back to placeholder when image load fails', () => {
        render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'campgrounds' }}
            />
        );

        const img = screen.getByRole('img', { name: /map preview/i });
        fireEvent.error(img);
        expect(img.src).toContain('map-previews/defaultmap.webp');
    });

    it('map name text remains visible', () => {
        render(
            <LiveServerStatusModal
                isOpen={true}
                onClose={() => {}}
                instance={baseInstance}
                serverStatus={{ ...baseStatus, map: 'campgrounds' }}
            />
        );

        expect(screen.getByText('campgrounds')).toBeInTheDocument();
    });
});
