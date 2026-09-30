import { render, screen, fireEvent, within } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import LiveServerStatusModal from '../LiveServerStatusModal';

vi.mock('../../../hooks/useWorkshopPreview', () => ({
    useWorkshopPreview: vi.fn(),
}));

const mockUseRankData = vi.fn(() => ({ ranks: {}, configured: false }));
vi.mock('../../../hooks/useRankData', () => ({
    useRankData: (...args) => mockUseRankData(...args),
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

const statusWithPlayers = {
    ...baseStatus,
    players: [
        { name: 'PlayerOne', steam: '76561198000000001', team: 'red', score: 5, ping: 30 },
    ],
};

const renderModal = (props = {}) => render(
    <LiveServerStatusModal
        isOpen
        onClose={() => {}}
        instance={baseInstance}
        serverStatus={baseStatus}
        {...props}
    />,
);

beforeEach(() => {
    mockUseRankData.mockReset();
    mockUseRankData.mockReturnValue({ ranks: {}, configured: false });
    useWorkshopPreview.mockReturnValue({ previewUrl: null, loading: false });
});

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


describe('LiveServerStatusModal player ranks', () => {
    it('hides the rank column entirely when no provider is configured', () => {
        renderModal({ serverStatus: statusWithPlayers });
        expect(screen.queryByRole('columnheader', { name: /elo/i })).not.toBeInTheDocument();
        expect(within(screen.getByText('PlayerOne').closest('tr')).getAllByRole('cell')).toHaveLength(5);
    });

    it('shows the rank column when a provider is configured', () => {
        mockUseRankData.mockReturnValue({
            ranks: { '76561198000000001': { display: '1650', provisional: false } },
            configured: true,
        });
        renderModal({ serverStatus: statusWithPlayers });
        expect(screen.getByRole('columnheader', { name: /elo/i })).toBeInTheDocument();
        expect(screen.getByText('1650')).toBeInTheDocument();
        expect(screen.getAllByRole('columnheader').map((header) => header.textContent))
            .toEqual(['Name', 'SteamID', 'Team', 'ELO', 'Score', 'Ping']);
    });

    it('merges on the string steam id', () => {
        mockUseRankData.mockReturnValue({
            ranks: { '76561198000000001': { display: '1650', provisional: false } },
            configured: true,
        });
        renderModal({ serverStatus: statusWithPlayers });
        const row = screen.getByText('PlayerOne').closest('tr');
        expect(within(row).getByText('1650')).toBeInTheDocument();
        expect(mockUseRankData).toHaveBeenCalledWith(1, ['76561198000000001'], { enabled: true });
    });

    it('renders an em dash for a player with no rating', () => {
        mockUseRankData.mockReturnValue({ ranks: {}, configured: true });
        renderModal({ serverStatus: statusWithPlayers });
        const row = screen.getByText('PlayerOne').closest('tr');
        expect(within(row).getByText('—')).toBeInTheDocument();
    });

    it('preserves provider display labels whole', () => {
        mockUseRankData.mockReturnValue({
            ranks: { '76561198000000001': { display: '1650 (Gold)', provisional: true } },
            configured: true,
        });
        renderModal({ serverStatus: statusWithPlayers });
        expect(within(screen.getByText('PlayerOne').closest('tr')).getByText('1650 (Gold)'))
            .toBeInTheDocument();
    });

    it('disables rank requests while the modal is closed', () => {
        renderModal({ isOpen: false, serverStatus: statusWithPlayers });
        expect(mockUseRankData).toHaveBeenCalledWith(1, ['76561198000000001'], { enabled: false });
    });

    it('disables rank requests without an instance id', () => {
        renderModal({ instance: null, serverStatus: statusWithPlayers });
        expect(mockUseRankData).toHaveBeenCalledWith(undefined, ['76561198000000001'], { enabled: false });
    });
});
