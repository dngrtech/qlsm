import React, { useImperativeHandle } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createPreset: vi.fn(),
  downloadPreset: vi.fn(),
  flushEdits: vi.fn(),
  fetchInstanceHooks: vi.fn(),
  getBinaryMeta: vi.fn(),
  getFactoryContent: vi.fn(),
  getFactoryTree: vi.fn(),
  getInstanceById: vi.fn(),
  getInstanceConfig: vi.fn(),
  getPresetById: vi.fn(),
  getPresets: vi.fn(),
  saveBinaryMeta: vi.fn(),
  showError: vi.fn(),
  showSuccess: vi.fn(),
  hooksTabProps: [],
  updateInstance: vi.fn(),
  updateInstanceConfig: vi.fn(),
  updatePreset: vi.fn(),
  fileManagerProps: [],
  qlentLanguage: { name: 'qlent' },
  qlentLinter: vi.fn(),
  useDraftWorkspace: vi.fn(),
  // Last acceptedReplacements the plugin draft adapter saw for each preset name --
  // proves whether a stale accepted list from a previous preset leaked onto this one.
  draftAdapterAcceptedReplacementsByPreset: {},
}));

vi.mock('@headlessui/react', () => {
  const Dialog = ({ children }) => <div>{children}</div>;
  Dialog.Panel = ({ children, transition: _transition, ...props }) => {
    void _transition;
    return <div {...props}>{children}</div>;
  };
  Dialog.Title = ({ children, ...props }) => <div {...props}>{children}</div>;
  const DialogBackdrop = ({ children, transition: _transition, ...props }) => {
    void _transition;
    return <div {...props}>{children}</div>;
  };

  const Transition = ({ show, children }) => (show ? <>{children}</> : null);
  Transition.Child = ({ children }) => <>{children}</>;

  return { Dialog, DialogBackdrop, Transition };
});

vi.mock('../../../services/api', () => ({
  createPreset: mocks.createPreset,
  downloadPreset: mocks.downloadPreset,
  getFactoryContent: mocks.getFactoryContent,
  getFactoryTree: mocks.getFactoryTree,
  fetchInstanceHooks: mocks.fetchInstanceHooks,
  getInstanceById: mocks.getInstanceById,
  getInstanceConfig: mocks.getInstanceConfig,
  getPresetById: mocks.getPresetById,
  getPresets: mocks.getPresets,
  updateInstance: mocks.updateInstance,
  updateInstanceConfig: mocks.updateInstanceConfig,
  updatePreset: mocks.updatePreset,
}));

vi.mock('../../../services/draftApi', () => ({
  getBinaryMeta: mocks.getBinaryMeta,
  saveBinaryMeta: mocks.saveBinaryMeta,
}));

vi.mock('../../NotificationProvider', () => ({
  useNotification: () => ({
    showError: mocks.showError,
    showSuccess: mocks.showSuccess,
  }),
}));

vi.mock('../../ExpandedEditorModal', () => ({
  default: () => null,
}));

vi.mock('../../ConfirmationModal', () => ({
  default: () => null,
}));

vi.mock('../../presetManager/PresetManagerModal', () => ({
  default: ({ isOpen, onSavePreset, onLoadPreset, savedPreset }) => (
    isOpen ? (
      <div data-testid="preset-manager">
        <button
          type="button"
          onClick={() => onSavePreset({ name: 'saved-from-edit', description: 'copy' })}
        >
          Confirm Save Preset
        </button>
        <button
          type="button"
          onClick={() => onLoadPreset('99')}
        >
          Confirm Load Preset
        </button>
        {savedPreset && (
          <button
            type="button"
            onClick={async () => {
              const blob = await mocks.downloadPreset(savedPreset.id);
              const url = window.URL.createObjectURL(blob);
              const link = document.createElement('a');
              link.href = url;
              link.download = `${String(savedPreset.name).replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '')}.zip`;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              window.URL.revokeObjectURL(url);
            }}
          >
            Download Preset
          </button>
        )}
      </div>
    ) : null
  ),
}));

vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="info-tooltip">{text}</span>,
}));

