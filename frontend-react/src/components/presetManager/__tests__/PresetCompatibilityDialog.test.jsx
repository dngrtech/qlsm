import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import PresetCompatibilityDialog from '../PresetCompatibilityDialog';

const compatibility = {
  preset_runtime: 'minqlx',
  target_runtime: 'minqlxtended',
  stripped: [
    { path: 'myFun.py', verdict: 'incompatible', reasons: ['line 3: imports the minqlx module'], replacement: 'myFun.py', originally_checked: true },
    {
      path: 'commands.py',
      verdict: 'incompatible',
      reasons: ['line 1: imports the minqlx module'],
      replacement: 'commands.py',
      originally_checked: false,
    },
    { path: 'mybalance.py', verdict: 'incompatible', reasons: ['line 1: references the minqlx module'], replacement: null, originally_checked: false },
    { path: 'custom.py', verdict: 'unknown', reasons: [], replacement: null, originally_checked: false },
    {
      path: 'discord_extensions/admin.py',
      verdict: 'incompatible',
      reasons: ['line 11: imports the minqlx module'],
      replacement: null,
      auto_replaced: true,
      originally_checked: false,
    },
  ],
  replacements: { 'myFun.py': 'import minqlxtended\n', 'commands.py': 'import minqlxtended\n' },
};

const setup = (overrides = {}) => {
  const props = { isOpen: true, compatibility, onCancel: vi.fn(), onConfirm: vi.fn(), ...overrides };
  render(<PresetCompatibilityDialog {...props} />);
  return props;
};

describe('PresetCompatibilityDialog', () => {
  it('lists every stripped plugin', () => {
    setup();
    ['myFun.py', 'mybalance.py', 'custom.py'].forEach((name) => {
      expect(screen.getByText(name)).toBeInTheDocument();
    });
  });

  it('says the instance still gets the target runtime\'s own plugins', () => {
    // The dialog lists what this preset loses, not what the instance ends up
    // with: a cross-runtime load seeds the target runtime's default plugins
    // underneath the preset, so plugins appear that were never listed here.
    setup();
    expect(screen.getByText(/starts from/)).toBeInTheDocument();
    expect(screen.getByText(/not simply this preset's minus what is listed here/))
      .toBeInTheDocument();
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

  it('offers a replacement checkbox only where one exists', () => {
    setup();
    // myFun.py and commands.py both have a replacement offered; mybalance.py,
    // custom.py, and the auto-replaced helper do not.
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it('defaults a replacement to accepted only when the plugin was originally checked', () => {
    // Regression: every replaceable entry used to default to accepted
    // regardless of whether the operator had ever enabled it, because most
    // entries here exist only because the preset's own scripts dict is
    // seeded from its source runtime's entire default catalog for
    // compatibility scanning -- not from the operator's actual selection.
    // Confirming with those old defaults silently re-enabled the runtime's
    // entire default plugin set.
    setup();
    expect(screen.getByRole('checkbox', { name: /myFun\.py/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /commands\.py/ })).not.toBeChecked();
  });

  it('confirms with only the originally-checked accepted replacement paths', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('button', { name: /load preset/i }));
    expect(onConfirm).toHaveBeenCalledWith(['myFun.py']);
  });

  it('lets the operator opt into a replacement that was not originally checked', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('checkbox', { name: /commands\.py/ }));
    await userEvent.click(screen.getByRole('button', { name: /load preset/i }));
    expect(onConfirm.mock.calls[0][0].sort()).toEqual(['commands.py', 'myFun.py']);
  });

  it('confirms with nothing when the originally-checked replacement is unticked', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('checkbox', { name: /myFun\.py/ }));
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
