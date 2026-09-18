import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import PluginManifestEditorModal from '../PluginManifestEditorModal';

const repo = {
  id: 3,
  name: 'Doomsday\'s Repository',
  plugins: [
    { filename: 'afkplus.py', label: 'AFK Plus', description: 'desc', runtime: 'minqlx', requires_qlsm_version: '1.36.0', cvars: [], commands: [] },
    { filename: 'lastmaps.py', label: 'Last Maps', description: '', runtime: '', requires_qlsm_version: '', commands: [{ name: 'lm', description: 'List maps.' }] },
  ],
};

describe('PluginManifestEditorModal', () => {
  beforeEach(() => {
    window.URL.createObjectURL = vi.fn(() => 'blob:manifest');
    window.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    delete window.URL.createObjectURL;
    delete window.URL.revokeObjectURL;
  });

  it('loads the repository plugins into the editor, selecting the first', () => {
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={repo} />);
    expect(screen.getByDisplayValue('afkplus.py')).toBeInTheDocument();
    expect(screen.getByText('Last Maps')).toBeInTheDocument();
  });

  it('never renders version_risk as an editable field', () => {
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={{ plugins: [{ filename: 'x.py', version_risk: { level: 'hard', message: 'nope' } }] }} />);
    expect(screen.queryByText(/version_risk|nope/i)).not.toBeInTheDocument();
  });

  it('adds a blank plugin and selects it', () => {
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={repo} />);
    fireEvent.click(screen.getByRole('button', { name: /add plugin/i }));
    // The filename field for the newly-selected (blank) plugin is empty.
    expect(screen.getByPlaceholderText('myplugin.py')).toHaveValue('');
  });

  it('flags a plugin with a bad filename as an error in the plugin list', () => {
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={{ plugins: [{ filename: 'bad name.py' }] }} />);
    expect(screen.getByText(/1 error/i)).toBeInTheDocument();
  });

  it('downloads a cleaned qlsm-plugins.json for the current draft', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={repo} />);

    fireEvent.click(screen.getByRole('button', { name: /^download/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(clickSpy.mock.instances[0].download).toBe('qlsm-plugins.json');
    clickSpy.mockRestore();
  });

  it('gives every plugin row a drag handle for reordering', () => {
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={repo} />);
    expect(screen.getByRole('button', { name: /reorder afk plus/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reorder last maps/i })).toBeInTheDocument();
  });

  it('sorts the plugin list A-Z and keeps the same plugin selected', () => {
    const reversed = {
      id: 3,
      name: 'Doomsday\'s Repository',
      plugins: [
        { filename: 'zzz.py', label: 'Zulu Plugin' },
        { filename: 'afkplus.py', label: 'AFK Plus' },
      ],
    };
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={reversed} />);

    // Loaded order is verbatim: Zulu first, and it's selected as the first row.
    let rows = screen.getAllByRole('button', { name: /^Reorder /i });
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual(['Reorder Zulu Plugin', 'Reorder AFK Plus']);
    expect(screen.getByDisplayValue('zzz.py')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /sort a–z/i }));

    rows = screen.getAllByRole('button', { name: /^Reorder /i });
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual(['Reorder AFK Plus', 'Reorder Zulu Plugin']);
    // Zulu Plugin is still the one being edited, even though it moved to row 2.
    expect(screen.getByDisplayValue('zzz.py')).toBeInTheDocument();
  });

  it('disables Sort A-Z with fewer than two plugins', () => {
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={{ plugins: [{ filename: 'x.py' }] }} />);
    expect(screen.getByRole('button', { name: /sort a–z/i })).toBeDisabled();
  });
});
