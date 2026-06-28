import React, { useImperativeHandle } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createPreset: vi.fn(),
  downloadPreset: vi.fn(),
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
  hooksTabProps: [],
  updateInstance: vi.fn(),
  updateInstanceConfig: vi.fn(),
  fileManagerProps: [],
  qlentLanguage: { name: 'qlent' },
  qlentLinter: vi.fn(),
  useDraftWorkspace: vi.fn(),
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
  default: ({ isOpen, onSave, savedPreset, onDownload }) => (
    isOpen ? (
      <div>
        <button
          type="button"
          onClick={() => onSave({ name: 'saved-from-edit', description: 'copy' })}
        >
          Confirm Save Preset
        </button>
        {savedPreset && (
          <button type="button" onClick={() => onDownload(savedPreset)}>
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
        <button type="button" onClick={() => props.onApplied?.()}>
          Mock Apply Hooks
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

vi.mock('../../../codemirror-lang-qlent', () => ({
  qlentLanguage: mocks.qlentLanguage,
  qlentLinter: mocks.qlentLinter,
}));

describe('EditInstanceConfigModal preset saving', () => {
  let EditInstanceConfigModal;

  beforeEach(async () => {
    vi.clearAllMocks();
    mocks.fileManagerProps = [];
    mocks.hooksTabProps = [];
    if (!EditInstanceConfigModal) {
      ({ default: EditInstanceConfigModal } = await import('../EditInstanceConfigModal'));
    }
    mocks.createPreset.mockResolvedValue({ message: 'saved', data: { id: 42, name: 'saved-from-edit' } });
    mocks.downloadPreset.mockResolvedValue(new Blob(['zip-bytes'], { type: 'application/zip' }));
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
    global.URL.createObjectURL = vi.fn(() => 'blob:qlsm-preset');
    global.URL.revokeObjectURL = vi.fn();
    vi.spyOn(document.body, 'appendChild');
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
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
    expect(global.URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    const anchor = document.body.appendChild.mock.calls.find(
      ([node]) => node instanceof HTMLAnchorElement,
    )?.[0];
    expect(anchor).toEqual(expect.objectContaining({
      href: 'blob:qlsm-preset',
      download: 'saved-from-edit.zip',
    }));
    expect(global.URL.revokeObjectURL).toHaveBeenCalledWith('blob:qlsm-preset');
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

  it('opens on the hooks tab and closes after hook apply', async () => {
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

    fireEvent.click(screen.getByRole('button', { name: /mock apply hooks/i }));

    expect(mocks.showSuccess).toHaveBeenCalledWith('LD_PRELOAD hooks saved. Apply task queued.');
    expect(onConfigSaved).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(mocks.hooksTabProps.at(-1).instanceId).toBe(1);
  });
});