vi.mock('../HooksTab', () => ({
  default: (props) => {
    mocks.hooksTabProps.push(props);
    return (
      <div>
        <div>hooks-tab</div>
        <button type="button" onClick={() => props.onToggleHook?.('c.so')}>
          Mock Toggle c.so
        </button>
      </div>
    );
  },
}));

vi.mock('../../fileManager', () => ({
  CONFIG_CAPS: {
    allowedExtensions: ['.cfg', '.txt', '.ent'],
    protectedFiles: ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'],
  },
  PLUGIN_CAPS: {
    allowedExtensions: ['.py', '.txt', '.so'],
    protectedFiles: [],
  },
  FACTORY_CAPS: {
    allowedExtensions: ['.factories'],
    protectedFiles: [],
  },
  FileManager: React.forwardRef(function MockFileManager(props, ref) {
    mocks.fileManagerProps.push(props);
    useImperativeHandle(ref, () => ({
      flushEdits: mocks.flushEdits,
    }));
    const [newFolderStep, setNewFolderStep] = React.useState(null); // { parent } | { parent, opening: true }
    const [newFolderName, setNewFolderName] = React.useState('');
    const folders = props.adapter?.folders ?? [];
    return (
      <div>
        file-manager
        {folders.map((folderPath) => (
          <div key={folderPath}>
            <span>{folderPath}</span>
            <button
              type="button"
              aria-label={`folder actions for ${folderPath}`}
              onClick={() => setNewFolderStep({ parent: folderPath, opening: true })}
            >
              folder actions
            </button>
            {newFolderStep?.parent === folderPath && newFolderStep.opening && (
              <button
                type="button"
                onClick={() => setNewFolderStep({ parent: folderPath, opening: false })}
              >
                New Folder
              </button>
            )}
            {newFolderStep?.parent === folderPath && newFolderStep.opening === false && (
              <div>
                <label htmlFor="mock-new-folder-name">Folder Name</label>
                <input
                  id="mock-new-folder-name"
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => {
                    props.adapter.createFolder(`${folderPath}/${newFolderName}`);
                    setNewFolderStep(null);
                    setNewFolderName('');
                  }}
                >
                  Create
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }),
  useDraftAdapter: ({ preset, acceptedReplacements } = {}) => {
    if (preset) {
      mocks.draftAdapterAcceptedReplacementsByPreset[preset] = acceptedReplacements || [];
    }
    return {
      ...mocks.useDraftWorkspace(),
      hasChanges: false,
    };
  },
  useStateAdapter: ({ initialFiles = {}, initialFolders = [], serverTree = [] } = {}) => {
    const [files, setFiles] = React.useState(initialFiles);
    const [folders, setFolders] = React.useState(initialFolders);
    const reset = React.useCallback((nextFiles = {}, nextFolders = []) => {
      setFiles(nextFiles);
      setFolders(nextFolders);
    }, []);
    const createFolder = React.useCallback((path) => {
      setFolders(prev => (prev.includes(path) ? prev : [...prev, path]));
    }, []);
    return React.useMemo(() => ({
      tree: serverTree,
      folders,
      createFolder,
      readContent: vi.fn().mockResolvedValue(''),
      writeContent: vi.fn().mockResolvedValue(undefined),
      upload: vi.fn().mockResolvedValue({}),
      deleteFile: vi.fn().mockResolvedValue(undefined),
      renameFile: vi.fn().mockResolvedValue(undefined),
      checkedFiles: new Set(Object.keys(files)),
      setChecked: vi.fn().mockResolvedValue(undefined),
      hasChanges: false,
      serialize: () => ({ files: { ...files }, folders: [...folders] }),
      reset,
      loading: false,
      error: null,
    }), [files, folders, createFolder, reset, serverTree]);
  },
}));

vi.mock('../../../codemirror-lang-qlcfg', () => ({
  qlcfgLanguage: {},
  createQlCfgLinter: vi.fn(() => vi.fn()),
  stripManagedCvars: vi.fn((value) => value),
}));

vi.mock('../../../codemirror-lang-qlmappool', () => ({
  qlmappoolLanguage: {},
}));

vi.mock('../../../codemirror-lang-qlaccess', () => ({
  qlaccessLanguage: {},
}));

vi.mock('../../../codemirror-lang-qlworkshop', () => ({
  qlworkshopLanguage: {},
}));

vi.mock('../../../codemirror-lang-qlent', () => ({
  qlentLanguage: mocks.qlentLanguage,
  qlentLinter: mocks.qlentLinter,
}));

const baseDraftWorkspace = {
  draftId: 'draft-123',
  tree: [
    {
      type: 'folder',
      name: 'discord_extensions',
      path: 'discord_extensions',
      children: [
        {
          type: 'file',
          name: 'balance.py',
          path: 'discord_extensions/balance.py',
        },
      ],
    },
  ],
  loading: false,
  error: null,
  refreshTree: vi.fn(),
  readContent: vi.fn(),
  writeContent: vi.fn(),
  upload: vi.fn(),
  deleteFile: vi.fn(),
  commit: vi.fn(),
  discard: vi.fn(),
  consume: vi.fn(),
};

describe('EditInstanceConfigModal preset saving', () => {
  let EditInstanceConfigModal;

  beforeEach(async () => {
    vi.clearAllMocks();
    mocks.fileManagerProps = [];
    mocks.hooksTabProps = [];
    mocks.draftAdapterAcceptedReplacementsByPreset = {};
    if (!EditInstanceConfigModal) {
      ({ default: EditInstanceConfigModal } = await import('../EditInstanceConfigModal'));
    }
    mocks.createPreset.mockResolvedValue({ message: 'saved', data: { id: 42, name: 'saved-from-edit' } });
    mocks.downloadPreset.mockResolvedValue(new Blob(['zip-bytes'], { type: 'application/zip' }));
    mocks.flushEdits.mockResolvedValue(undefined);
    mocks.fetchInstanceHooks.mockResolvedValue({
      available: [
        { filename: 'a.so', size: 1, modified: 1, enabled: true, order: 1, description: '' },
        { filename: 'c.so', size: 1, modified: 1, enabled: false, order: null, description: '' },
      ],
      missing: [],
      system_hooks_active: [],
    });
    mocks.getBinaryMeta.mockResolvedValue({});
    mocks.getFactoryContent.mockResolvedValue({ content: '' });
    mocks.getFactoryTree.mockResolvedValue([]);
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host',
      lan_rate_enabled: false,
      status: 'running',
      name: 'inst',
      qlx_plugins: 'balance',
    });
    mocks.getInstanceConfig.mockResolvedValue({
      'server.cfg': 'set sv_hostname "Test123"',
      'mappool.txt': '',
      'access.txt': '',
      'workshop.txt': '',
      factories: {},
    });
    mocks.getPresetById.mockResolvedValue(null);
    mocks.getPresets.mockResolvedValue([]);
    mocks.saveBinaryMeta.mockResolvedValue({});
    mocks.updateInstance.mockResolvedValue({});
    mocks.updateInstanceConfig.mockResolvedValue({ message: 'ok' });
    mocks.updatePreset.mockResolvedValue({ message: 'updated', data: { id: 42, name: 'saved-from-edit' } });
    mocks.useDraftWorkspace.mockReturnValue(baseDraftWorkspace);
    window.URL.createObjectURL = vi.fn(() => 'blob:qlsm-preset');
    window.URL.revokeObjectURL = vi.fn();
    vi.spyOn(document.body, 'appendChild');
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  it('preserves checked plugin file paths when saving a preset from edit mode', async () => {
    // Root-level plugin (not a subfolder match) so it's actually enableable
    // and gets ticked by the load-resolution effect.
    mocks.useDraftWorkspace.mockReturnValue({
      ...baseDraftWorkspace,
      tree: [{ type: 'file', name: 'balance.py', path: 'balance.py' }],
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    expect(mocks.createPreset).toHaveBeenCalledWith(
      expect.objectContaining({
        draft_id: 'draft-123',
        // Full path (extension retained) proves Save Preset preserves the raw
        // checkedPlugins entries rather than flattening them like Save Configuration does.
        checked_plugins: ['balance.py'],
        factories: {},
        checked_factories: [],
      })
    );
  });

  it('includes lan_rate_enabled when saving a preset from edit mode', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host',
      host_os_type: 'debian',
      lan_rate_enabled: true,
      status: 'running',
      name: 'inst',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    expect(mocks.createPreset.mock.calls[0][0].lan_rate_enabled).toBe(true);
  });

  it('includes lan_rate_enabled: false when saving a preset with the toggle off', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host',
      host_os_type: 'debian',
      lan_rate_enabled: false,
      status: 'running',
      name: 'inst',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    expect(mocks.createPreset.mock.calls[0][0].lan_rate_enabled).toBe(false);
  });

  it('applies lan_rate_enabled from a loaded preset and forces a restart', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host',
      host_os_type: 'debian',
      lan_rate_enabled: false,
      status: 'running',
      name: 'inst',
      qlx_plugins: '',
    });
    mocks.getPresetById.mockResolvedValue({
      name: 'lan-preset',
      configs: {},
      factories: {},
      lan_rate_enabled: true,
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    // Drive restartAfterSave to false before the preset load so the
    // post-load assertion is diagnostic of the forcing logic in
    // handleLoadPreset, rather than just observing the mount-time default
    // (restartAfterSave starts true on open, per line ~100/~318).
    const restartToggle = screen.getByRole('button', { name: /toggle restart after save/i });
    expect(restartToggle).not.toBeDisabled();
    fireEvent.click(restartToggle);
    expect(restartToggle).toHaveAttribute('aria-pressed', 'false');

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith('99', { targetRuntime: 'minqlx' }));
    await waitFor(() => expect(toggle).toHaveAttribute('aria-pressed', 'true'));

    expect(restartToggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('clamps a preset lan_rate_enabled=true to false on an unsupported host', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: false,
      lan_rate_enabled: false,
      name: 'UbuntuInst',
      qlx_plugins: '',
    });
    mocks.getPresetById.mockResolvedValue({
      name: 'lan-preset',
      configs: {},
      factories: {},
      lan_rate_enabled: true,
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="UbuntuInst"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith('99', { targetRuntime: 'minqlx' }));

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-pressed', 'false'));
  });

  it('does not disable an already-enabled legacy-host instance when the loaded preset also wants it on', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: false,
      lan_rate_enabled: true,
      status: 'running',
      name: 'UbuntuInst',
      qlx_plugins: '',
    });
    mocks.getPresetById.mockResolvedValue({
      name: 'lan-preset',
      configs: {},
      factories: {},
      lan_rate_enabled: true,
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="UbuntuInst"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).toHaveAttribute('aria-pressed', 'true');

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith('99', { targetRuntime: 'minqlx' }));
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('leaves the lan rate toggle untouched when the loaded preset has no recorded value', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host',
      host_os_type: 'debian',
      lan_rate_enabled: true,
      status: 'running',
      name: 'inst',
      qlx_plugins: '',
    });
    mocks.getPresetById.mockResolvedValue({
      name: 'legacy-preset',
      configs: {},
      factories: {},
      lan_rate_enabled: null,
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-pressed', 'true'));

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith('99', { targetRuntime: 'minqlx' }));
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps the save modal open and downloads the saved preset archive', async () => {
    const onClose = vi.fn();

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={onClose}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    const downloadButton = await screen.findByRole('button', { name: /download preset/i });
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(downloadButton);

    await waitFor(() => expect(mocks.downloadPreset).toHaveBeenCalledWith(42));
    expect(window.URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    const anchor = document.body.appendChild.mock.calls.find(
      ([node]) => node instanceof HTMLAnchorElement,
    )?.[0];
    expect(anchor).toEqual(expect.objectContaining({
      href: 'blob:qlsm-preset',
      download: 'saved-from-edit.zip',
    }));
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:qlsm-preset');
  });

  it('sanitizes unsafe saved preset names before downloading', async () => {
    mocks.createPreset.mockResolvedValue({
      message: 'saved',
      data: { id: 42, name: '../Unsafe Name\nWith Spaces' },
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    const downloadButton = await screen.findByRole('button', { name: /download preset/i });
    fireEvent.click(downloadButton);

    await waitFor(() => expect(mocks.downloadPreset).toHaveBeenCalledWith(42));
    const anchor = document.body.appendChild.mock.calls.find(
      ([node]) => node instanceof HTMLAnchorElement,
    )?.[0];
    expect(anchor.download).toBe('Unsafe-Name-With-Spaces.zip');
  });

  it('sends factory adapter files when saving instance configuration', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));

    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    expect(mocks.updateInstanceConfig).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        factories: {},
      }),
      true,
    );
  });

  it('creates a nested subfolder via the row menu and includes it in the config_folders payload', async () => {
    mocks.getInstanceConfig.mockResolvedValue({
      'server.cfg': 'set sv_hostname "Test123"',
      'mappool.txt': '',
      'access.txt': '',
      'workshop.txt': '',
      factories: {},
      config_folders: ['existingFolder'],
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('button', { name: /folder actions for existingFolder/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /folder actions for existingFolder/i }));
    fireEvent.click(screen.getByRole('button', { name: /new folder/i }));
    fireEvent.change(screen.getByLabelText(/folder name/i), { target: { value: 'newSubfolder' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));

    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    expect(mocks.updateInstanceConfig.mock.calls[0][1].config_folders).toContain('existingFolder/newSubfolder');
  });

  it('shows the Save Configuration button on the Hooks tab', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
        initialTab="hooks"
      />
    );

    await waitFor(() => expect(screen.getByText('hooks-tab')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument();
  });

  it('Save payload carries enabled_hooks reflecting toggles', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
        initialTab="hooks"
      />
    );

    await waitFor(() => expect(screen.getByText('hooks-tab')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /mock toggle c.so/i }));
    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));

    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    expect(mocks.updateInstanceConfig.mock.calls[0][1].enabled_hooks).toEqual(['a.so', 'c.so']);
  });

  it('shows the preset buttons on the hooks tab and Save Preset captures the live hook draft', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
        initialTab="hooks"
      />
    );

    await waitFor(() => expect(screen.getByText('hooks-tab')).toBeInTheDocument());
    // Preset buttons must be present on the hooks tab, same as every other tab.
    expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument();

    // A hook toggle made on this tab must be reflected in the saved preset.
    fireEvent.click(screen.getByRole('button', { name: /mock toggle c.so/i }));
    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    expect(mocks.createPreset.mock.calls[0][0].enabled_hooks).toEqual(['a.so', 'c.so']);
  });

  it('forces + disables restart toggle when hooks change on a RUNNING instance', async () => {
    mocks.getInstanceById.mockResolvedValue({ host_name: 'h', lan_rate_enabled: false, status: 'running', name: 'i' });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        instanceId={1}
        onClose={vi.fn()}
        initialTab="hooks"
      />
    );

    await waitFor(() => expect(screen.getByText('hooks-tab')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Mock Toggle c.so'));
    const toggle = screen.getByRole('button', { name: /toggle restart after save/i });
    await waitFor(() => expect(toggle).toBeDisabled());
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Changing hooks requires an instance restart')).toBeInTheDocument();
  });

  it('keeps restart off and disabled when hooks change on a STOPPED instance', async () => {
    mocks.getInstanceById.mockResolvedValue({ host_name: 'h', lan_rate_enabled: false, status: 'stopped', name: 'i' });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        initialTab="hooks"
      />
    );

    await waitFor(() => expect(screen.getByText('hooks-tab')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Mock Toggle c.so'));
    const toggle = screen.getByRole('button', { name: /toggle restart after save/i });
    await waitFor(() => expect(toggle).toBeDisabled());
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Stopped instances stay stopped when hook changes are saved')).toBeInTheDocument();
  });

  it('does NOT send enabled_hooks when the hooks fetch failed on open', async () => {
    mocks.fetchInstanceHooks.mockRejectedValueOnce(new Error('hooks unavailable'));

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
        initialTab="config"
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));

    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    expect(mocks.updateInstanceConfig.mock.calls[0][1]).not.toHaveProperty('enabled_hooks');
  });

  it('an unrelated Save preserves the loaded hooks', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
        initialTab="config"
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));

    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    expect(mocks.updateInstanceConfig.mock.calls[0][1].enabled_hooks).toEqual(['a.so']);
  });

  it('disables enabling 99k lan rate for ubuntu hosts', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: false,
      lan_rate_enabled: false,
      name: 'UbuntuInst',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={7}
        instanceName="UbuntuInst"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).toBeDisabled();
    expect(screen.getByTestId('info-tooltip')).toHaveTextContent(/99k LAN Rate currently requires Debian/);
  });

  it('enables 99k lan rate on a migrated ubuntu host (lan_rate_uses_hook: true)', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-migrated',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: true,
      lan_rate_enabled: false,
      name: 'UbuntuMigrated',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={10}
        instanceName="UbuntuMigrated"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).not.toBeDisabled();
    expect(screen.queryByTestId('info-tooltip')).not.toBeInTheDocument();
  });

  it('allows disabling an already-enabled ubuntu instance', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      host_lan_rate_uses_hook: false,
      lan_rate_enabled: true,
      name: 'UbuntuInst',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={8}
        instanceName="UbuntuInst"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(toggle);

    expect(toggle).toBeDisabled();
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    const tooltips = screen.getAllByTestId('info-tooltip');
    expect(tooltips.some(t => /99k LAN Rate currently requires Debian/.test(t.textContent))).toBe(true);
  });

  it('allows enabling 99k lan rate for legacy debian12 host records', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'debian-host',
      host_os_type: 'debian12',
      lan_rate_enabled: false,
      name: 'DebianInst',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={9}
        instanceName="DebianInst"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByText('99k LAN rate is only supported on Debian hosts.')).not.toBeInTheDocument();
  });

  it('uses python highlighting for plugin .py files', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /plugins/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /plugins/i }));

    await waitFor(() => {
      expect(mocks.fileManagerProps.some(props => props.binaryContext?.contextType === 'instance')).toBe(true);
    });
    const pluginManagerProps = mocks.fileManagerProps.find(
      props => props.binaryContext?.contextType === 'instance',
    );

    expect(pluginManagerProps.getLanguageForFile('balance.py')).toBeTruthy();
    expect(pluginManagerProps.getLanguageForFile('readme.txt')).toBeNull();
    expect(pluginManagerProps.onExpandEditor).toEqual(expect.any(Function));
  });

  it('uses entity highlighting and linting for .ent config files', async () => {
    mocks.getInstanceConfig.mockResolvedValue({
      'server.cfg': 'set sv_hostname "Test123"',
      'mappool.txt': '',
      'access.txt': '',
      'workshop.txt': '',
      'custom_entities/items.ent': '{\n"classname" "worldspawn"\n}',
      factories: {},
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument());
    const configManagerProps = mocks.fileManagerProps.find(props => props.defaultSelectedPath === 'server.cfg');

    expect(configManagerProps.getLanguageForFile('custom_entities/items.ent')).toBe(mocks.qlentLanguage);
    expect(configManagerProps.getLinterSourceForFile('custom_entities/items.ent')).toBe(mocks.qlentLinter);
  });

  it('uses JSON highlighting and linting for factory files', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /factories/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /factories/i }));

    await waitFor(() => {
      expect(mocks.fileManagerProps.some(
        props => props.capabilities.allowedExtensions.includes('.factories'),
      )).toBe(true);
    });
    const factoryManagerProps = mocks.fileManagerProps.find(
      props => props.capabilities.allowedExtensions.includes('.factories'),
    );

    expect(factoryManagerProps.getLanguageForFile('ca.factories')).toBeTruthy();
    expect(factoryManagerProps.getLinterSourceForFile('ca.factories')).toEqual(expect.any(Function));
    expect(factoryManagerProps.getLanguageForFile('readme.txt')).toBeNull();
    expect(factoryManagerProps.getLinterSourceForFile('readme.txt')).toBeNull();
    expect(factoryManagerProps.onExpandEditor).toEqual(expect.any(Function));
  });

  it('opens on the hooks tab with controlled hook props', async () => {
    const onClose = vi.fn();
    const onConfigSaved = vi.fn();

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={onClose}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={onConfigSaved}
        initialTab="hooks"
      />
    );

    await waitFor(() => expect(screen.getByText('hooks-tab')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /^hooks$/i })).toHaveClass('text-[var(--accent-primary)]');
    expect(onConfigSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(mocks.hooksTabProps.at(-1)).toEqual(expect.objectContaining({
      instanceId: 1,
      enabledOrder: ['a.so'],
      dirty: false,
    }));
  });

  describe('non-enableable plugins', () => {
    const getPluginManagerProps = () => mocks.fileManagerProps
      .filter(props => props.binaryContext?.contextType === 'instance')
      .at(-1);

    it('does not tick a qlx_plugins name that only exists in a subfolder, and shows the notice', async () => {
      mocks.getInstanceById.mockResolvedValue({
        host_name: 'test-host',
        lan_rate_enabled: false,
        status: 'running',
        name: 'inst',
        qlx_plugins: 'admin, essentials',
      });
      mocks.useDraftWorkspace.mockReturnValue({
        ...baseDraftWorkspace,
        tree: [
          {
            type: 'folder',
            name: 'discord_extensions',
            path: 'discord_extensions',
            children: [
              { type: 'file', name: 'admin.py', path: 'discord_extensions/admin.py' },
            ],
          },
          { type: 'file', name: 'essentials.py', path: 'essentials.py' },
        ],
      });

      render(
        <EditInstanceConfigModal
          isOpen={true}
          onClose={vi.fn()}
          instanceId={1}
          instanceName="Test123"
          onConfigSaved={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByRole('button', { name: /plugins/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /plugins/i }));

      await waitFor(() => {
        expect([...(getPluginManagerProps()?.checkedFiles ?? [])]).toEqual(['essentials.py']);
      });
      expect(screen.getByRole('status')).toHaveTextContent(
        "1 plugin that can't be enabled was deselected"
      );
    });

    it('drops non-enableable entries when loading a preset and shows the notice', async () => {
      mocks.getInstanceById.mockResolvedValue({
        host_name: 'test-host',
        lan_rate_enabled: false,
        status: 'running',
        name: 'inst',
        qlx_plugins: '',
      });
      mocks.getPresetById.mockResolvedValue({
        name: 'my-preset',
        configs: {},
        factories: {},
        checked_plugins: ['balance.py', 'extras/textart.py', '__init__.py'],
      });

      render(
        <EditInstanceConfigModal
          isOpen={true}
          onClose={vi.fn()}
          instanceId={1}
          instanceName="Test123"
          onConfigSaved={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith('99', { targetRuntime: 'minqlx' }));

      fireEvent.click(screen.getByRole('button', { name: /plugins/i }));
      await waitFor(() => {
        expect([...(getPluginManagerProps()?.checkedFiles ?? [])]).toEqual(['balance.py']);
      });
      expect(screen.getByRole('status')).toHaveTextContent(
        "2 plugins that can't be enabled were deselected"
      );
    });

    it('excludes subfolder plugins from the saved checked_plugins payload', async () => {
      mocks.getInstanceById.mockResolvedValue({
        host_name: 'test-host',
        lan_rate_enabled: false,
        status: 'running',
        name: 'inst',
        qlx_plugins: 'admin, essentials',
      });
      mocks.useDraftWorkspace.mockReturnValue({
        ...baseDraftWorkspace,
        tree: [
          {
            type: 'folder',
            name: 'discord_extensions',
            path: 'discord_extensions',
            children: [
              { type: 'file', name: 'admin.py', path: 'discord_extensions/admin.py' },
            ],
          },
          { type: 'file', name: 'essentials.py', path: 'essentials.py' },
        ],
      });

      render(
        <EditInstanceConfigModal
          isOpen={true}
          onClose={vi.fn()}
          instanceId={1}
          instanceName="Test123"
          onConfigSaved={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument());
      // Wait for the load-resolution effect to settle before saving, or the
      // click can race ahead of the async plugin-tree resolution.
      fireEvent.click(screen.getByRole('button', { name: /plugins/i }));
      await waitFor(() => {
        expect([...(getPluginManagerProps()?.checkedFiles ?? [])]).toEqual(['essentials.py']);
      });

      fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));

      await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
      const payload = mocks.updateInstanceConfig.mock.calls[0][1];
      expect(payload.checked_plugins).not.toContain('admin');
      expect(payload.checked_plugins).toEqual(['essentials']);
    });

    it('hides the notice once dismissed', async () => {
      mocks.getInstanceById.mockResolvedValue({
        host_name: 'test-host',
        lan_rate_enabled: false,
        status: 'running',
        name: 'inst',
        qlx_plugins: 'admin, essentials',
      });
      mocks.useDraftWorkspace.mockReturnValue({
        ...baseDraftWorkspace,
        tree: [
          {
            type: 'folder',
            name: 'discord_extensions',
            path: 'discord_extensions',
            children: [
              { type: 'file', name: 'admin.py', path: 'discord_extensions/admin.py' },
            ],
          },
          { type: 'file', name: 'essentials.py', path: 'essentials.py' },
        ],
      });

      render(
        <EditInstanceConfigModal
          isOpen={true}
          onClose={vi.fn()}
          instanceId={1}
          instanceName="Test123"
          onConfigSaved={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));

      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });
  });

  describe('preset compatibility gate on load', () => {
    const renderModal = () => render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    it('sends the host runtime with the preset fetch', async () => {
      mocks.getPresetById.mockResolvedValue({ name: 'my-preset', configs: {}, factories: {} });
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith('99', { targetRuntime: 'minqlx' }));
    });

    it('applies directly when the response carries no compatibility block', async () => {
      mocks.getPresetById.mockResolvedValue({ name: 'my-preset', configs: {}, factories: {} });
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "my-preset" loaded successfully.'));
      expect(screen.queryByText(/won.t carry over/i)).not.toBeInTheDocument();
    });

    it('does not apply a preset immediately when the response has stripped plugins', async () => {
      // The matched-pair regression test: without the compatibility gate this
      // response would apply exactly like the no-compatibility-block case
      // above, so showSuccess firing here is the bug the gate exists to
      // prevent.
      mocks.getPresetById.mockResolvedValue({
        name: 'my-preset',
        configs: {},
        factories: {},
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [
            { path: 'essentials.py', verdict: 'incompatible', reasons: ['uses a minqlxtended-only API'], replacement: null },
          ],
          replacements: {},
        },
      });
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await screen.findByText(/won.t carry over/i);
      expect(mocks.showSuccess).not.toHaveBeenCalled();
    });

    it('applies a cross-runtime preset silently when every plugin is compatible', async () => {
      // stripped: [] is a real response shape -- every plugin scanned clean --
      // and it must not surface a dialog with nothing in it.
      mocks.getPresetById.mockResolvedValue({
        name: 'my-preset',
        configs: {},
        factories: {},
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [],
          replacements: {},
        },
      });
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "my-preset" loaded successfully.'));
      expect(screen.queryByText(/won.t carry over/i)).not.toBeInTheDocument();
    });

    it('does not carry a confirmed preset\'s accepted replacements onto the next preset loaded', async () => {
      // Regression: handleLoadPreset used to leave acceptedReplacements untouched
      // when the next load needed no compatibility confirmation of its own, so a
      // stale accepted filename from preset A rode along into preset B's draft
      // seed. Fixed by clearing at the top of every load; only the compatibility
      // dialog's confirm handler is allowed to repopulate it.
      mocks.getPresetById
        .mockResolvedValueOnce({
          name: 'presetA',
          configs: {},
          factories: {},
          compatibility: {
            preset_runtime: 'minqlxtended',
            target_runtime: 'minqlx',
            stripped: [
              {
                path: 'essentials.py',
                verdict: 'incompatible',
                reasons: ['uses a minqlxtended-only API'],
                replacement: 'essentials_mqx.py',
              },
            ],
            replacements: { 'essentials.py': 'essentials_mqx.py' },
          },
        })
        .mockResolvedValueOnce({ name: 'presetB', configs: {}, factories: {} });
      renderModal();

      // Load preset A and confirm the compatibility dialog, accepting the one
      // offered replacement (pre-checked by the dialog itself).
      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      // @headlessui/react is mocked to plain <div>s in this file (no role="dialog"
      // to scope by), so disambiguate from the outer "Load Preset" trigger by DOM
      // order: PresetCompatibilityDialog's own confirm button renders last.
      const loadPresetButtons = screen.getAllByRole('button', { name: /load preset/i });
      fireEvent.click(loadPresetButtons[loadPresetButtons.length - 1]);

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "presetA" loaded successfully.'));
      expect(mocks.draftAdapterAcceptedReplacementsByPreset.presetA).toEqual(['essentials.py']);

      // Now load preset B, which needs no confirmation of its own.
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "presetB" loaded successfully.'));
      expect(mocks.draftAdapterAcceptedReplacementsByPreset.presetB).toEqual([]);
    });
  });
});
