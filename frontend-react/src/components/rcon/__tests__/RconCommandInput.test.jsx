import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import RconCommandInput from '../RconCommandInput';

function input() {
  return screen.getByRole('textbox');
}

describe('RconCommandInput', () => {
  it('takes focus on mount but does not steal it back from the user', () => {
    vi.useFakeTimers();
    try {
      render(<><button type="button">Elsewhere</button><RconCommandInput onSend={() => true} /></>);
      expect(document.activeElement).toBe(input());

      // The fleet page mounts this permanently, so a user who clicks away
      // during the deferred re-focus window must keep their focus.
      const elsewhere = screen.getByRole('button', { name: 'Elsewhere' });
      elsewhere.focus();
      vi.advanceTimersByTime(400);
      expect(document.activeElement).toBe(elsewhere);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not submit empty or disabled commands', () => {
    const onSend = vi.fn(() => true);
    const { rerender } = render(<RconCommandInput onSend={onSend} />);
    fireEvent.submit(input().closest('form'));
    expect(onSend).not.toHaveBeenCalled();

    rerender(<RconCommandInput disabled onSend={onSend} />);
    fireEvent.change(input(), { target: { value: 'status' } });
    fireEvent.submit(input().closest('form'));
    expect(onSend).not.toHaveBeenCalled();
  });

  it('trims, sends, clears, and restores focus after successful submission', () => {
    const onSend = vi.fn(() => true);
    render(<RconCommandInput onSend={onSend} />);
    fireEvent.change(input(), { target: { value: '  status  ' } });
    fireEvent.submit(input().closest('form'));

    expect(onSend).toHaveBeenCalledWith('status');
    expect(input()).toHaveValue('');
    expect(input()).toHaveFocus();
  });

  it('keeps the newest 50 commands and navigates history with Up and Down', () => {
    render(<RconCommandInput onSend={() => true} />);
    for (let i = 0; i < 51; i += 1) {
      fireEvent.change(input(), { target: { value: `cmd-${i}` } });
      fireEvent.submit(input().closest('form'));
    }

    for (let i = 0; i < 50; i += 1) fireEvent.keyDown(input(), { key: 'ArrowUp' });
    expect(input()).toHaveValue('cmd-1');
    fireEvent.keyDown(input(), { key: 'ArrowUp' });
    expect(input()).toHaveValue('cmd-1');
    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    expect(input()).toHaveValue('cmd-2');
  });

  it('renders fleet-ready recipient and label text without changing defaults', () => {
    const { rerender } = render(<RconCommandInput onSend={() => true} />);
    expect(screen.getByText('RCON>')).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveTextContent('Send');

    rerender(<RconCommandInput recipientCount={3} buttonLabel="Send to 3 targets" onSend={() => true} />);
    expect(screen.getByText('3 recipients')).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveTextContent('Send to 3 targets');
  });
});
