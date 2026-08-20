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
      fireEvent.mouseDown(elsewhere);
      elsewhere.focus();
      vi.advanceTimersByTime(400);
      expect(document.activeElement).toBe(elsewhere);
    } finally {
      vi.useRealTimers();
    }
  });

  it('claims focus once enabled even if something else already holds it, as long as the user never interacted', () => {
    // Reproduces the RCON console modal case: closing the row's "Actions"
    // menu to launch the modal leaves DOM focus on that menu's own trigger
    // button (Headless UI restores focus there on close), and Headless
    // UI's Dialog FocusTrap can independently land on some other in-panel
    // element while the field is still disabled. Neither is a real user
    // gesture, so becoming enabled should still win the field focus.
    const { rerender } = render(<><button type="button">Elsewhere</button><RconCommandInput disabled onSend={() => true} /></>);
    const elsewhere = screen.getByRole('button', { name: 'Elsewhere' });
    elsewhere.focus();
    expect(document.activeElement).toBe(elsewhere);

    rerender(<><button type="button">Elsewhere</button><RconCommandInput disabled={false} onSend={() => true} /></>);
    expect(input()).toHaveFocus();
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
