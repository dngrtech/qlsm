import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import RankProviderTab from '../RankProviderTab';
import * as api from '../../../services/api';

vi.mock('../../../services/api');

describe('RankProviderTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getRankProvider).mockResolvedValue(null);
    vi.mocked(api.saveRankProvider).mockResolvedValue({});
    vi.mocked(api.deleteRankProvider).mockResolvedValue({});
  });

  it('issues a delete rather than a save when the provider is None', async () => {
    vi.mocked(api.getRankProvider).mockResolvedValue({
      provider_type: 'slipgate', base_url: 'https://slipgate.gg/api/v1',
      api_key: 'tok', game_type: null, extra: {}, enabled: true,
    });
    render(<RankProviderTab instanceId={7} />);
    await screen.findByLabelText(/provider/i);
    fireEvent.change(screen.getByLabelText(/provider/i), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(api.deleteRankProvider).toHaveBeenCalledWith(7));
    expect(api.saveRankProvider).not.toHaveBeenCalled();
  });

  it('disables Save after a failed load so it cannot delete the real config', async () => {
    vi.mocked(api.getRankProvider).mockRejectedValue(new Error('network'));
    render(<RankProviderTab instanceId={7} />);
    await screen.findByText(/could not load/i);
    const save = screen.getByRole('button', { name: /save/i });
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(api.deleteRankProvider).not.toHaveBeenCalled();
  });

  it('hides the API key field for qlstats and shows it for the others', async () => {
    render(<RankProviderTab instanceId={7} />);
    await screen.findByLabelText(/provider/i);
    fireEvent.change(screen.getByLabelText(/provider/i), { target: { value: 'qlstats' } });
    expect(screen.queryByLabelText(/api key|upload token/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/provider/i), { target: { value: 'slipgate' } });
    expect(screen.getByLabelText(/upload token/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/provider/i), { target: { value: 'elo_service' } });
    expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
  });

  it('persists an elo_b selection into extra', async () => {
    render(<RankProviderTab instanceId={7} />);
    await screen.findByLabelText(/provider/i);
    fireEvent.change(screen.getByLabelText(/provider/i), { target: { value: 'qlstats' } });
    fireEvent.change(screen.getByLabelText(/base url/i),
      { target: { value: 'http://qlstats.net' } });
    fireEvent.change(screen.getByLabelText(/rating system/i), { target: { value: 'elo_b' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(api.saveRankProvider).toHaveBeenCalled());
    expect(api.saveRankProvider.mock.calls[0][1].extra)
      .toEqual({ rating_system: 'elo_b' });
  });
});
