import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import PresetCompatibilityDialog from '../PresetCompatibilityDialog';

const compatibility = {
  preset_runtime: 'minqlx',
  target_runtime: 'minqlxtended',
  stripped: [
    { path: 'myFun.py', verdict: 'incompatible', reasons: ['line 3: imports the minqlx module'], replacement: 'myFun.py' },
    { path: 'mybalance.py', verdict: 'incompatible', reasons: ['line 1: references the minqlx module'], replacement: null },
    { path: 'custom.py', verdict: 'unknown', reasons: [], replacement: null },
    {
      path: 'discord_extensions/admin.py',
      verdict: 'incompatible',
      reasons: ['line 11: imports the minqlx module'],
      replacement: null,
      auto_replaced: true,
    },
  ],
  replacements: { 'myFun.py': 'import minqlxtended\n' },
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
    expect(screen.getByText(/imports the minqlx module/)).toBeInTheDocument();
  });

  it('explains an unknown verdict rather than leaving it blank', () => {
    // "custom.py was removed" with no cause is not an answer.
    setup();
    expect(screen.getByText(/not part of the .* baseline/i)).toBeInTheDocument();
  });

  it('offers a replacement checkbox only where one exists', () => {
    setup();
    expect(screen.getAllByRole('checkbox')).toHaveLength(1);
  });

  it('defaults the replacement to accepted', () => {
    setup();
    expect(screen.getByRole('checkbox')).toBeChecked();
  });

  it('confirms with the accepted replacement paths', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('button', { name: /load preset/i }));
    expect(onConfirm).toHaveBeenCalledWith(['myFun.py']);
  });

  it('confirms with nothing when the replacement is unticked', async () => {
    const { onConfirm } = setup();
    await userEvent.click(screen.getByRole('checkbox'));
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
    // One checkbox in the whole dialog: myFun.py, the only entry with a replacement.
    expect(screen.getAllByRole('checkbox')).toHaveLength(1);
  });

  it('renders nothing when there is no compatibility block', () => {
    const { container } = render(
      <PresetCompatibilityDialog isOpen compatibility={null} onCancel={vi.fn()} onConfirm={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
