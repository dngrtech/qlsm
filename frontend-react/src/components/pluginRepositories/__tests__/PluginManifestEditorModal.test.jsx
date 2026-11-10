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

  it('downloads a cleaned qlsm-repository.json for the current draft', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={repo} />);

    fireEvent.click(screen.getByRole('button', { name: /^download/i }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(clickSpy.mock.instances[0].download).toBe('qlsm-repository.json');
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

  // A cvar arrives exactly as the repository wrote it, so `label` and
  // `description` can be missing. Bound as `value={c.label}` those inputs go
  // uncontrolled, and React -- reusing the row's DOM node across plugins --
  // left the previous plugin's text sitting in them.
  it('does not carry cvar text from one plugin over to the next', () => {
    const twoCvars = {
      id: 9,
      plugins: [
        { filename: 'a.py', label: 'Alpha', cvars: [{ cvar: 'qlx_a', type: 'number', default: 1 }] },
        { filename: 'b.py', label: 'Bravo', cvars: [{ cvar: 'qlx_b', type: 'number', default: 2 }] },
      ],
    };
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={twoCvars} />);

    fireEvent.change(screen.getByPlaceholderText('label'), { target: { value: 'TYPED-INTO-A' } });
    expect(screen.getByPlaceholderText('label')).toHaveValue('TYPED-INTO-A');

    fireEvent.click(screen.getByText('Bravo'));

    expect(screen.getByDisplayValue('qlx_b')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('label')).toHaveValue('');
  });

  it('names both rows of a duplicate filename in the issue list', () => {
    const duplicates = {
      id: 4,
      plugins: [
        { filename: 'dupe.py', label: 'One', description: 'd' },
        { filename: 'dupe.py', label: 'Two', description: 'd' },
      ],
    };
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={duplicates} />);

    const reported = screen.getAllByText(/"dupe.py" appears 2 times/);
    expect(reported).toHaveLength(2);
    expect(reported.map((el) => el.textContent)).toEqual([
      expect.stringContaining('Plugin #1'),
      expect.stringContaining('Plugin #2'),
    ]);
  });

  it('jumps to the offending plugin when its issue is clicked', () => {
    const mixed = {
      id: 5,
      plugins: [
        { filename: 'good.py', label: 'Good', description: 'd' },
        { filename: 'bad name.py', label: 'Bad', description: 'd' },
      ],
    };
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={mixed} />);

    expect(screen.getByDisplayValue('good.py')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/filename must be a bare/));
    expect(screen.getByDisplayValue('bad name.py')).toBeInTheDocument();
  });

  // PluginRepositoriesPage rebuilds the whole repos array on every silent
  // poll, so `repo` arrives as a new object with the same id.
  it('keeps in-progress edits when the repo object is replaced by a poll', () => {
    const { rerender } = render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={repo} />);

    fireEvent.change(screen.getByPlaceholderText('myplugin.py'), { target: { value: 'renamed.py' } });
    rerender(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={{ ...repo, plugins: [...repo.plugins] }} />);

    expect(screen.getByDisplayValue('renamed.py')).toBeInTheDocument();
  });

  it('offers "not set" for a cvar type and shows an unrecognized one as-is', () => {
    const oddType = {
      id: 6,
      plugins: [{ filename: 'x.py', label: 'X', description: 'd', cvars: [{ cvar: 'qlx_x', label: 'X', type: 'integer' }] }],
    };
    render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={oddType} />);

    const select = screen.getByLabelText('Cvar type');
    expect(select).toHaveValue('integer');
    expect(screen.getByRole('option', { name: 'not set' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /integer \(unrecognized\)/ })).toBeInTheDocument();
  });

  describe('addons', () => {
    const withAddons = {
      id: 7,
      name: 'Addon Repo',
      plugins: [{ filename: 'afkplus.py', label: 'AFK Plus', description: 'd' }],
      addons: [{
        id: 'my-addon', zip: 'my-addon.zip', label: 'My Addon', description: 'd', version: '1.0.0',
        sha256: 'a'.repeat(64), requires_qlsm_version: null,
      }],
    };

    const exportedBody = (blobSpy) => JSON.parse(blobSpy.mock.calls[0][0][0]);

    it('lists the repository addons on their own tab', () => {
      render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={withAddons} />);
      fireEvent.click(screen.getByRole('tab', { name: /addons \(1\)/i }));
      expect(screen.getByLabelText('Addon ID')).toHaveValue('my-addon');
      expect(screen.getByLabelText('Zip')).toHaveValue('my-addon.zip');
    });

    it('opens an addon-only repository on the Addons tab', () => {
      render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={{ id: 8, plugins: [], addons: withAddons.addons }} />);
      expect(screen.getByRole('tab', { name: /addons/i })).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByLabelText('Addon ID')).toHaveValue('my-addon');
    });

    it('adds, edits and removes addons, and exports them', () => {
      const blobSpy = vi.spyOn(globalThis, 'Blob').mockImplementation(function FakeBlob(parts) { this.parts = parts; });
      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={withAddons} />);
      fireEvent.click(screen.getByRole('tab', { name: /addons/i }));

      fireEvent.click(screen.getByRole('button', { name: /add addon/i }));
      expect(screen.getByLabelText('Addon ID')).toHaveValue('');
      fireEvent.change(screen.getByLabelText('Addon ID'), { target: { value: 'second' } });
      fireEvent.change(screen.getByLabelText('Zip'), { target: { value: 'second.zip' } });

      fireEvent.click(screen.getByRole('button', { name: /remove my addon/i }));
      // The added addon is still the one being edited after the row above it went.
      expect(screen.getByLabelText('Addon ID')).toHaveValue('second');

      fireEvent.click(screen.getByRole('button', { name: /^download/i }));
      const body = exportedBody(blobSpy);
      expect(body.addons).toEqual([{ id: 'second', zip: 'second.zip' }]);
      expect(body.plugins).toEqual([{ filename: 'afkplus.py', label: 'AFK Plus', description: 'd' }]);

      blobSpy.mockRestore();
      clickSpy.mockRestore();
    });

    it('counts an addon error and jumps to the addon when the issue is clicked', () => {
      const bad = { ...withAddons, addons: [{ ...withAddons.addons[0], id: 'Bad Id' }] };
      render(<PluginManifestEditorModal isOpen onClose={vi.fn()} repo={bad} />);
      // Opens on plugins; the addon's error is still counted in the footer.
      expect(screen.getByText(/1 error/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue('afkplus.py')).toBeInTheDocument();

      fireEvent.click(screen.getByText(/id must be kebab-case/));
      expect(screen.getByRole('tab', { name: /addons/i })).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByLabelText('Addon ID')).toHaveValue('Bad Id');
    });
  });
});
