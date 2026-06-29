import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  qlentLanguage: { name: 'qlent' },
  qlentLinter: vi.fn(),
  savePreset: vi.fn(),
  saveBinaryMeta: vi.fn(),
  updatePreset: vi.fn(),
  useDraftWorkspace: vi.fn(),
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
    return <div>file-manager</div>;
  }),
  useDraftAdapter: () => ({
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
  }),
  useStateAdapter: ({ initialFiles = {}, serverTree = [] } = {}) => {
    const [files, setFiles] = React.useState(initialFiles);
    const reset = React.useCallback((nextFiles = {}) => {
      setFiles(nextFiles);
    }, []);
    const readContent = React.useCallback(async (path) => files[path] || '', [files]);
    const writeContent = React.useCallback(async (path, content) => {
      setFiles(prev => ({ ...prev, [path]: content || '' }));
    }, []);
    return React.useMemo(() => ({
      tree: serverTree,
      readContent,
      writeContent,
      upload: vi.fn().mockResolvedValue({}),
      deleteFile: vi.fn().mockResolvedValue(undefined),
      renameFile: vi.fn().mockResolvedValue(undefined),
      checkedFiles: new Set(Object.keys(files)),
      setChecked: vi.fn().mockResolvedValue(undefined),
      hasChanges: false,
      serialize: () => ({ files: { ...files }, folders: [] }),
      reset,
      loading: false,
      error: null,
    }), [files, readContent, reset, serverTree, writeContent]);
  },
}));

vi.mock('../InstanceBasicInfoForm', () => ({
  default: ({
    lanRateDisabled,
    lanRateEnabled,
    lanRateUnavailableReason,
    onHostChange,
    onLanRateChange,
    selectedHostId,
  }) => (
    <div>
      <div>basic-info</div>
      <div data-testid="selected-host">{selectedHostId || 'none'}</div>
      <div data-testid="lan-rate-enabled">{String(lanRateEnabled)}</div>
      <div data-testid="lan-rate-disabled">{String(lanRateDisabled)}</div>
      <div data-testid="lan-rate-reason">{lanRateUnavailableReason || ''}</div>
      <button type="button" onClick={() => onHostChange('1')}>Select Host 1</button>
      <button type="button" onClick={() => onHostChange('2')}>Select Host 2</button>
      <button type="button" onClick={() => onLanRateChange(!lanRateEnabled)}>Toggle 99k</button>
    </div>
  ),
}));

vi.mock('../../presetManager/PresetManagerModal', () => ({
  default: ({ isOpen, initialTab, initialOverwriteName, onSavePreset }) => (
    isOpen ? (
      <div data-testid="preset-manager" data-tab={initialTab} data-overwrite={initialOverwriteName || ''}>
        preset-manager
        <button
          type="button"
          onClick={() => onSavePreset({ name: 'saved-preset', description: 'copy' })}
        >
          Confirm Save Preset
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
});
