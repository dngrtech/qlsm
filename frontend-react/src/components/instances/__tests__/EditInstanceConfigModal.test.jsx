import React, { useImperativeHandle } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createPreset: vi.fn(),
  flushEdits: vi.fn(),
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
  updateInstance: vi.fn(),
  updateInstanceConfig: vi.fn(),
  fileManagerProps: [],
  useDraftWorkspace: vi.fn(),
}));

vi.mock('@headlessui/react', () => {
  const Dialog = ({ children }) => <div>{children}</div>;
  Dialog.Panel = ({ children, transition: _transition, ...props }) => <div {...props}>{children}</div>;
  Dialog.Title = ({ children, ...props }) => <div {...props}>{children}</div>;
  const DialogBackdrop = ({ children, transition: _transition, ...props }) => <div {...props}>{children}</div>;

  const Transition = ({ show, children }) => (show ? <>{children}</> : null);
  Transition.Child = ({ children }) => <>{children}</>;

  return { Dialog, DialogBackdrop, Transition };
});

vi.mock('../../../services/api', () => ({
  createPreset: mocks.createPreset,
  getFactoryContent: mocks.getFactoryContent,
  getFactoryTree: mocks.getFactoryTree,
  getInstanceById: mocks.getInstanceById,
  getInstanceConfig: mocks.getInstanceConfig,
  getPresetById: mocks.getPresetById,
  getPresets: mocks.getPresets,
  updateInstance: mocks.updateInstance,
  updateInstanceConfig: mocks.updateInstanceConfig,
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

vi.mock('../../addInstance/LoadPresetModal', () => ({
  default: () => null,
}));

vi.mock('../../addInstance/SavePresetModal', () => ({
  default: ({ isOpen, onSave }) => (
    isOpen ? (
      <button
        type="button"
        onClick={() => onSave({ name: 'saved-from-edit', description: 'copy' })}
      >
        Confirm Save Preset
      </button>
    ) : null
  ),
}));

vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="info-tooltip">{text}</span>,
}));

vi.mock('../../fileManager', () => ({
  CONFIG_CAPS: {
    allowedExtensions: ['.cfg', '.txt'],
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
    return <div>file-manager</div>;
  }),
  useDraftAdapter: () => ({
    ...mocks.useDraftWorkspace(),
    hasChanges: false,
  }),
  useStateAdapter: ({ initialFiles = {}, serverTree = [] } = {}) => {
    const [files, setFiles] = React.useState(initialFiles);
    const reset = React.useCallback((nextFiles = {}) => {
      setFiles(nextFiles);
    }, []);
    return React.useMemo(() => ({
      tree: serverTree,
      readContent: vi.fn().mockResolvedValue(''),
      writeContent: vi.fn().mockResolvedValue(undefined),
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
    }), [files, reset, serverTree]);
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

describe('EditInstanceConfigModal preset saving', () => {
  let EditInstanceConfigModal;

  beforeEach(async () => {
    vi.clearAllMocks();
    mocks.fileManagerProps = [];
    if (!EditInstanceConfigModal) {
      ({ default: EditInstanceConfigModal } = await import('../EditInstanceConfigModal'));
    }
    mocks.createPreset.mockResolvedValue({ message: 'saved' });
    mocks.flushEdits.mockResolvedValue(undefined);
    mocks.getBinaryMeta.mockResolvedValue({});
    mocks.getFactoryContent.mockResolvedValue({ content: '' });
    mocks.getFactoryTree.mockResolvedValue([]);
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host',
      lan_rate_enabled: false,
      name: 'Test123',
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
    mocks.updateInstanceConfig.mockResolvedValue({ message: 'saved' });
    mocks.useDraftWorkspace.mockReturnValue({
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
    });
  });

  it('preserves checked plugin file paths when saving a preset from edit mode', async () => {
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
        checked_plugins: ['discord_extensions/balance.py'],
        factories: {},
        checked_factories: [],
      })
    );
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

  it('disables enabling 99k lan rate for ubuntu hosts', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
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
    expect(screen.getByTestId('info-tooltip')).toHaveTextContent('99k LAN rate is not compatible with Ubuntu.');
  });

  it('allows disabling an already-enabled ubuntu instance', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
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
    expect(screen.getByText('99k LAN rate is not compatible with Ubuntu.')).toBeInTheDocument();
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
});
