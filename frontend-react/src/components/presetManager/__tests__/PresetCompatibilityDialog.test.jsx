import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import PresetCompatibilityDialog from '../PresetCompatibilityDialog';

// Only actionable strips reach this dialog now. Untouched stock plugins are
// swapped for the target runtime's own copy by the backend and are absent from
// `stripped` entirely, so no fixture here represents one.
const compatibility = {
  preset_runtime: 'minqlx',
  target_runtime: 'minqlxtended',
  stripped: [
    {
      path: 'myFun.py',
      verdict: 'incompatible',
      reasons: ['line 3: imports the minqlx module'],
      replacement: 'myFun.py',
      kind: 'replaceable',
      from_catalog: false,
      originally_checked: true,
    },
    {
      path: 'commands.py',
      verdict: 'incompatible',
      reasons: ['line 1: imports the minqlx module'],
      replacement: 'commands.py',
      kind: 'replaceable',
      from_catalog: true,
      originally_checked: false,
    },
    {
      path: 'mybalance.py',
      verdict: 'incompatible',
      reasons: ['line 1: references the minqlx module'],
      replacement: null,
      kind: 'unavailable',
      from_catalog: false,
      originally_checked: true,
    },
    {
      path: 'custom.py',
      verdict: 'unknown',
      reasons: [],
      replacement: null,
      kind: 'unavailable',
      from_catalog: false,
      originally_checked: false,
    },
    {
      path: 'discord_extensions/admin.py',
      verdict: 'incompatible',
      reasons: ['line 11: imports the minqlx module'],
      replacement: null,
      auto_replaced: true,
      kind: 'helper',
      from_catalog: true,
      originally_checked: false,
    },
  ],
  replacements: { 'myFun.py': 'import minqlxtended\n', 'commands.py': 'import minqlxtended\n' },
  auto_accepted: ['motd.py'],
};

const setup = (overrides = {}) => {
  const props = { isOpen: true, compatibility, onCancel: vi.fn(), onConfirm: vi.fn(), ...overrides };
  render(<PresetCompatibilityDialog {...props} />);
  return props;
};

describe('PresetCompatibilityDialog', () => {
  it('lists every reported plugin', () => {
    setup();
    ['myFun.py', 'mybalance.py', 'custom.py'].forEach((name) => {
      expect(screen.getByText(name)).toBeInTheDocument();
    });
  });

  it('says untouched standard plugins were swapped automatically', () => {
    // The operator has to know why this list is short -- that the plugins
    // absent from it were handled, not forgotten.
    setup();
    expect(screen.getByText(/swapped for.*own version of the same plugin automatically/is))
      .toBeInTheDocument();
  });

  it('promises the preset\'s own plugin selection is preserved', () => {
    // The bug this dialog caused: confirming it enabled the target runtime's
    // entire default catalog. The copy now states the guarantee outright.
    setup();
    expect(screen.getByText(/enabled exactly as this preset had them/i)).toBeInTheDocument();
  });

  it('shows the reason a plugin was stripped', () => {
    setup();
    expect(screen.getByText('line 3: imports the minqlx module')).toBeInTheDocument();
  });

  it('explains an unknown verdict rather than leaving it blank', () => {
    // "custom.py was removed" with no cause is not an answer.
    setup();
    expect(screen.getByText(/not part of the .* baseline/i)).toBeInTheDocument();
  });

  // Scoped to the row rather than the whole dialog: several entries carry each
  // of these sentences, and a document-wide match would pass on the wrong one.
  const rowFor = (path) => within(screen.getByText(path).closest('li'));

  it('calls a modified standard plugin what it is', () => {
    setup();
    expect(rowFor('commands.py').getByText(/A standard minqlx plugin that this preset modified\./))
      .toBeInTheDocument();
  });

  it('distinguishes a custom plugin from a modified standard one', () => {
    setup();
    expect(rowFor('custom.py').getByText(/A custom plugin, not part of the standard minqlx set\./))
      .toBeInTheDocument();
  });

  it('warns that an unavailable plugin the preset had enabled gets switched off', () => {
    setup();
    expect(rowFor('mybalance.py').getByText(/no version of it.*switched off/is))
      .toBeInTheDocument();
  });

  it('does not threaten to switch off an unavailable plugin the preset had disabled', () => {
    setup();
    expect(rowFor('custom.py').queryByText(/switched off/i)).not.toBeInTheDocument();
  });

  it('offers a replacement checkbox only where one exists', () => {
    setup();
    // myFun.py and commands.py both have a replacement offered; mybalance.py,
    // custom.py, and the auto-replaced helper do not.
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it('defaults every offered replacement to accepted', () => {
    // Declining loses the file outright -- the preset's copy cannot run on the
    // target either way -- so taking the working version is the better
    // default. This is only safe because a tick no longer enables the plugin:
    // enablement comes from the preset's own selection (see mergeReplacements).
    setup();
    expect(screen.getByRole('checkbox', { name: /myFun\.py/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /commands\.py/ })).toBeChecked();
  });

  it('says plainly that accepting a replacement discards the preset\'s changes', () => {
    setup();
    expect(screen.getAllByText(/changes to it are lost/i).length).toBeGreaterThan(0);
  });

  it('confirms with the accepted replacement paths', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('button', { name: /load preset/i }));
    expect(onConfirm.mock.calls[0][0].sort()).toEqual(['commands.py', 'myFun.py']);
  });

  it('lets the operator decline a replacement', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('checkbox', { name: /commands\.py/ }));
    await userEvent.click(screen.getByRole('button', { name: /load preset/i }));
    expect(onConfirm).toHaveBeenCalledWith(['myFun.py']);
  });

  it('confirms with nothing when every replacement is declined', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('checkbox', { name: /myFun\.py/ }));
    await userEvent.click(screen.getByRole('checkbox', { name: /commands\.py/ }));
    await userEvent.click(screen.getByRole('button', { name: /load preset/i }));
    expect(onConfirm).toHaveBeenCalledWith([]);
  });

  it('cancels without confirming', async () => {
    const { onCancel, onConfirm } = setup();
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  // A helper module the target ships at the same path is restored by the draft filter,
  // so it must not be presented the way an unrecoverable file is. Before this, the two
  // were indistinguishable in the dialog: same warning triangle, same "won't be
  // installed" framing, no checkbox -- and operators reported the helpers as still
  // showing up incompatible even though they were landing correctly on disk.
  it('presents an auto-replaced helper as swapped, not as a loss', () => {
    setup();
    expect(screen.getByText(/Replaced automatically with minqlxtended/i)).toBeInTheDocument();
  });

  it('does not show the stripping reason for an auto-replaced helper', () => {
    setup();
    expect(screen.queryByText('line 11: imports the minqlx module')).not.toBeInTheDocument();
  });

  it('gives an auto-replaced helper no checkbox, since there is no choice to make', () => {
    setup();
    // Two checkboxes in the whole dialog: myFun.py and commands.py, the only
    // entries with a replacement offered.
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it('renders nothing when there is no compatibility block', () => {
    const { container } = render(
      <PresetCompatibilityDialog isOpen compatibility={null} onCancel={vi.fn()} onConfirm={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
