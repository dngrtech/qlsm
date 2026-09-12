import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import AdminRow from '../AdminRow';

const row = (over = {}) => ({ steamId: '76561198012345678', level: 3, state: 'managed', ...over });

describe('AdminRow', () => {
  it('shows the operator name when known', () => {
    render(<AdminRow row={row()} operator={{ name: 'Vex' }} />);
    expect(screen.getByText('Vex')).toBeInTheDocument();
  });

  it('shows the SteamID as the label when unknown, with an add action', () => {
    const onAddToDirectory = vi.fn();
    render(<AdminRow row={row()} operator={null} onAddToDirectory={onAddToDirectory} />);
    expect(screen.getByText('76561198012345678')).toBeInTheDocument();
    expect(screen.queryByText(/unknown operator/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add to operators/i })).toBeInTheDocument();
  });

  it('offers Adopt for a row the server has but QLSM does not', async () => {
    const onAdopt = vi.fn();
    const { rerender } = render(<AdminRow row={row({ state: 'live-only' })} onAdopt={onAdopt} />);
    await userEvent.click(screen.getByRole('button', { name: /adopt/i }));
    expect(onAdopt).toHaveBeenCalledWith('76561198012345678');
    rerender(<AdminRow row={row({ state: 'will-be-revoked' })} onAdopt={onAdopt} />);
    expect(screen.getByRole('button', { name: /adopt/i })).toBeInTheDocument();
    rerender(<AdminRow row={row()} onAdopt={onAdopt} />);
    expect(screen.queryByRole('button', { name: /adopt/i })).not.toBeInTheDocument();
  });

  it('labels a pending row as not applied yet', () => {
    render(<AdminRow row={row({ state: 'pending' })} />);
    expect(screen.getByText(/not applied yet/i)).toBeInTheDocument();
  });

  it('labels a managed-but-rowless row as one that will be revoked', () => {
    render(<AdminRow row={row({ state: 'will-be-revoked' })} />);
    expect(screen.getByText(/will be revoked on save/i)).toBeInTheDocument();
  });

  it('shows no state badge when the live level is unknown', () => {
    render(<AdminRow row={row({ state: 'unknown' })} />);
    expect(screen.queryByText(/not applied yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/set in-game/i)).not.toBeInTheDocument();
  });

  it('removes on click', async () => {
    const onRemove = vi.fn();
    render(<AdminRow row={row()} onRemove={onRemove} />);
    await userEvent.click(screen.getByRole('button', { name: /remove admin/i }));
    expect(onRemove).toHaveBeenCalledWith('76561198012345678');
  });

  it('has no Remove on a row QLSM does not manage', async () => {
    // Remove filters the stored list, which a server-only row is not in -- the
    // button would do nothing. Adopt first, then remove.
    const onRemove = vi.fn();
    const { rerender } = render(<AdminRow row={row({ state: 'live-only' })} onRemove={onRemove} />);
    expect(screen.queryByRole('button', { name: /remove admin/i })).not.toBeInTheDocument();
    rerender(<AdminRow row={row({ state: 'will-be-revoked' })} onRemove={onRemove} />);
    expect(screen.queryByRole('button', { name: /remove admin/i })).not.toBeInTheDocument();
  });

  it('exposes the SteamID and level via data-testid for fragmented-markup queries', () => {
    render(<AdminRow row={row()} operator={{ name: 'Vex' }} />);
    const rowEl = screen.getByTestId('admin-row-76561198012345678');
    expect(rowEl).toHaveTextContent('Vex');
    expect(rowEl).toHaveTextContent('76561198012345678');
  });
});
