import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  consumeDraft: vi.fn(),
  discardDraft: vi.fn(),
  getAvailablePortsForHost: vi.fn(),
  getBinaryMeta: vi.fn(),
  getFactoryContent: vi.fn(),
  getFactoryTree: vi.fn(),
  getPresetById: vi.fn(),
  getPresets: vi.fn(),
  fileManagerProps: [],
  // Preset names the plugin draft adapter was opened against, newest last.
  draftAdapterPresets: [],
  // Last acceptedReplacements the plugin draft adapter saw for each preset name --
  // proves whether a stale accepted list from a previous preset leaked onto this one.
  draftAdapterAcceptedReplacementsByPreset: {},
  qlentLanguage: { name: 'qlent' },
  qlentLinter: vi.fn(),
  savePreset: vi.fn(),
  saveBinaryMeta: vi.fn(),
  updatePreset: vi.fn(),
  useDraftWorkspace: vi.fn(),
  uploadDraftHook: vi.fn(),
  deleteDraftHook: vi.fn(),
}));

vi.mock('../../../hooks/useDraftWorkspace', () => ({
  useDraftWorkspace: mocks.useDraftWorkspace,
}));

vi.mock('../../../services/api', () => ({
  getAvailablePortsForHost: mocks.getAvailablePortsForHost,
  getFactoryContent: mocks.getFactoryContent,
  getFactoryTree: mocks.getFactoryTree,
  getPresetById: mocks.getPresetById,
  getPresets: mocks.getPresets,
  savePreset: mocks.savePreset,
  updatePreset: mocks.updatePreset,
}));

vi.mock('../../../services/draftApi', () => ({
  getBinaryMeta: mocks.getBinaryMeta,
  saveBinaryMeta: mocks.saveBinaryMeta,
  uploadDraftHook: mocks.uploadDraftHook,
  deleteDraftHook: mocks.deleteDraftHook,
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
    React.useImperativeHandle(ref, () => ({
      flushEdits: vi.fn().mockResolvedValue(undefined),
    }));
    const [newFolderStep, setNewFolderStep] = React.useState(null); // { parent, opening: bool }
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
    if (mocks.draftAdapterPresets[mocks.draftAdapterPresets.length - 1] !== preset) {
      mocks.draftAdapterPresets.push(preset);
    }
    if (preset) {
      mocks.draftAdapterAcceptedReplacementsByPreset[preset] = acceptedReplacements || [];
    }
    return {
    draftId: 'draft-123',
    tree: [],
    loading: false,
    error: null,
    refreshTree: vi.fn(),
    readContent: vi.fn(),
    writeContent: vi.fn(),
    upload: vi.fn(),
    deleteFile: vi.fn(),
    renameFile: vi.fn(),
    commit: vi.fn(),
    discard: mocks.discardDraft,
    consume: mocks.consumeDraft,
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
    const readContent = React.useCallback(async (path) => files[path] || '', [files]);
    const writeContent = React.useCallback(async (path, content) => {
      setFiles(prev => ({ ...prev, [path]: content || '' }));
    }, []);
    return React.useMemo(() => ({
      tree: serverTree,
      folders,
      createFolder,
      readContent,
      writeContent,
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
    }), [files, folders, createFolder, readContent, reset, serverTree, writeContent]);
  },
}));

vi.mock('../InstanceBasicInfoForm', () => ({
  default: ({
    onHostChange,
    onPortChange,
    onRedisDbChange,
    port,
    redisDb,
    selectedHostId,
  }) => (
    <div>
      <div>basic-info</div>
      <div data-testid="selected-host">{selectedHostId || 'none'}</div>
      <div data-testid="port">{port || 'none'}</div>
      <div data-testid="redis-db">{redisDb ?? 'none'}</div>
      <button type="button" onClick={() => onHostChange('1')}>Select Host 1</button>
      <button type="button" onClick={() => onHostChange('2')}>Select Host 2</button>
      <button type="button" onClick={() => onPortChange('27963')}>Set Port 27963</button>
      <button type="button" onClick={() => onPortChange('27965')}>Set Port 27965</button>
      <button type="button" onClick={() => onRedisDbChange(1)}>Pick Redis DB 1</button>
      <button type="button" onClick={() => onRedisDbChange(7)}>Pick Redis DB 7</button>
    </div>
  ),
}));

vi.mock('../InstanceOptionsRow', () => ({
  default: ({
    autoGeneratePasswords,
    lanRateDisabled,
    lanRateEnabled,
    lanRateUnavailableReason,
    onAutoGeneratePasswordsChange,
    onLanRateChange,
    onZmqRconPasswordChange,
    onZmqStatsPasswordChange,
    passwordErrors,
    zmqRconPassword,
    zmqStatsPassword,
  }) => (
    <div>
      <div data-testid="lan-rate-enabled">{String(lanRateEnabled)}</div>
      <div data-testid="lan-rate-disabled">{String(lanRateDisabled)}</div>
      <div data-testid="lan-rate-reason">{lanRateUnavailableReason || ''}</div>
      <div data-testid="auto-generate-passwords">{String(autoGeneratePasswords)}</div>
      <div data-testid="stats-password">{zmqStatsPassword}</div>
      <div data-testid="rcon-password">{zmqRconPassword}</div>
      <div data-testid="password-errors">{JSON.stringify(passwordErrors || {})}</div>
      <button type="button" onClick={() => onLanRateChange(!lanRateEnabled)}>Toggle 99k</button>
      <button type="button" onClick={() => onAutoGeneratePasswordsChange(!autoGeneratePasswords)}>Toggle Auto Passwords</button>
      <button type="button" onClick={() => onZmqStatsPasswordChange('Kp3-xR_9vT=2wQ')}>Set Valid Stats Password</button>
      <button type="button" onClick={() => onZmqRconPasswordChange('aB7_zQ2-mN4kLp')}>Set Valid Rcon Password</button>
      <button type="button" onClick={() => onZmqStatsPasswordChange('bad pass!')}>Set Invalid Stats Password</button>
    </div>
  ),
}));

