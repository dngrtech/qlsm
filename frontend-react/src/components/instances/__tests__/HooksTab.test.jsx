import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HooksTab from '../HooksTab';
import * as api from '../../../services/api';

vi.mock('../../../services/api');

function hooksResponse(overrides = {}) {
  return {
    available: [
      { filename: 'a.so', size: 1024, modified: 1, enabled: true, order: 1, description: 'Speed hook' },
      { filename: 'b.so', size: 2048, modified: 1, enabled: true, order: 2, description: '' },
      { filename: 'c.so', size: 3072, modified: 1, enabled: false, order: null, description: '' },
    ],
    system_hooks_active: [],
    ...overrides,
  };
}

describe('HooksTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchInstanceHooks.mockResolvedValue(hooksResponse());
    api.saveInstanceHooks.mockResolvedValue({ task_id: 't1' });
  });

  it('renders user hooks with enabled state and order', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => expect(screen.getByTestId('hook-row-a.so')).toBeInTheDocument());
    expect(screen.getByRole('checkbox', { name: /enable a.so/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /enable c.so/i })).not.toBeChecked();
  });

  it('hides system hooks section when system_hooks_active is empty', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(screen.queryByText(/system hooks/i)).not.toBeInTheDocument();
  });

  it('shows system hooks section when non-empty', async () => {
    api.fetchInstanceHooks.mockResolvedValueOnce(hooksResponse({
      system_hooks_active: [{ filename: 'force_rate.so', size: 15880 }],
    }));

    render(<HooksTab instanceId={1} />);

    await waitFor(() => expect(screen.getByText(/system hooks/i)).toBeInTheDocument());
    expect(screen.getByText('force_rate.so')).toBeInTheDocument();
  });

  it('toggling a checkbox marks the form dirty and enables Apply', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    const apply = screen.getByRole('button', { name: /apply.*restart/i });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /enable c.so/i }));
    expect(apply).toBeEnabled();
  });

  it('Apply sends the enabled list in display order', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    fireEvent.click(screen.getByRole('checkbox', { name: /enable c.so/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply.*restart/i }));

    await waitFor(() => expect(api.saveInstanceHooks).toHaveBeenCalled());
    expect(api.saveInstanceHooks).toHaveBeenCalledWith(1, ['a.so', 'b.so', 'c.so'], undefined);
  });

  it('renders hook descriptions from GET data as tooltips', async () => {
    render(<HooksTab instanceId={1} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    expect(screen.getByTitle('Speed hook')).toBeInTheDocument();
  });

  it('calls onApplied after a successful save', async () => {
    const onApplied = vi.fn();
    render(<HooksTab instanceId={1} onApplied={onApplied} />);

    await waitFor(() => screen.getByTestId('hook-row-a.so'));
    fireEvent.click(screen.getByRole('checkbox', { name: /enable c.so/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply.*restart/i }));

    await waitFor(() => expect(onApplied).toHaveBeenCalled());
  });
});
