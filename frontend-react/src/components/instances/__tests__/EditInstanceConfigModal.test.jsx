import React, { useImperativeHandle } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createPreset: vi.fn(),
  downloadPreset: vi.fn(),
  flushEdits: vi.fn(),
  fetchInstanceHooks: vi.fn(),
  getInstanceAdmins: vi.fn(),
  getBinaryMeta: vi.fn(),
  getFactoryContent: vi.fn(),
  getFactoryTree: vi.fn(),
  getInstanceById: vi.fn(),
  getInstanceConfig: vi.fn(),
  getPresetById: vi.fn(),
  getPresets: vi.fn(),
  previewPresetApply: vi.fn(),
  discardDraft: vi.fn(),
  getDeferRestartsSetting: vi.fn(),
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
  // Every existingDraftId the plugin draft adapter was rendered with: shows
  // which server-made draft the Plugins tab works on.
  draftAdapterExistingDraftIds: [],
  // The same, only for renders where the workspace is active (would adopt it).
  draftAdapterActiveDraftIds: [],
  // instance_tabs an installed addon contributes; empty unless a test sets it.
  addonMounts: [],
  addonPanelSubmit: vi.fn(),
}));

vi.mock('../../../contexts/AddonsContext', () => ({
  useAddonMounts: () => mocks.addonMounts,
}));

// Stands in for a declarative addon panel: like the real AddonFormPanel, it
// is a <form> of its own with its own submit button.
vi.mock('../../addons/AddonPanel', () => ({
  default: () => (
    <form data-testid="addon-form" onSubmit={(e) => { e.preventDefault(); mocks.addonPanelSubmit(); }}>
      <button type="submit">Save</button>
    </form>
  ),
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
  getInstanceAdmins: mocks.getInstanceAdmins,
  getInstanceById: mocks.getInstanceById,
  getInstanceConfig: mocks.getInstanceConfig,
  getPresetById: mocks.getPresetById,
  getPresets: mocks.getPresets,
  previewPresetApply: mocks.previewPresetApply,
  getDeferRestartsSetting: mocks.getDeferRestartsSetting,
  updateInstance: mocks.updateInstance,
  updateInstanceConfig: mocks.updateInstanceConfig,
  updatePreset: mocks.updatePreset,
  checkPluginUpdates: vi.fn().mockRejectedValue(new Error('offline')),
  applyPluginUpdates: vi.fn(),
}));

