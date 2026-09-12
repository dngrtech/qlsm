import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import PluginCvarsModal from '../PluginCvarsModal';

const CVARS = [
  { cvar: 'qlx_chatRconEnabled', label: 'Enabled', description: null, type: 'bool', default: true, min: null, max: null },
  { cvar: 'qlx_chatRconRefPerm', label: 'Referee Permission Level', description: null, type: 'number', default: 3, min: 0, max: 5 },
  { cvar: 'qlx_chatRconRefCommands', label: 'Referee-Allowed Commands', description: null, type: 'string', default: 'pause,unpause', min: null, max: null },
];

describe('PluginCvarsModal', () => {
  it('prefills fields from the current server.cfg content when present', () => {
    render(
      <PluginCvarsModal
        isOpen
        onClose={vi.fn()}
        onSave={vi.fn()}
        pluginLabel="Chat RCON"
        cvars={CVARS}
        configText={'set qlx_chatRconEnabled "0"\nset qlx_chatRconRefPerm "4"\n'}
      />,
    );

    expect(screen.getByRole('checkbox', { name: 'Enabled' })).not.toBeChecked();
    expect(screen.getByRole('spinbutton', { name: 'Referee Permission Level' })).toHaveValue(4);
    expect(screen.getByRole('textbox', { name: 'Referee-Allowed Commands' })).toHaveValue('pause,unpause');
  });

  it('falls back to the manifest default when server.cfg has no value yet', () => {
    render(
      <PluginCvarsModal
        isOpen
        onClose={vi.fn()}
        onSave={vi.fn()}
        pluginLabel="Chat RCON"
        cvars={CVARS}
        configText=""
      />,
    );

    expect(screen.getByRole('checkbox', { name: 'Enabled' })).toBeChecked();
    expect(screen.getByRole('spinbutton', { name: 'Referee Permission Level' })).toHaveValue(3);
  });

  it('saves edited values as set lines merged into the existing config text', () => {
    const onSave = vi.fn();
    render(
      <PluginCvarsModal
        isOpen
        onClose={vi.fn()}
        onSave={onSave}
        pluginLabel="Chat RCON"
        cvars={CVARS}
        configText={'set sv_hostname "My Server"\n'}
      />,
    );

    fireEvent.click(screen.getByRole('checkbox', { name: 'Enabled' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Referee Permission Level' }), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(onSave).toHaveBeenCalledTimes(1);
    const nextConfig = onSave.mock.calls[0][0];
    expect(nextConfig).toContain('set sv_hostname "My Server"');
    expect(nextConfig).toContain('set qlx_chatRconEnabled "0"');
    expect(nextConfig).toContain('set qlx_chatRconRefPerm "2"');
  });

  it('calls onClose without saving on Cancel', () => {
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(
      <PluginCvarsModal
        isOpen
        onClose={onClose}
        onSave={onSave}
        pluginLabel="Chat RCON"
        cvars={CVARS}
        configText=""
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders nothing to save when the plugin declares no cvars', () => {
    render(
      <PluginCvarsModal
        isOpen
        onClose={vi.fn()}
        onSave={vi.fn()}
        pluginLabel="Empty Plugin"
        cvars={[]}
        configText=""
      />,
    );

    expect(screen.getByText(/no settings declared/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled();
  });
});
