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

  it('renders nothing when there is no compatibility block', () => {
    const { container } = render(
      <PresetCompatibilityDialog isOpen compatibility={null} onCancel={vi.fn()} onConfirm={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