vi.mock('../../../services/draftApi', () => ({
  discardDraft: mocks.discardDraft,
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

vi.mock('../../operators/OwnerAdminEditor', () => ({
  // Renders what it is given (so preset seeding is observable) and exposes a
  // button (so the save payload can be asserted) -- a plain `() => null` mock
  // would hide the render-loop bug this component had in an earlier task.
  default: ({ adminEntries, onAdminEntriesChange, onAdminEntriesLoaded }) => (
    <div>
      <button
        type="button"
        onClick={() => onAdminEntriesLoaded([
          { steam_id64: '76561198012345678', level: 3 },
          { steam_id64: '76561198087654321', level: 5 },
        ])}
      >
        load-server-admins
      </button>
      {(adminEntries || []).map((entry) => (
        <span key={entry.steam_id64}>{`seeded:${entry.steam_id64}:${entry.level}`}</span>
      ))}
      <button
        type="button"
        onClick={() => onAdminEntriesChange([{ steam_id64: '76561198012345678', level: 2 }])}
      >
        set-admins
      </button>
    </div>
  ),
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
  PluginCvarsModal: () => null,
  useUploadBusy: () => ({ uploading: false, track: () => () => {} }),
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
  useDraftAdapter: ({ existingDraftId, active } = {}) => {
    mocks.draftAdapterExistingDraftIds.push(existingDraftId);
    if (active) mocks.draftAdapterActiveDraftIds.push(existingDraftId);
    const workspace = mocks.useDraftWorkspace();
    return {
      ...workspace,
      draftId: existingDraftId || workspace.draftId,
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
  setCvarCatalog: vi.fn(),
  registerPluginCvarProvider: vi.fn(() => vi.fn()),
  getCvarCatalog: vi.fn(() => ({ cvars: [], commands: [], gametypes: [], sources: {} })),
}));

vi.mock('../../../codemirror-lang-qlfactories', () => ({
  qlFactoriesLanguage: {},
  qlFactoriesLinterSource: vi.fn(() => vi.fn()),
  qlFactoriesCompletion: [],
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

const DEFAULT_TARGET_CONFIGS = {
  'server.cfg': 'set sv_hostname "Test123"',
  'mappool.txt': '',
  'access.txt': '',
  'workshop.txt': '',
};

// What POST /instances/<id>/preset-preview returns for preset 99, named `name`
// in the presets list. `target` fields override the defaults.
const mockPresetPreview = (name, target = {}, extra = {}) => {
  mocks.getPresets.mockResolvedValue([{ id: 99, name }]);
  return {
    compatibility: null,
    needs_decision: false,
    keep_cvars: [],
    kept_cvars: [],
    diff: {},
    preview_hash: 'hash',
    ...extra,
    target: {
      hostname: 'Test123',
      configs: { ...DEFAULT_TARGET_CONFIGS },
      config_folders: [],
      factories: {},
      draft_id: 'preset-draft-1',
      ...target,
    },
  };
};

const PREVIEW_BODY = { preset_id: 99, keep_draft: true };

describe('EditInstanceConfigModal preset saving', () => {
  let EditInstanceConfigModal;

  beforeEach(async () => {
    vi.clearAllMocks();
    mocks.fileManagerProps = [];
    mocks.hooksTabProps = [];
    mocks.addonMounts = [];
    mocks.draftAdapterExistingDraftIds = [];
    mocks.draftAdapterActiveDraftIds = [];
    if (!EditInstanceConfigModal) {
      ({ default: EditInstanceConfigModal } = await import('../EditInstanceConfigModal'));
    }
    mocks.createPreset.mockResolvedValue({ message: 'saved', data: { id: 42, name: 'saved-from-edit' } });
    mocks.downloadPreset.mockResolvedValue(new Blob(['zip-bytes'], { type: 'application/zip' }));
    mocks.flushEdits.mockResolvedValue(undefined);
    mocks.getInstanceAdmins.mockResolvedValue({ admins: [], error: null });
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
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('my-preset'));
    mocks.discardDraft.mockResolvedValue(undefined);
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: false });
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

  it('folds a loaded preset\'s plugin dependency in from the draft tree', async () => {
    // The server's checked_plugins are qlx_plugins names, dependencies left
    // out; resolving them against the preset draft's tree still enables the
    // iouonegirl.py that mybalance.py declares.
    // The draft tree is empty on the first render and arrives after it, which
    // is what the real workspace does.
    mocks.useDraftWorkspace.mockReturnValueOnce({ ...baseDraftWorkspace, tree: [] });
    mocks.useDraftWorkspace.mockReturnValue({
      ...baseDraftWorkspace,
      tree: [
        {
          type: 'file', name: 'mybalance.py', path: 'mybalance.py',
          plugin_manifest: { depends_on: ['iouonegirl.py'] },
        },
        { type: 'file', name: 'iouonegirl.py', path: 'iouonegirl.py' },
      ],
    });
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('dep-preset', {
      checked_plugins: ['mybalance'],
    }));

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
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "dep-preset" loaded successfully.'));

    fireEvent.click(await screen.findByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    expect(mocks.createPreset.mock.calls[0][0].checked_plugins.sort())
      .toEqual(['iouonegirl.py', 'mybalance.py']);
  });

  it('keeps the instance hostname when a preset is loaded', async () => {
    // The server has already put the instance's hostname into the preset's cfg.
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('named-preset', {
      configs: { ...DEFAULT_TARGET_CONFIGS, 'server.cfg': 'set sv_hostname "Test123"\nset g_motd "from preset"' },
    }));

    render(
      <EditInstanceConfigModal isOpen={true} onClose={vi.fn()} instanceId={1} instanceName="Test123" onConfigSaved={vi.fn()} />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "named-preset" loaded successfully.'));

    expect(screen.getByLabelText(/server hostname/i)).toHaveValue('Test123');

    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    const payload = mocks.updateInstanceConfig.mock.calls[0][1];
    expect(payload.hostname).toBe('Test123');
    expect(payload.configs['server.cfg']).toBe('set sv_hostname "Test123"\nset g_motd "from preset"');
  });

  it('loads a preset through the server preview and keeps the server\'s hostname', async () => {
    // The instance record's hostname wins over the cfg text the modal opened
    // with, and every per-server cvar the server kept (sv_tags here) stays.
    const serverCfg = 'set sv_hostname "Record Name"\nset sv_tags "own,tags"\nset g_motd "from preset"';
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('server-preset', {
      hostname: 'Record Name',
      configs: { ...DEFAULT_TARGET_CONFIGS, 'server.cfg': serverCfg, 'custom.cfg': 'set g_custom "1"' },
      config_folders: ['maps'],
      factories: { 'ca.factories': 'factory' },
      draft_id: 'server-draft-7',
    }, { kept_cvars: ['sv_tags'] }));

    render(
      <EditInstanceConfigModal isOpen={true} onClose={vi.fn()} instanceId={1} instanceName="Test123" onConfigSaved={vi.fn()} />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "server-preset" loaded successfully.'));

    expect(mocks.previewPresetApply).toHaveBeenCalledTimes(1);
    expect(mocks.previewPresetApply).toHaveBeenCalledWith(1, PREVIEW_BODY);
    expect(mocks.getPresetById).not.toHaveBeenCalled();
    expect(mocks.getFactoryTree).toHaveBeenLastCalledWith({ preset: 'server-preset' });
    expect(mocks.draftAdapterExistingDraftIds.at(-1)).toBe('server-draft-7');
    expect(screen.getByLabelText(/server hostname/i)).toHaveValue('Record Name');

    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    const payload = mocks.updateInstanceConfig.mock.calls[0][1];
    expect(payload.hostname).toBe('Record Name');
    expect(payload.configs).toEqual({ ...DEFAULT_TARGET_CONFIGS, 'server.cfg': serverCfg, 'custom.cfg': 'set g_custom "1"' });
    expect(payload.config_folders).toEqual(['maps']);
    expect(payload.factories).toEqual({ 'ca.factories': 'factory' });
    expect(payload.draft_id).toBe('server-draft-7');
  });

  it('keeps the instance\'s checked plugins when the preset records no selection', async () => {
    // A legacy preset (checked_plugins null): the server leaves qlx_plugins
    // and scripts/ alone and sends neither the field nor a draft, so the modal
    // keeps what was ticked and its own instance draft.
    mocks.useDraftWorkspace.mockReturnValue({
      ...baseDraftWorkspace,
      tree: [{ type: 'file', name: 'balance.py', path: 'balance.py' }],
    });
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('legacy-preset', { draft_id: undefined }));

    render(
      <EditInstanceConfigModal isOpen={true} onClose={vi.fn()} instanceId={1} instanceName="Test123" onConfigSaved={vi.fn()} />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "legacy-preset" loaded successfully.'));

    expect(mocks.draftAdapterActiveDraftIds.at(-1)).toBeUndefined();
    expect(mocks.discardDraft).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    expect(mocks.updateInstanceConfig.mock.calls[0][1].checked_plugins).toEqual(['balance']);
    expect(mocks.updateInstanceConfig.mock.calls[0][1].draft_id).toBe('draft-123');
  });

  it('keeps the instance\'s plugins when a legacy preset is loaded before the plugin tree arrives', async () => {
    // The instance's qlx_plugins are only ticked once a tree is in; a legacy
    // load before that must not cancel that sync, or Save sends [].
    let treeReady = false;
    mocks.useDraftWorkspace.mockImplementation(() => ({
      ...baseDraftWorkspace,
      tree: treeReady ? [{ type: 'file', name: 'balance.py', path: 'balance.py' }] : [],
    }));
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('legacy-preset', { draft_id: undefined }));

    render(
      <EditInstanceConfigModal isOpen={true} onClose={vi.fn()} instanceId={1} instanceName="Test123" onConfigSaved={vi.fn()} />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "legacy-preset" loaded successfully.'));

    // The instance draft's tree arrives now; any render picks it up.
    treeReady = true;
    fireEvent.click(screen.getByRole('button', { name: /plugins/i }));
    await waitFor(() => {
      const props = mocks.fileManagerProps.filter(p => p.binaryContext?.contextType === 'instance').at(-1);
      expect([...(props?.checkedFiles ?? [])]).toEqual(['balance.py']);
    });

    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    expect(mocks.updateInstanceConfig.mock.calls[0][1].checked_plugins).toEqual(['balance']);
  });

  it('keeps a hostname typed before the preset load in the field and in server.cfg', async () => {
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('named-preset', {
      configs: { ...DEFAULT_TARGET_CONFIGS, 'server.cfg': 'set sv_hostname "Test123"\nset g_motd "from preset"' },
    }));

    render(
      <EditInstanceConfigModal isOpen={true} onClose={vi.fn()} instanceId={1} instanceName="Test123" onConfigSaved={vi.fn()} />
    );

    const hostnameField = await screen.findByLabelText(/server hostname/i);
    fireEvent.change(hostnameField, { target: { value: 'Edited Name' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "named-preset" loaded successfully.'));

    expect(screen.getByLabelText(/server hostname/i)).toHaveValue('Edited Name');
    fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
    await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
    const payload = mocks.updateInstanceConfig.mock.calls[0][1];
    expect(payload.hostname).toBe('Edited Name');
    expect(payload.configs['server.cfg']).toBe('set sv_hostname "Edited Name"\nset g_motd "from preset"');
  });

  it('does not adopt a loaded preset\'s draft again after the modal is closed and reopened', async () => {
    const props = { onClose: vi.fn(), instanceId: 1, instanceName: 'Test123', onConfigSaved: vi.fn() };
    const { rerender } = render(<EditInstanceConfigModal isOpen={true} {...props} />);

    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
    await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "my-preset" loaded successfully.'));
    expect(mocks.draftAdapterActiveDraftIds.at(-1)).toBe('preset-draft-1');

    rerender(<EditInstanceConfigModal isOpen={false} {...props} />);
    const seenBeforeReopen = mocks.draftAdapterActiveDraftIds.length;
    rerender(<EditInstanceConfigModal isOpen={true} {...props} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());

    expect(mocks.draftAdapterActiveDraftIds.slice(seenBeforeReopen)).not.toContain('preset-draft-1');
  });

  it('shows the modal while the admin read is still running and the preset waits for it', async () => {
    let finishAdmins;
    mocks.getInstanceAdmins.mockReturnValue(new Promise((resolve) => { finishAdmins = resolve; }));
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host', host_os_type: 'debian', status: 'running', name: 'inst', qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal isOpen={true} onClose={vi.fn()} instanceId={1} instanceName="Test123" onConfigSaved={vi.fn()} />
    );

    // Started on open, and the spinner does not wait for it.
    expect(mocks.getInstanceAdmins).toHaveBeenCalledWith(1);
    await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));
    expect(mocks.createPreset).not.toHaveBeenCalled();

    finishAdmins({ admins: [{ steam_id64: '76561198012345678', level: 4 }], error: null });
    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    expect(mocks.createPreset.mock.calls[0][0].admins).toEqual([{ steam_id64: '76561198012345678', level: 4 }]);
    expect(mocks.getInstanceAdmins).toHaveBeenCalledTimes(1);
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
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('lan-preset', { lan_rate_enabled: true }));

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

    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(1, PREVIEW_BODY));
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
    // The server clamps the preset's true to false for this host.
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('lan-preset', { lan_rate_enabled: false }));

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

    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(1, PREVIEW_BODY));

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
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('lan-preset', { lan_rate_enabled: true }));

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

    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(1, PREVIEW_BODY));
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
    // No recorded value: the server leaves lan_rate_enabled out of the target.
    mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('legacy-preset', { draft_id: undefined }));

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

    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(1, PREVIEW_BODY));
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

  it('an addon tab keeps its own form out of the config form and saves by itself', async () => {
    mocks.addonMounts = [{
      key: 'player-ranks:instance_tabs:ranks', label: 'Ranks', icon: 'gauge',
      addon: { id: 'player-ranks' }, entry: { id: 'ranks' }, panel: { kind: 'form' }, scope: 'instance',
    }];
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

    fireEvent.click(screen.getByRole('button', { name: /ranks/i }));

    const addonForm = await screen.findByTestId('addon-form');
    // Nested in the config form, the addon's Save button reloaded the page
    // instead of saving.
    expect(addonForm.parentElement.closest('form')).toBeNull();
    // The addon tab is no part of the instance config: no Save Configuration.
    expect(screen.queryByRole('button', { name: /save configuration/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(mocks.addonPanelSubmit).toHaveBeenCalledTimes(1);
    expect(mocks.updateInstanceConfig).not.toHaveBeenCalled();
  });

  it('pressing Enter in the hostname field still submits the config form', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );
    const hostname = await screen.findByLabelText(/server hostname/i);
    // The form is detached from the dialog body; the input joins it by id.
    expect(hostname.form).not.toBeNull();
    expect(hostname.form).toBe(screen.getByRole('button', { name: /save configuration/i }).form);
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

  it('starts with restart off when Settings > Defer restarts is on', async () => {
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: true });
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
    const toggle = screen.getByRole('button', { name: /toggle restart after save/i });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-pressed', 'false'));
    expect(toggle).not.toBeDisabled();

    // A change that needs a restart still forces it on.
    fireEvent.click(screen.getByText('Mock Toggle c.so'));
    await waitFor(() => expect(toggle).toHaveAttribute('aria-pressed', 'true'));
    expect(toggle).toBeDisabled();
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

    it('ticks the preset\'s plugins from the server\'s names and drops a subfolder-only one with the notice', async () => {
      mocks.getInstanceById.mockResolvedValue({
        host_name: 'test-host',
        lan_rate_enabled: false,
        status: 'running',
        name: 'inst',
        qlx_plugins: '',
      });
      // The server already dropped subfolder files and __init__.py; a name
      // that only matches a subfolder file of the draft tree is still dropped.
      mocks.useDraftWorkspace.mockReturnValue({
        ...baseDraftWorkspace,
        tree: [
          { type: 'file', name: 'balance.py', path: 'balance.py' },
          {
            type: 'folder',
            name: 'extras',
            path: 'extras',
            children: [{ type: 'file', name: 'textart.py', path: 'extras/textart.py' }],
          },
        ],
      });
      mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('my-preset', {
        checked_plugins: ['balance', 'textart'],
      }));

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

      await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(1, PREVIEW_BODY));

      fireEvent.click(screen.getByRole('button', { name: /plugins/i }));
      await waitFor(() => {
        expect([...(getPluginManagerProps()?.checkedFiles ?? [])]).toEqual(['balance.py']);
      });
      expect(screen.getByRole('status')).toHaveTextContent(
        "1 plugin that can't be enabled was deselected"
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

    it('previews the preset on the server and keeps its draft', async () => {
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(1, PREVIEW_BODY));
    });

    it('applies directly when the response carries no compatibility block', async () => {
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
      mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('my-preset', { draft_id: 'asked-draft' }, {
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [
            { path: 'essentials.py', verdict: 'incompatible', reasons: ['uses a minqlxtended-only API'], replacement: null },
          ],
          replacements: {},
        },
      }));
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await screen.findByText(/won.t carry over/i);
      expect(mocks.showSuccess).not.toHaveBeenCalled();
      // The draft of a preview that waits for the operator is not kept.
      expect(mocks.discardDraft).toHaveBeenCalledWith('asked-draft');
      expect(mocks.draftAdapterExistingDraftIds).not.toContain('asked-draft');
    });

    it('applies a cross-runtime preset silently when every plugin is compatible', async () => {
      // stripped: [] is a real response shape -- every plugin scanned clean --
      // and it must not surface a dialog with nothing in it.
      mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('my-preset', {}, {
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [],
          replacements: {},
          auto_accepted: ['balance.py'],
        },
      }));
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "my-preset" loaded successfully.'));
      expect(screen.queryByText(/won.t carry over/i)).not.toBeInTheDocument();
    });

    it('asks the compatibility question from the preview and re-previews with the accepted paths', async () => {
      const compatibility = {
        preset_runtime: 'minqlxtended',
        target_runtime: 'minqlx',
        stripped: [
          {
            path: 'essentials.py',
            verdict: 'incompatible',
            reasons: ['uses a minqlxtended-only API'],
            replacement: 'essentials_mqx.py',
            originally_checked: true,
          },
        ],
        replacements: { 'essentials.py': 'essentials_mqx.py' },
        auto_accepted: ['balance.py'],
      };
      mocks.useDraftWorkspace.mockReturnValue({
        ...baseDraftWorkspace,
        tree: [{ type: 'file', name: 'essentials.py', path: 'essentials.py' }],
      });
      mocks.previewPresetApply
        .mockResolvedValueOnce(mockPresetPreview('presetA', { draft_id: 'draft-asked' }, {
          compatibility, needs_decision: true,
        }))
        .mockResolvedValueOnce(mockPresetPreview('presetA', {
          draft_id: 'draft-accepted', checked_plugins: ['essentials'],
        }, { compatibility }));
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      await waitFor(() => expect(screen.getByRole('checkbox')).toBeChecked());
      // @headlessui/react is mocked to plain <div>s in this file, so the
      // dialog's own confirm button is the last "Load preset" one.
      const loadPresetButtons = screen.getAllByRole('button', { name: /load preset/i });
      fireEvent.click(loadPresetButtons[loadPresetButtons.length - 1]);

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "presetA" loaded successfully.'));
      // The ticked paths only: the server adds auto_accepted itself.
      expect(mocks.previewPresetApply).toHaveBeenNthCalledWith(2, 1, {
        ...PREVIEW_BODY, accepted_replacements: ['essentials.py'],
      });
      expect(mocks.discardDraft).toHaveBeenCalledWith('draft-asked');
      expect(mocks.draftAdapterExistingDraftIds.at(-1)).toBe('draft-accepted');

      fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
      await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalledTimes(1));
      const payload = mocks.updateInstanceConfig.mock.calls[0][1];
      expect(payload.draft_id).toBe('draft-accepted');
      expect(payload.checked_plugins).toEqual(['essentials']);
    });

    it('does not carry a confirmed preset\'s accepted replacements onto the next preset loaded', async () => {
      // Regression: a stale accepted filename from preset A must not ride
      // along into preset B's load. Only the compatibility dialog's confirm
      // handler sends accepted_replacements.
      mocks.previewPresetApply
        .mockResolvedValueOnce(mockPresetPreview('presetA', { draft_id: 'draft-a1' }, {
          compatibility: {
            preset_runtime: 'minqlxtended',
            target_runtime: 'minqlx',
            stripped: [
              {
                path: 'essentials.py',
                verdict: 'incompatible',
                reasons: ['uses a minqlxtended-only API'],
                replacement: 'essentials_mqx.py',
                originally_checked: true,
              },
            ],
            replacements: { 'essentials.py': 'essentials_mqx.py' },
          },
        }))
        .mockResolvedValueOnce(mockPresetPreview('presetA', { draft_id: 'draft-a2' }))
        .mockResolvedValueOnce(mockPresetPreview('presetA', { draft_id: 'draft-b' }));
      renderModal();

      // Load preset A and confirm the compatibility dialog, accepting the one
      // offered replacement (pre-checked by the dialog itself).
      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      // The dialog pre-checks the offered replacement via an effect that fires
      // after the title first paints, so wait for the checkbox itself to be
      // checked before confirming -- clicking on the title alone races that
      // effect and intermittently confirms with an empty accepted set.
      await waitFor(() => expect(screen.getByRole('checkbox')).toBeChecked());
      // @headlessui/react is mocked to plain <div>s in this file (no role="dialog"
      // to scope by), so disambiguate from the outer "Load Preset" trigger by DOM
      // order: PresetCompatibilityDialog's own confirm button renders last.
      const loadPresetButtons = screen.getAllByRole('button', { name: /load preset/i });
      fireEvent.click(loadPresetButtons[loadPresetButtons.length - 1]);

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "presetA" loaded successfully.'));
      expect(mocks.previewPresetApply).toHaveBeenNthCalledWith(2, 1, {
        ...PREVIEW_BODY, accepted_replacements: ['essentials.py'],
      });
      expect(mocks.draftAdapterExistingDraftIds.at(-1)).toBe('draft-a2');

      // Now load preset B, which needs no confirmation of its own.
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledTimes(3));
      expect(mocks.previewPresetApply).toHaveBeenNthCalledWith(3, 1, PREVIEW_BODY);
      await waitFor(() => expect(mocks.draftAdapterExistingDraftIds.at(-1)).toBe('draft-b'));
    });

    it('shows an error notification and closes the preset manager when the compatibility dialog is cancelled', async () => {
      mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('my-preset', {}, {
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [
            { path: 'essentials.py', verdict: 'incompatible', reasons: ['uses a minqlxtended-only API'], replacement: null },
          ],
          replacements: {},
        },
      }));
      renderModal();

      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);

      const cancelButtons = screen.getAllByRole('button', { name: /^cancel$/i });
      fireEvent.click(cancelButtons[cancelButtons.length - 1]);

      await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith(
        expect.stringMatching(/my-preset.*not applied/i)
      ));
      expect(screen.queryByTestId('preset-manager')).not.toBeInTheDocument();
    });

    it('leaves the active preset\'s accepted replacements intact when a subsequent load is cancelled', async () => {
      // Regression, round 2: cancelling the load of preset B must not touch
      // preset A's still-active draft, which holds the replacement the
      // operator accepted for A.
      mocks.previewPresetApply
        .mockResolvedValueOnce(mockPresetPreview('presetA', { draft_id: 'draft-a1' }, {
          compatibility: {
            preset_runtime: 'minqlxtended',
            target_runtime: 'minqlx',
            stripped: [
              {
                path: 'essentials.py',
                verdict: 'incompatible',
                reasons: ['uses a minqlxtended-only API'],
                replacement: 'essentials_mqx.py',
                originally_checked: true,
              },
            ],
            replacements: { 'essentials.py': 'essentials_mqx.py' },
          },
        }))
        .mockResolvedValueOnce(mockPresetPreview('presetA', { draft_id: 'draft-a2' }))
        .mockResolvedValueOnce(mockPresetPreview('presetA', { draft_id: 'draft-b' }, {
          compatibility: {
            preset_runtime: 'minqlxtended',
            target_runtime: 'minqlx',
            stripped: [
              { path: 'other.py', verdict: 'incompatible', reasons: ['unrelated'], replacement: null },
            ],
            replacements: {},
          },
        }));
      renderModal();

      // Load preset A and confirm, accepting the offered replacement.
      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      // The dialog pre-checks the offered replacement via an effect that fires
      // after the title first paints, so wait for the checkbox itself to be
      // checked before confirming -- clicking on the title alone races that
      // effect and intermittently confirms with an empty accepted set.
      await waitFor(() => expect(screen.getByRole('checkbox')).toBeChecked());
      let loadPresetButtons = screen.getAllByRole('button', { name: /load preset/i });
      fireEvent.click(loadPresetButtons[loadPresetButtons.length - 1]);

      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "presetA" loaded successfully.'));
      expect(mocks.draftAdapterExistingDraftIds.at(-1)).toBe('draft-a2');

      // Start loading preset B, then cancel out of its compatibility dialog.
      // @headlessui/react is mocked to plain <div>s in this file, so
      // disambiguate the dialog's own Cancel button from the modal's own
      // Cancel button (present since renderModal opens the edit modal) by DOM
      // order: PresetCompatibilityDialog's button renders last.
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      const cancelButtons = screen.getAllByRole('button', { name: /^cancel$/i });
      fireEvent.click(cancelButtons[cancelButtons.length - 1]);

      await waitFor(() => expect(screen.queryByText(/won.t carry over/i)).not.toBeInTheDocument());

      // Preset A's draft is still the active one; only B's preview draft went.
      expect(mocks.draftAdapterExistingDraftIds.at(-1)).toBe('draft-a2');
      expect(mocks.discardDraft).toHaveBeenCalledWith('draft-b');
      expect(mocks.discardDraft).not.toHaveBeenCalledWith('draft-a2');
    });
  });

  describe('admin list wiring', () => {
    const renderModal = (props = {}) => render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={mocks.onClose}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
        initialTab="admins"
        {...props}
      />
    );

    beforeEach(() => {
      mocks.onClose = vi.fn();
    });

    it('sends only the admin changes against the server list with the config save', async () => {
      renderModal();
      fireEvent.click(await screen.findByRole('button', { name: 'load-server-admins' }));
      // Server had A=3, B=5; the edit leaves only A=2.
      fireEvent.click(screen.getByRole('button', { name: 'set-admins' }));
      fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
      await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalled());
      const payload = mocks.updateInstanceConfig.mock.calls[0][1];
      expect(payload.admin_changes).toEqual([
        { steam_id64: '76561198012345678', level: 2 },
        { steam_id64: '76561198087654321', level: 0 },
      ]);
      expect(payload).not.toHaveProperty('admins');
    });

    it('sends no admin changes from a save that never touched the tab', async () => {
      renderModal();
      fireEvent.click(await screen.findByRole('button', { name: 'load-server-admins' }));
      fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
      await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalled());
      expect(mocks.updateInstanceConfig.mock.calls[0][1]).not.toHaveProperty('admin_changes');
    });

    it('saves a preset without admins and warns when the server could not be read', async () => {
      mocks.getInstanceAdmins.mockResolvedValue({ admins: null, error: 'unreachable' });
      renderModal();
      await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));
      await waitFor(() => expect(mocks.createPreset).toHaveBeenCalled());
      expect(mocks.createPreset.mock.calls[0][0].admins).toBeNull();
      await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith(expect.stringMatching(/without admins/i)));
    });

    it('opening the modal does not make it dirty', async () => {
      renderModal();
      await waitFor(() => expect(screen.getByRole('button', { name: /^cancel$/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
      // Not dirty -> handleAttemptClose calls onClose directly rather than
      // opening the discard-changes confirmation.
      expect(mocks.onClose).toHaveBeenCalled();
    });

    it('seeds the admin list from an applied preset and sends it back on save-as-preset', async () => {
      // The server list is empty, so the preview's changes are the preset's list.
      mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('admins-preset', {
        admin_changes: [{ steam_id64: '76561198087654321', level: 4 }],
      }));
      renderModal();
      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await waitFor(() => expect(screen.getByText('seeded:76561198087654321:4')).toBeInTheDocument());

      fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));
      await waitFor(() => expect(mocks.createPreset).toHaveBeenCalled());
      expect(mocks.createPreset.mock.calls[0][0].admins)
        .toEqual([{ steam_id64: '76561198087654321', level: 4 }]);
    });

    it('applies the preview\'s admin changes to the server list so Save sends them back', async () => {
      // Server: A=3, B=5. Preset: A=2, C=1. The server's diff re-levels A,
      // adds C and revokes B; Save must send exactly that.
      const adminChanges = [
        { steam_id64: '76561198012345678', level: 2 },
        { steam_id64: '76561198000000001', level: 1 },
        { steam_id64: '76561198087654321', level: 0 },
      ];
      mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('admins-preset', { admin_changes: adminChanges }));
      renderModal();
      fireEvent.click(await screen.findByRole('button', { name: 'load-server-admins' }));
      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await waitFor(() => expect(screen.getByText('seeded:76561198000000001:1')).toBeInTheDocument());
      expect(screen.getByText('seeded:76561198012345678:2')).toBeInTheDocument();
      expect(screen.queryByText(/seeded:76561198087654321/)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
      await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalled());
      expect(mocks.updateInstanceConfig.mock.calls[0][1].admin_changes).toEqual(adminChanges);
    });

    it('a preset with no admin list leaves the current one alone', async () => {
      mocks.previewPresetApply.mockResolvedValue(mockPresetPreview('legacy-preset', { draft_id: undefined }));
      renderModal();
      await screen.findByRole('button', { name: 'set-admins' });
      fireEvent.click(screen.getByRole('button', { name: 'set-admins' }));
      await waitFor(() => expect(screen.getByRole('button', { name: /load preset/i })).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await waitFor(() => expect(mocks.showSuccess).toHaveBeenCalledWith('Preset "legacy-preset" loaded successfully.'));

      fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
      await waitFor(() => expect(mocks.updateInstanceConfig).toHaveBeenCalled());
      expect(mocks.updateInstanceConfig.mock.calls[0][1].admin_changes)
        .toEqual([{ steam_id64: '76561198012345678', level: 2 }]);
    });
  });
});
