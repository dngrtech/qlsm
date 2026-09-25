import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import RconCommandInput from '../RconCommandInput';
import { setCvarCatalog } from '../../../codemirror-lang-qlcfg';

vi.mock('../../../services/cvarCatalogApi', () => ({
  fetchCvarCatalog: vi.fn(() => Promise.resolve({
    cvars: [
      { name: 'sv_hostname', group: 'server', description: 'Server name shown in the browser.' },
      { name: 'sv_maxclients', group: 'server', description: 'Player slots.' },
      { name: 'g_gametype', group: 'game', description: 'Game mode.' },
    ],
    commands: [
      { name: 'set', description: 'Set a cvar.' },
      { name: 'status', description: 'List connected players.' },
      { name: 'say', description: 'Broadcast a message.' },
    ],
  })),
}));

function input() {
  return screen.getByRole('combobox');
}

function type(value) {
  fireEvent.change(input(), { target: { value } });
}

function optionLabels() {
  return screen.queryAllByRole('option').map(option => option.firstChild.textContent);
}

async function renderReady(props = {}) {
  const utils = render(<RconCommandInput onSend={() => true} {...props} />);
  await act(async () => {});
  return utils;
}

beforeEach(() => setCvarCatalog(null));

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

  describe('autocomplete', () => {
    it('offers commands and cvars for the first word, prefix matches first', async () => {
      await renderReady();
      type('s');
      expect(optionLabels().slice(0, 3)).toEqual(['set', 'status', 'say']);
      expect(optionLabels()).toContain('sv_hostname');
      expect(screen.getByText('Server name shown in the browser.')).toBeInTheDocument();
    });

    it('offers only cvars after set, and nothing for values', async () => {
      await renderReady();
      type('set sv_');
      // App-managed cvars still match but rank last at the console.
      expect(optionLabels()).toEqual(['sv_hostname', 'sv_maxclients', 'sv_servertype', 'sv_lanforcerate']);
      expect(optionLabels()).not.toContain('status');
      type('set sv_hostname My');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      type('say hel');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('Tab accepts the top suggestion and adds a trailing space', async () => {
      await renderReady();
      type('set sv_host');
      fireEvent.keyDown(input(), { key: 'Tab' });
      expect(input()).toHaveValue('set sv_hostname ');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('arrows move the highlight and Enter accepts it instead of sending', async () => {
      const onSend = vi.fn(() => true);
      await renderReady({ onSend });
      type('sv_');
      fireEvent.keyDown(input(), { key: 'ArrowDown' });
      fireEvent.keyDown(input(), { key: 'ArrowDown' });
      expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
      fireEvent.keyDown(input(), { key: 'Enter' });
      expect(input()).toHaveValue('sv_maxclients ');
      expect(onSend).not.toHaveBeenCalled();
    });

    it('Enter without a highlighted suggestion sends what was typed', async () => {
      const onSend = vi.fn(() => true);
      await renderReady({ onSend });
      type('stat');
      const event = fireEvent.keyDown(input(), { key: 'Enter' });
      expect(event).toBe(true); // not consumed, so the form submits
      fireEvent.submit(input().closest('form'));
      expect(onSend).toHaveBeenCalledWith('stat');
    });

    it('clicking a suggestion accepts it', async () => {
      await renderReady();
      type('g_');
      fireEvent.mouseDown(screen.getByRole('option'));
      expect(input()).toHaveValue('g_gametype ');
    });

    it('Escape closes the list and Up then walks history again', async () => {
      await renderReady();
      type('status');
      fireEvent.submit(input().closest('form'));
      type('s');
      expect(screen.getByRole('listbox')).toBeInTheDocument();
      fireEvent.keyDown(input(), { key: 'Escape' });
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      fireEvent.keyDown(input(), { key: 'ArrowUp' });
      expect(input()).toHaveValue('status');
    });

    it('recalling history does not open the list', async () => {
      await renderReady();
      type('sv_hostname');
      fireEvent.submit(input().closest('form'));
      type('set');
      fireEvent.submit(input().closest('form'));
      fireEvent.keyDown(input(), { key: 'ArrowUp' });
      expect(input()).toHaveValue('set');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
      fireEvent.keyDown(input(), { key: 'ArrowUp' });
      expect(input()).toHaveValue('sv_hostname');
    });
  });
});
