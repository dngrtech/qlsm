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
  saveBinaryMeta: vi.fn(),
  useDraftWorkspace: vi.fn(),
}));

vi.mock('../../../hooks/useDraftWorkspace', () => ({
  useDraftWorkspace: mocks.useDraftWorkspace,
}));

vi.mock('../../../services/api', () => ({
  getAvailablePortsForHost: mocks.getAvailablePortsForHost,
  getFactoryContent: mocks.getFactoryContent,
  getFactoryTree: mocks.getFactoryTree,
  getPresetById: vi.fn(),
  savePreset: vi.fn(),
  updatePreset: vi.fn(),
}));

vi.mock('../../../services/draftApi', () => ({
  getBinaryMeta: mocks.getBinaryMeta,
  saveBinaryMeta: mocks.saveBinaryMeta,
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
  FileManager: React.forwardRef(function MockFileManager(_props, ref) {
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
      serialize: () => ({ ...files }),
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

vi.mock('../SavePresetModal', () => ({ default: () => null }));
vi.mock('../LoadPresetModal', () => ({ default: () => null }));
vi.mock('../UpdatePresetModal', () => ({ default: () => null }));
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

describe('AddInstanceForm draft lifecycle', () => {
  let AddInstanceForm;

  beforeEach(async () => {
    vi.clearAllMocks();
    if (!AddInstanceForm) {
      ({ default: AddInstanceForm } = await import('../AddInstanceForm'));
    }
    mocks.getAvailablePortsForHost.mockResolvedValue({ available_ports: [] });
    mocks.getBinaryMeta.mockResolvedValue({});
    mocks.getFactoryContent.mockResolvedValue({ content: '' });
    mocks.getFactoryTree.mockResolvedValue([]);
    mocks.saveBinaryMeta.mockResolvedValue({});
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
    expect(screen.getByTestId('lan-rate-reason')).toHaveTextContent('99k LAN rate is not compatible with Ubuntu.');
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
});