vi.mock('../../presetManager/PresetManagerModal', () => ({
  default: ({ isOpen, initialTab, initialOverwriteName, onSavePreset, onLoadPreset }) => (
    isOpen ? (
      <div data-testid="preset-manager" data-tab={initialTab} data-overwrite={initialOverwriteName || ''}>
        preset-manager
        <button
          type="button"
          onClick={() => onSavePreset({ name: 'saved-preset', description: 'copy' })}
        >
          Confirm Save Preset
        </button>
        <button
          type="button"
          onClick={() => onLoadPreset(1)}
        >
          Confirm Load Preset
        </button>
      </div>
    ) : null
  ),
}));
vi.mock('../../config/FullScreenConfigEditorModal', () => ({ default: () => null }));

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

describe('AddInstanceForm draft lifecycle', () => {
  let AddInstanceForm;

  beforeEach(async () => {
    vi.clearAllMocks();
    mocks.fileManagerProps = [];
    mocks.draftAdapterPresets = [];
    mocks.draftAdapterAcceptedReplacementsByPreset = {};
    if (!AddInstanceForm) {
      ({ default: AddInstanceForm } = await import('../AddInstanceForm'));
    }
    mocks.getAvailablePortsForHost.mockResolvedValue({ available_ports: [] });
    mocks.getBinaryMeta.mockResolvedValue({});
    mocks.getFactoryContent.mockResolvedValue({ content: '' });
    mocks.getFactoryTree.mockResolvedValue([]);
    mocks.getPresetById.mockResolvedValue({});
    mocks.getPresets.mockResolvedValue([]);
    mocks.savePreset.mockResolvedValue({ message: 'saved' });
    mocks.saveBinaryMeta.mockResolvedValue({});
    mocks.updatePreset.mockResolvedValue({ message: 'updated' });
    mocks.uploadDraftHook.mockResolvedValue({});
    mocks.deleteDraftHook.mockResolvedValue({});
    mocks.useDraftWorkspace.mockReturnValue({
      draftId: 'draft-123',
      tree: [],
      loading: false,
      error: null,
      refreshTree: vi.fn(),
      readContent: vi.fn(),
      writeContent: vi.fn(),
      upload: vi.fn(),
      deleteFile: vi.fn(),
      commit: vi.fn(),
      discard: mocks.discardDraft,
      consume: mocks.consumeDraft,
    });
  });

  it('passes consumeDraft to the submit handler so the parent can consume the draft on success', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={null}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        draft_id: 'draft-123',
      }),
      { consumeDraft: mocks.consumeDraft }
    );
  });

  it('disables 99k lan rate for ubuntu hosts', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [
            { id: 1, name: 'deb-host', os_type: 'debian' },
            { id: 2, name: 'ubu-host', os_type: 'ubuntu' },
          ],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={2}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));
    expect(screen.getByTestId('lan-rate-disabled')).toHaveTextContent('true');
    expect(screen.getByTestId('lan-rate-reason')).toHaveTextContent(/99k LAN Rate currently requires Debian/);
  });

  it('resets lan rate when switching from debian to ubuntu', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [
            { id: 1, name: 'deb-host', os_type: 'debian' },
            { id: 2, name: 'ubu-host', os_type: 'ubuntu' },
          ],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={1}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
    fireEvent.click(screen.getByRole('button', { name: /toggle 99k/i }));
    expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('true');

    fireEvent.click(screen.getByRole('button', { name: /select host 2/i }));

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));
    await waitFor(() => expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('false'));
    expect(screen.getByTestId('lan-rate-disabled')).toHaveTextContent('true');
  });

  it('enables 99k lan rate for migrated ubuntu hosts (lan_rate_uses_hook: true)', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [
            { id: 3, name: 'ubu-migrated', os_type: 'ubuntu', lan_rate_uses_hook: true },
          ],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={3}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('3'));
    expect(screen.getByTestId('lan-rate-disabled')).toHaveTextContent('false');
    expect(screen.getByTestId('lan-rate-reason')).toHaveTextContent('');
  });

  it('includes lan_rate_enabled when saving a preset', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [{ id: 1, name: 'deb-host', os_type: 'debian' }],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={1}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
    fireEvent.click(screen.getByRole('button', { name: /toggle 99k/i }));
    expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('true');

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.savePreset).toHaveBeenCalledTimes(1));
    expect(mocks.savePreset).toHaveBeenCalledWith(
      expect.objectContaining({ lan_rate_enabled: true })
    );
  });

  it('includes lan_rate_enabled: false when saving a preset with the toggle off', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [{ id: 1, name: 'deb-host', os_type: 'debian' }],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={1}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
    expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('false');

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.savePreset).toHaveBeenCalledTimes(1));
    expect(mocks.savePreset).toHaveBeenCalledWith(
      expect.objectContaining({ lan_rate_enabled: false })
    );
  });

  it('applies lan_rate_enabled from a loaded preset', async () => {
    mocks.getPresetById.mockResolvedValue({
      name: 'lan-preset',
      configs: {},
      factories: {},
      lan_rate_enabled: true,
    });

    render(
      <AddInstanceForm
        initialData={{
          hosts: [{ id: 1, name: 'deb-host', os_type: 'debian' }],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={1}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
    expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('false');

    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith(1, { targetRuntime: null }));
    await waitFor(() => expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('true'));
  });

  it('does not enable lan rate from a preset on an unsupported host', async () => {
    mocks.getPresetById.mockResolvedValue({
      name: 'lan-preset',
      configs: {},
      factories: {},
      lan_rate_enabled: true,
    });

    render(
      <AddInstanceForm
        initialData={{
          hosts: [{ id: 2, name: 'ubu-host', os_type: 'ubuntu' }],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={2}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));

    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith(1, { targetRuntime: null }));
    await waitFor(() => expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('false'));
  });

  it('leaves the lan rate toggle untouched when the loaded preset has no recorded value', async () => {
    mocks.getPresetById.mockResolvedValue({
      name: 'legacy-preset',
      configs: {},
      factories: {},
      lan_rate_enabled: null,
    });

    render(
      <AddInstanceForm
        initialData={{
          hosts: [{ id: 1, name: 'deb-host', os_type: 'debian' }],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={1}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
    fireEvent.click(screen.getByRole('button', { name: /toggle 99k/i }));
    expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('true');

    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith(1, { targetRuntime: null }));
    expect(screen.getByTestId('lan-rate-enabled')).toHaveTextContent('true');
  });

  it('does not preselect default preset factories when adding an instance', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    mocks.getPresetById.mockResolvedValue({
      factories: {
        'ca.factories': '{"factory": true}',
      },
    });

    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [{ id: 1, name: 'default', is_builtin: true }],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={null}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toEqual(expect.objectContaining({
      factories: {},
    }));
    expect(mocks.getPresetById).not.toHaveBeenCalled();
  });

  it('saves factory adapter files as checked factory filenames', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
          defaultFactories: {
            'ca.factories': '{"factory": true}',
          },
        }}
        initialHostId={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.savePreset).toHaveBeenCalledTimes(1));
    expect(mocks.savePreset).toHaveBeenCalledWith(
      expect.objectContaining({
        config_folders: [],
        factories: { 'ca.factories': '{"factory": true}' },
        checked_factories: ['ca.factories'],
      }),
    );
  });

  it('creates a nested subfolder via the row menu and includes it in the submitted config_folders', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    mocks.getPresetById.mockResolvedValue({
      config_folders: ['existingFolder'],
    });

    render(
      <AddInstanceForm
        initialData={{
          hosts: [{ id: 1, name: 'deb-host', os_type: 'debian' }],
          presets: [{ id: 1, name: 'my-preset', is_builtin: false }],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={1}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

    await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith(1, { targetRuntime: null }));
    await waitFor(() => expect(screen.getByRole('button', { name: /folder actions for existingFolder/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /folder actions for existingFolder/i }));
    fireEvent.click(screen.getByRole('button', { name: /new folder/i }));
    fireEvent.change(screen.getByLabelText(/folder name/i), { target: { value: 'newSubfolder' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].config_folders).toContain('existingFolder/newSubfolder');
  });

  it('uses ql cfg highlighting and linting for any .cfg config file', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(mocks.fileManagerProps.length).toBeGreaterThan(0));
    const configManagerProps = mocks.fileManagerProps.find(props => props.defaultSelectedPath === 'server.cfg');

    expect(configManagerProps.getLanguageForFile('custom.cfg')).toEqual({});
    expect(configManagerProps.getLinterSourceForFile('custom.cfg')).toEqual(expect.any(Function));
  });

  it('uses entity highlighting and linting for .ent config files', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
            'custom_entities/items.ent': '{\n"classname" "worldspawn"\n}',
          },
        }}
        initialHostId={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    await waitFor(() => expect(mocks.fileManagerProps.length).toBeGreaterThan(0));
    const configManagerProps = mocks.fileManagerProps.find(props => props.defaultSelectedPath === 'server.cfg');

    expect(configManagerProps.getLanguageForFile('custom_entities/items.ent')).toBe(mocks.qlentLanguage);
    expect(configManagerProps.getLinterSourceForFile('custom_entities/items.ent')).toBe(mocks.qlentLinter);
  });

  it('uses python highlighting for plugin .py files', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /plugins/i }));

    await waitFor(() => {
      expect(mocks.fileManagerProps.some(props => props.binaryContext?.contextType === 'preset')).toBe(true);
    });
    const pluginManagerProps = mocks.fileManagerProps.find(
      props => props.binaryContext?.contextType === 'preset',
    );

    expect(pluginManagerProps.getLanguageForFile('balance.py')).toBeTruthy();
    expect(pluginManagerProps.getLanguageForFile('notes.txt')).toBeNull();
    expect(pluginManagerProps.onExpandEditor).toEqual(expect.any(Function));
  });

  it('reflects preset hooks in the Hooks tab and submits enabled_hooks order', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
          defaultSeedsByRuntime: {
            minqlx: {
              checkedPlugins: [],
              availableHooks: [
                { filename: 'a.so', size: 1024, modified: 1, enabled: false, order: null, description: '' },
                { filename: 'b.so', size: 2048, modified: 1, enabled: false, order: null, description: '' },
              ],
              enabledHooks: ['a.so'],
            },
          },
        }}
        initialHostId={null}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^hooks$/i }));

    // Reflects the (default) preset config: a.so enabled, b.so disabled.
    expect(screen.getByRole('button', { name: /enable a.so/i })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /enable b.so/i })).toHaveAttribute('aria-pressed', 'false');
    // No instance yet, but the draft is ready -> upload affordance is available.
    expect(screen.getByRole('button', { name: /upload \.so/i })).toBeInTheDocument();

    // Enabling b.so appends it to the LD_PRELOAD order sent on create. Once the
    // toggle commits, b.so moves into the enabled (sortable) section and gains a
    // reorder handle — wait on that instead of an arbitrary sleep.
    fireEvent.click(screen.getByRole('button', { name: /enable b.so/i }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /reorder b.so/i })).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].enabled_hooks).toEqual(['a.so', 'b.so']);
  });

  it('uploads a user hook into the draft and shows it in the Hooks tab', async () => {
    mocks.uploadDraftHook.mockResolvedValue({
      filename: 'newhook.so', size: 128, modified: 1, enabled: false, order: null, description: '',
    });

    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^hooks$/i }));
    const uploadBtn = await screen.findByRole('button', { name: /upload \.so/i });
    expect(uploadBtn).toBeInTheDocument();

    const input = document.querySelector('[data-testid="hook-upload-input"]');
    const file = new File([new Uint8Array([0x7f, 0x45, 0x4c, 0x46])], 'newhook.so');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(mocks.uploadDraftHook).toHaveBeenCalledWith('draft-123', file));
    expect(await screen.findByText('newhook')).toBeInTheDocument();
  });

  it('uses JSON highlighting and linting for factory files', async () => {
    render(
      <AddInstanceForm
        initialData={{
          hosts: [],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

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
    expect(factoryManagerProps.getLanguageForFile('notes.txt')).toBeNull();
    expect(factoryManagerProps.getLinterSourceForFile('notes.txt')).toBeNull();
    expect(factoryManagerProps.onExpandEditor).toEqual(expect.any(Function));
  });

  describe('non-enableable plugins', () => {
    it('drops non-enableable entries from the runtime seed', async () => {
      render(
        <AddInstanceForm
          initialData={{
            hosts: [],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
            defaultSeedsByRuntime: {
              minqlx: {
                checkedPlugins: ['balance.py', 'extras/textart.py'],
                availableHooks: [],
                enabledHooks: [],
              },
            },
          }}
          initialHostId={null}
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      expect(await screen.findByRole('status')).toHaveTextContent(
        /1 plugin that can't be enabled was deselected/i
      );
    });

    it('drops non-enableable entries when loading a preset', async () => {
      mocks.getPresetById.mockResolvedValue({
        checked_plugins: ['balance.py', 'discord_extensions/admin.py', '__init__.py'],
      });

      render(
        <AddInstanceForm
          initialData={{
            hosts: [{ id: 1, name: 'deb-host', os_type: 'debian' }],
            presets: [{ id: 1, name: 'my-preset', is_builtin: false }],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={1}
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith(1, { targetRuntime: null }));
      expect(await screen.findByRole('status')).toHaveTextContent(
        /2 plugins that can't be enabled were deselected/i
      );
    });

    it('omits subfolder plugins from checked_plugins and qlx_plugins on submit', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);

      render(
        <AddInstanceForm
          initialData={{
            hosts: [],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
            defaultSeedsByRuntime: {
              minqlx: {
                checkedPlugins: ['balance.py', 'discord_extensions/admin.py'],
                availableHooks: [],
                enabledHooks: [],
              },
            },
          }}
          initialHostId={null}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      const submitData = onSubmit.mock.calls[0][0];
      expect(submitData.checked_plugins).toEqual(['balance']);
      expect(submitData.qlx_plugins).toBe('balance');
    });
  });

  describe('Redis DB is independent of port and host', () => {
    const renderWithTwoHosts = () => render(
      <AddInstanceForm
        initialData={{
          hosts: [
            { id: 1, name: 'host-one', os_type: 'debian', instances: [] },
            { id: 2, name: 'host-two', os_type: 'debian', instances: [] },
          ],
          presets: [],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    it('defaults to Redis DB 1 and leaves it untouched when the port changes', async () => {
      mocks.getAvailablePortsForHost.mockResolvedValue({ available_ports: [27963, 27965] });

      renderWithTwoHosts();

      fireEvent.click(screen.getByRole('button', { name: 'Select Host 1' }));
      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      expect(screen.getByTestId('redis-db')).toHaveTextContent('1');

      fireEvent.click(screen.getByRole('button', { name: 'Set Port 27963' }));
      await waitFor(() => expect(screen.getByTestId('port')).toHaveTextContent('27963'));
      expect(screen.getByTestId('redis-db')).toHaveTextContent('1');

      fireEvent.click(screen.getByRole('button', { name: 'Set Port 27965' }));
      await waitFor(() => expect(screen.getByTestId('port')).toHaveTextContent('27965'));
      expect(screen.getByTestId('redis-db')).toHaveTextContent('1');
    });

    it('keeps an explicitly picked Redis DB fixed across port changes', async () => {
      mocks.getAvailablePortsForHost.mockResolvedValue({ available_ports: [27963, 27965] });

      renderWithTwoHosts();

      fireEvent.click(screen.getByRole('button', { name: 'Select Host 1' }));
      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: 'Set Port 27963' }));
      await waitFor(() => expect(screen.getByTestId('port')).toHaveTextContent('27963'));

      fireEvent.click(screen.getByRole('button', { name: 'Pick Redis DB 7' }));
      await waitFor(() => expect(screen.getByTestId('redis-db')).toHaveTextContent('7'));

      fireEvent.click(screen.getByRole('button', { name: 'Set Port 27965' }));
      await waitFor(() => expect(screen.getByTestId('port')).toHaveTextContent('27965'));
      expect(screen.getByTestId('redis-db')).toHaveTextContent('7');
    });

    it('keeps an explicitly picked Redis DB fixed across a host switch, even when the port is dropped', async () => {
      mocks.getAvailablePortsForHost.mockImplementation((hostId) => Promise.resolve({
        available_ports: String(hostId) === '1' ? [27963] : [27962],
      }));

      renderWithTwoHosts();

      fireEvent.click(screen.getByRole('button', { name: 'Select Host 1' }));
      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: 'Set Port 27963' }));
      await waitFor(() => expect(screen.getByTestId('port')).toHaveTextContent('27963'));

      fireEvent.click(screen.getByRole('button', { name: 'Pick Redis DB 7' }));
      await waitFor(() => expect(screen.getByTestId('redis-db')).toHaveTextContent('7'));

      fireEvent.click(screen.getByRole('button', { name: 'Select Host 2' }));

      await waitFor(() => expect(screen.getByTestId('port')).toHaveTextContent('none'));
      expect(screen.getByTestId('redis-db')).toHaveTextContent('7');
    });
  });

  describe('Redis DB default on initial host load', () => {
    it('defaults to the next free Redis DB for the preselected host', async () => {
      mocks.getAvailablePortsForHost.mockResolvedValue({ available_ports: [27963] });

      render(
        <AddInstanceForm
          initialData={{
            hosts: [
              {
                id: 1,
                name: 'host-one',
                os_type: 'debian',
                instances: [
                  { name: 'Duel #1', port: 27960, redis_db: null },
                  { name: 'FFA', port: 27961, redis_db: null },
                ],
              },
            ],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={1}
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      expect(screen.getByTestId('redis-db')).toHaveTextContent('3');
    });

    it('falls back to DB 1 as the default when the host has no instances', async () => {
      mocks.getAvailablePortsForHost.mockResolvedValue({ available_ports: [27960] });

      render(
        <AddInstanceForm
          initialData={{
            hosts: [{ id: 1, name: 'host-one', os_type: 'debian', instances: [] }],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={1}
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      expect(screen.getByTestId('redis-db')).toHaveTextContent('1');
    });
  });

  describe('ZMQ password entry', () => {
    it('defaults to auto generate and omits both passwords from the payload', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      mocks.getAvailablePortsForHost.mockResolvedValue({ available_ports: [27963] });

      render(
        <AddInstanceForm
          initialData={{
            hosts: [{ id: 1, name: 'host-one', os_type: 'debian' }],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={null}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('auto-generate-passwords')).toHaveTextContent('true');

      fireEvent.click(screen.getByRole('button', { name: 'Select Host 1' }));
      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: 'Set Port 27963' }));
      await waitFor(() => expect(screen.getByTestId('port')).toHaveTextContent('27963'));

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      const submitted = onSubmit.mock.calls[0][0];
      expect(submitted).not.toHaveProperty('zmq_stats_password');
      expect(submitted).not.toHaveProperty('zmq_rcon_password');
    });

    it('includes both passwords in the payload when auto generate is off', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);

      render(
        <AddInstanceForm
          initialData={{
            hosts: [],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={null}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      fireEvent.click(screen.getByText('Toggle Auto Passwords'));
      fireEvent.click(screen.getByText('Set Valid Stats Password'));
      fireEvent.click(screen.getByText('Set Valid Rcon Password'));

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      const submitted = onSubmit.mock.calls[0][0];
      expect(submitted.zmq_stats_password).toBe('Kp3-xR_9vT=2wQ');
      expect(submitted.zmq_rcon_password).toBe('aB7_zQ2-mN4kLp');
    });

    it('blocks submit and surfaces an error when a manual password is invalid', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);

      render(
        <AddInstanceForm
          initialData={{
            hosts: [],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={null}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      fireEvent.click(screen.getByText('Toggle Auto Passwords'));
      fireEvent.click(screen.getByText('Set Invalid Stats Password'));
      fireEvent.click(screen.getByText('Set Valid Rcon Password'));

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

      expect(onSubmit).not.toHaveBeenCalled();
      await waitFor(() => {
        expect(screen.getAllByText(/may only contain/).length).toBeGreaterThan(0);
      });
      expect(screen.getByTestId('password-errors')).toHaveTextContent('may only contain');
    });

    it('blocks submit when auto generate is off and the fields are empty', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);

      render(
        <AddInstanceForm
          initialData={{
            hosts: [],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={null}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      fireEvent.click(screen.getByText('Toggle Auto Passwords'));

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

      expect(onSubmit).not.toHaveBeenCalled();
      await waitFor(() => {
        expect(screen.getAllByText(/is required when Auto Generate Passwords is off/).length).toBeGreaterThan(0);
      });
    });

    it('clears password errors when auto generate is switched back on', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);

      render(
        <AddInstanceForm
          initialData={{
            hosts: [],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={null}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      fireEvent.click(screen.getByText('Toggle Auto Passwords'));
      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

      await waitFor(() => {
        expect(screen.getByTestId('password-errors')).toHaveTextContent('is required');
      });

      // Re-enabling auto generate disables the inputs, so their errors must go
      // with them -- otherwise the red borders stick to fields nobody can edit.
      fireEvent.click(screen.getByText('Toggle Auto Passwords'));

      expect(screen.getByTestId('password-errors')).toHaveTextContent('{}');
    });

    it('does not send typed passwords after auto generate is switched back on', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);

      render(
        <AddInstanceForm
          initialData={{
            hosts: [],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={null}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      fireEvent.click(screen.getByText('Toggle Auto Passwords'));
      fireEvent.click(screen.getByText('Set Valid Stats Password'));
      fireEvent.click(screen.getByText('Set Valid Rcon Password'));
      fireEvent.click(screen.getByText('Toggle Auto Passwords'));

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));

      expect(screen.getByTestId('stats-password')).toHaveTextContent('Kp3-xR_9vT=2wQ');
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      const submitted = onSubmit.mock.calls[0][0];
      expect(submitted).not.toHaveProperty('zmq_stats_password');
    });

    it('does not write passwords into a saved preset', async () => {
      render(
        <AddInstanceForm
          initialData={{
            hosts: [{ id: 1, name: 'deb-host', os_type: 'debian' }],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
          }}
          initialHostId={1}
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));

      fireEvent.click(screen.getByText('Toggle Auto Passwords'));
      fireEvent.click(screen.getByText('Set Valid Stats Password'));

      fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

      await waitFor(() => expect(mocks.savePreset).toHaveBeenCalledTimes(1));
      const savedPreset = mocks.savePreset.mock.calls[0][0];
      expect(savedPreset).not.toHaveProperty('zmq_stats_password');
      expect(savedPreset).not.toHaveProperty('zmq_rcon_password');
      expect(savedPreset).not.toHaveProperty('auto_generate_passwords');
    });
  });

  describe('preset runtime compatibility', () => {
    const renderForm = (hosts, initialHostId) => render(
      <AddInstanceForm
        initialData={{
          hosts,
          presets: [{ id: 1, name: 'my-preset', is_builtin: false }],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={initialHostId}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    const loadThePreset = async () => {
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await waitFor(() => expect(screen.getByText('Editing preset:')).toBeInTheDocument());
    };

    it('cannot open the preset loader before a host is chosen', () => {
      // With no host there is no runtime to check a preset against, so the
      // gate has nothing to gate on -- the entry point closes instead.
      renderForm([{ id: 1, name: 'deb-host', runtime: 'minqlx' }], null);

      expect(screen.getByTestId('selected-host')).toHaveTextContent('none');
      expect(screen.getByRole('button', { name: /load preset/i })).toBeDisabled();
    });

    it('enables the preset loader once a host is chosen', async () => {
      renderForm([{ id: 1, name: 'deb-host', runtime: 'minqlx' }], 1);

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      expect(screen.getByRole('button', { name: /load preset/i })).toBeEnabled();
    });

    it('clears a loaded preset when the host switches to the other runtime', async () => {
      mocks.getPresetById.mockResolvedValue({ name: 'my-preset', runtime: 'minqlx' });
      renderForm(
        [
          { id: 1, name: 'deb-host', runtime: 'minqlx' },
          { id: 2, name: 'ubu-host', runtime: 'minqlxtended' },
        ],
        1,
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      await loadThePreset();

      fireEvent.click(screen.getByRole('button', { name: /select host 2/i }));

      await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/no longer matches this host and was cleared/i));
      expect(screen.queryByText('Editing preset:')).not.toBeInTheDocument();
    });

    it('keeps a loaded preset when the new host runs the same runtime', async () => {
      // The clear is destructive, so it must fire only on a genuine mismatch --
      // dropping the operator's loaded config on a same-runtime swap would be a
      // worse bug than the one the gate exists to prevent.
      mocks.getPresetById.mockResolvedValue({ name: 'my-preset', runtime: 'minqlx' });
      renderForm(
        [
          { id: 1, name: 'deb-host-a', runtime: 'minqlx' },
          { id: 2, name: 'deb-host-b', runtime: 'minqlx' },
        ],
        1,
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      await loadThePreset();

      fireEvent.click(screen.getByRole('button', { name: /select host 2/i }));

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));
      expect(screen.getByText('Editing preset:')).toBeInTheDocument();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('seeds the minqlxtended default when the form opens on a minqlxtended host', async () => {
      // The defect this guards: seeding every host from the minqlx builtin
      // ships plugins that cannot load on a minqlxtended server.
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(
        <AddInstanceForm
          initialData={{
            hosts: [{ id: 2, name: 'ubu-host', runtime: 'minqlxtended' }],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': '',
            },
            defaultSeedsByRuntime: {
              minqlx: { checkedPlugins: ['balance.py'], availableHooks: [], enabledHooks: [] },
              minqlxtended: { checkedPlugins: ['essentials.py'], availableHooks: [], enabledHooks: [] },
            },
          }}
          initialHostId={2}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));
      expect(mocks.draftAdapterPresets).toContain('default-minqlxtended');
      expect(mocks.draftAdapterPresets).not.toContain('default');

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0].checked_plugins).toEqual(['essentials']);
    });

    it('re-seeds from the new runtime when the host switches across runtimes', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(
        <AddInstanceForm
          initialData={{
            hosts: [
              { id: 1, name: 'deb-host', runtime: 'minqlx' },
              { id: 2, name: 'ubu-host', runtime: 'minqlxtended' },
            ],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': '',
            },
            defaultSeedsByRuntime: {
              minqlx: { checkedPlugins: ['balance.py'], availableHooks: [], enabledHooks: [] },
              minqlxtended: { checkedPlugins: ['essentials.py'], availableHooks: [], enabledHooks: [] },
            },
          }}
          initialHostId={1}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /select host 2/i }));
      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));

      await waitFor(() => expect(mocks.draftAdapterPresets).toContain('default-minqlxtended'));

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0].checked_plugins).toEqual(['essentials']);
    });

    it('keeps a manual plugin selection when switching between same-runtime hosts', async () => {
      // The no-wipe half of the re-seed guard, and the dominant path: every
      // existing user moves between minqlx hosts. Re-seeding there would
      // silently discard the operator's manual selection, which is exactly
      // what the original plan got wrong -- so pin it against the submitted
      // payload, not against a rendered label.
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(
        <AddInstanceForm
          initialData={{
            hosts: [
              { id: 1, name: 'deb-host-a', runtime: 'minqlx' },
              { id: 2, name: 'deb-host-b', runtime: 'minqlx' },
            ],
            presets: [],
            defaultConfigContents: {
              'server.cfg': '', 'mappool.txt': '', 'access.txt': '', 'workshop.txt': '',
            },
            defaultSeedsByRuntime: {
              minqlx: { checkedPlugins: ['balance.py'], availableHooks: [], enabledHooks: [] },
              minqlxtended: { checkedPlugins: ['essentials.py'], availableHooks: [], enabledHooks: [] },
            },
          }}
          initialHostId={1}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));

      // The operator edits the seeded selection by hand: drop balance, add irc.
      const pluginManagerProps = () => mocks.fileManagerProps
        .filter(props => props.checkable && props.capabilities.allowedExtensions.includes('.py'))
        .at(-1);
      act(() => {
        pluginManagerProps().onCheck('balance.py', false);
        pluginManagerProps().onCheck('irc.py', true);
      });
      await waitFor(() => expect(pluginManagerProps().checkedFiles).toEqual(new Set(['irc.py'])));

      fireEvent.click(screen.getByRole('button', { name: /select host 2/i }));
      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));

      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0].checked_plugins).toEqual(['irc']);
    });

    it('treats a runtime-less preset and a runtime-less host as compatible', async () => {
      // Legacy rows predate the runtime column, and nothing but minqlx ever
      // existed, so both sides normalize to minqlx and nothing is cleared.
      mocks.getPresetById.mockResolvedValue({ name: 'my-preset' });
      renderForm(
        [
          { id: 1, name: 'legacy-a' },
          { id: 2, name: 'legacy-b' },
        ],
        1,
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      await loadThePreset();

      fireEvent.click(screen.getByRole('button', { name: /select host 2/i }));

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('2'));
      expect(screen.getByText('Editing preset:')).toBeInTheDocument();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });
  });

  describe('preset compatibility gate on load', () => {
    const renderOnHost = () => render(
      <AddInstanceForm
        initialData={{
          hosts: [{ id: 1, name: 'deb-host', runtime: 'minqlx' }],
          presets: [{ id: 1, name: 'my-preset', is_builtin: false }],
          defaultConfigContents: {
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
          },
        }}
        initialHostId={1}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoadingSubmit={false}
        formError={null}
        onServerCfgLintStatusChange={vi.fn()}
        onDirtyStateChange={vi.fn()}
      />
    );

    it('sends the host runtime with the preset fetch', async () => {
      mocks.getPresetById.mockResolvedValue({ name: 'my-preset', runtime: 'minqlx' });
      renderOnHost();

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(mocks.getPresetById).toHaveBeenCalledWith(1, { targetRuntime: 'minqlx' }));
    });

    it('applies directly when the response carries no compatibility block', async () => {
      mocks.getPresetById.mockResolvedValue({ name: 'my-preset', runtime: 'minqlx' });
      renderOnHost();

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(screen.getByText('Editing preset:')).toBeInTheDocument());
      expect(screen.queryByText(/won.t carry over/i)).not.toBeInTheDocument();
    });

    it('does not apply a preset immediately when the response has stripped plugins', async () => {
      // The matched-pair regression test: without the compatibility gate this
      // response would apply exactly like the no-compatibility-block case
      // above, so "Editing preset:" appearing here is the bug the gate exists
      // to prevent.
      mocks.getPresetById.mockResolvedValue({
        name: 'my-preset',
        runtime: 'minqlxtended',
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [
            { path: 'essentials.py', verdict: 'incompatible', reasons: ['uses a minqlxtended-only API'], replacement: null },
          ],
          replacements: {},
        },
      });
      renderOnHost();

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await screen.findByText(/won.t carry over/i);
      expect(screen.queryByText('Editing preset:')).not.toBeInTheDocument();
    });

    it('shows a not-applied notice and closes the preset manager when the compatibility dialog is cancelled', async () => {
      mocks.getPresetById.mockResolvedValue({
        name: 'my-preset',
        runtime: 'minqlxtended',
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [
            { path: 'essentials.py', verdict: 'incompatible', reasons: ['uses a minqlxtended-only API'], replacement: null },
          ],
          replacements: {},
        },
      });
      renderOnHost();

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);

      const dialog = screen.getByRole('dialog');
      fireEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }));

      await waitFor(() => expect(screen.getByText(/was not applied/i)).toBeInTheDocument());
      expect(screen.getByText(/was not applied/i).textContent).toMatch(/my-preset/);
      expect(screen.queryByTestId('preset-manager')).not.toBeInTheDocument();
      expect(screen.queryByText('Editing preset:')).not.toBeInTheDocument();
    });

    it('records the target runtime on the loaded preset, not the preset\'s own source runtime', async () => {
      // Regression: loadedPreset.runtime used to be set from presetData.runtime
      // (the preset's declared source runtime, e.g. minqlx), which is never
      // equal to the host it was just loaded onto after a cross-runtime load.
      // handleHostChange compares loadedPreset.runtime against the current
      // host's runtime to decide whether to clear the preset -- storing the
      // source runtime instead of the target makes that comparison always
      // "mismatched" and silently wipes a correctly-applied preset's plugin
      // selection on the very next host reselection.
      mocks.getPresetById.mockResolvedValue({
        name: 'my-preset',
        runtime: 'minqlx',
        checked_plugins: ['ban.py'],
        compatibility: {
          preset_runtime: 'minqlx',
          target_runtime: 'minqlxtended',
          stripped: [],
          replacements: {},
        },
      });
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(
        <AddInstanceForm
          initialData={{
            hosts: [{ id: 1, name: 'mqx-host', runtime: 'minqlxtended' }],
            presets: [{ id: 1, name: 'my-preset', is_builtin: false }],
            defaultConfigContents: {
              'server.cfg': '',
              'mappool.txt': '',
              'access.txt': '',
              'workshop.txt': '',
            },
            // A recognizable, non-empty default seed so a reseed-to-default
            // is distinguishable from "no reseed happened" -- an empty
            // default seed would make both outcomes look like [].
            defaultSeedsByRuntime: {
              minqlx: { checkedPlugins: ['balance.py'], availableHooks: [], enabledHooks: [] },
              minqlxtended: { checkedPlugins: ['default_plugin.py'], availableHooks: [], enabledHooks: [] },
            },
          }}
          initialHostId={1}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          isLoadingSubmit={false}
          formError={null}
          onServerCfgLintStatusChange={vi.fn()}
          onDirtyStateChange={vi.fn()}
        />
      );

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await waitFor(() => expect(screen.getByText('Editing preset:')).toBeInTheDocument());

      // Re-selecting the SAME host (same runtime, "minqlxtended") must not
      // clear the just-loaded preset. The mocked InstanceBasicInfoForm (this
      // test file, ~line 176-191) renders a "Select Host 1" button wired to
      // onHostChange('1') regardless of current selection -- clicking it here
      // re-fires handleHostChange with hostId '1' while already on host 1,
      // which is exactly the "no-op reselect" scenario the bug affects.
      fireEvent.click(screen.getByRole('button', { name: /select host 1/i }));

      await waitFor(() => expect(screen.getByText('Editing preset:')).toBeInTheDocument());
      expect(screen.queryByText(/no longer matches this host/i)).not.toBeInTheDocument();

      // Prove it's not just the banner that survived: the operator's actual
      // loaded selection ('ban', from the preset) must still be what gets
      // submitted, not silently reseeded back to the runtime's default
      // ('default_plugin') by the no-op reselect.
      fireEvent.click(screen.getByRole('button', { name: /create instance/i }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0].checked_plugins).toEqual(['ban']);
    });

    it('applies a cross-runtime preset silently when every plugin is compatible', async () => {
      // stripped: [] is a real response shape -- every plugin scanned clean --
      // and it must not surface a dialog with nothing in it.
      mocks.getPresetById.mockResolvedValue({
        name: 'my-preset',
        runtime: 'minqlxtended',
        compatibility: {
          preset_runtime: 'minqlxtended',
          target_runtime: 'minqlx',
          stripped: [],
          replacements: {},
        },
      });
      renderOnHost();

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(screen.getByText('Editing preset:')).toBeInTheDocument());
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
          runtime: 'minqlxtended',
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
        .mockResolvedValueOnce({ name: 'presetB', runtime: 'minqlx' });
      renderOnHost();

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));

      // Load preset A and confirm the compatibility dialog, accepting the one
      // offered replacement (pre-checked by the dialog itself).
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      const dialog = screen.getByRole('dialog');
      fireEvent.click(within(dialog).getByRole('button', { name: /load preset/i }));

      await waitFor(() => expect(screen.getByText('Editing preset:').parentElement).toHaveTextContent('presetA'));
      expect(mocks.draftAdapterAcceptedReplacementsByPreset.presetA).toEqual(['essentials.py']);

      // Now load preset B, which needs no confirmation of its own.
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));

      await waitFor(() => expect(screen.getByText('Editing preset:').parentElement).toHaveTextContent('presetB'));
      expect(mocks.draftAdapterAcceptedReplacementsByPreset.presetB).toEqual([]);
    });

    it('leaves the active preset\'s accepted replacements intact when a subsequent load is cancelled', async () => {
      // Regression, round 2: an earlier fix cleared acceptedReplacements
      // speculatively at the start of every load, before it was known whether
      // the load would even complete. Since acceptedKey is a dependency of
      // useDraftWorkspace's seeding effect, that speculative clear re-seeded
      // preset A's still-active draft with an empty list immediately -- so
      // cancelling the load of preset B destroyed a replacement the operator
      // had explicitly accepted for A. Fixed by making the accepted list an
      // argument to applyPresetData (called only on confirm, never on cancel)
      // instead of ambient state cleared ahead of time.
      mocks.getPresetById
        .mockResolvedValueOnce({
          name: 'presetA',
          runtime: 'minqlxtended',
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
        .mockResolvedValueOnce({
          name: 'presetB',
          runtime: 'minqlxtended',
          compatibility: {
            preset_runtime: 'minqlxtended',
            target_runtime: 'minqlx',
            stripped: [
              { path: 'other.py', verdict: 'incompatible', reasons: ['unrelated'], replacement: null },
            ],
            replacements: {},
          },
        });
      renderOnHost();

      await waitFor(() => expect(screen.getByTestId('selected-host')).toHaveTextContent('1'));

      // Load preset A and confirm, accepting the offered replacement.
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      let dialog = screen.getByRole('dialog');
      fireEvent.click(within(dialog).getByRole('button', { name: /load preset/i }));

      await waitFor(() => expect(screen.getByText('Editing preset:').parentElement).toHaveTextContent('presetA'));
      expect(mocks.draftAdapterAcceptedReplacementsByPreset.presetA).toEqual(['essentials.py']);

      // Start loading preset B, then cancel out of its compatibility dialog.
      fireEvent.click(screen.getByRole('button', { name: /load preset/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm load preset/i }));
      await screen.findByText(/won.t carry over/i);
      dialog = screen.getByRole('dialog');
      fireEvent.click(within(dialog).getByRole('button', { name: /cancel/i }));

      // Preset A is still the active preset, and it must still show its
      // accepted replacement -- not silently reseeded to an empty list.
      expect(screen.getByText('Editing preset:').parentElement).toHaveTextContent('presetA');
      expect(mocks.draftAdapterAcceptedReplacementsByPreset.presetA).toEqual(['essentials.py']);
    });
  });
});
